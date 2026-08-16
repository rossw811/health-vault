"""Collect raw transcripts only - no Claude involvement, no note-writing, no
relevance judgment, no concept-linking. Just: enumerate the queue, fetch
metadata + transcript for anything not already collected, save the raw text.

This exists so transcript collection can keep making real progress even when
no Claude session budget is available - a future Claude pass can process
these raw files into proper AI-first notes once budget is back, without
re-fetching anything.

Usage:
    python scripts/collect_raw_transcripts.py

Reads "YouTube Queue.md", writes one file per video to Research/YouTube/Raw/
named "<video-id>_full.txt" (metadata header + raw transcript body). Tracks
what's already collected in Research/YouTube/Raw/.collected_ids.json so
re-runs only fetch new videos. Honors the same permanent exclusion list
/youtube-channel uses (Research/YouTube/.state/_excluded-channels.json).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collector_common import (
    MAX_RETRIES,
    append_checkpoint_log,
    find_matching_podcast_episode,
    load_podcast_title_index,
    record_result,
    retry_eligible_ids,
)

# Same fix as podcast_collector.py, 2026-07-26: a video title with a non-cp1252
# character printed to a Task Scheduler-piped stdout (console default cp1252,
# not UTF-8) would crash the whole process with UnicodeEncodeError, killing
# the run past whatever result had already been written to disk. reconfigure()
# is Python 3.7+.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

VAULT_ROOT = Path(__file__).resolve().parent.parent  # portable — see NEW-MACHINE-SETUP.md, 2026-08-15
QUEUE_FILE = VAULT_ROOT / "YouTube Queue.md"
RAW_DIR = VAULT_ROOT / "Research" / "YouTube" / "Raw"
COLLECTED_IDS_FILE = RAW_DIR / ".collected_ids.json"
CHECKPOINT_LOG_FILE = RAW_DIR / ".checkpoint_log.jsonl"
LOCK_FILE = RAW_DIR / ".collector.lock"
PODCAST_STATE_FILE = VAULT_ROOT / "Research" / "Podcasts" / "Raw" / ".collected_ids.json"
EXCLUDED_CHANNELS_FILE = VAULT_ROOT / "Research" / "YouTube" / ".state" / "_excluded-channels.json"
SCRIPTS_DIR = Path(__file__).resolve().parent


def _pid_is_running(pid: int) -> bool:
    """Windows has no os.kill(pid, 0) liveness check - shell out to tasklist.
    POSIX (Linux, added 2026-08-15 for the CachyOS side - see
    NEW-MACHINE-SETUP.md) has a real portable liveness check via signal 0:
    it doesn't actually send a signal, just checks permissions/existence,
    raising ProcessLookupError if the PID is gone and PermissionError if it's
    alive but owned by another user (still "running" for this check's
    purpose, so both are handled explicitly rather than falling through to
    a bare except)."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        else:
            return True
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True, text=True,
    )
    return str(pid) in result.stdout


def acquire_singleton_lock() -> bool:
    """Real incident 2026-07-25: Stop-ScheduledTask does not reliably kill this
    script's child process tree, so re-running the scheduled task (or a manual
    restart) can stack up multiple concurrent instances - each with its own
    stale in-memory `collected` dict, all racing to overwrite the same
    .collected_ids.json and clobbering each other's progress. This lock makes
    that structurally impossible regardless of whether Task Scheduler's own
    process tracking behaves."""
    if LOCK_FILE.exists():
        try:
            existing_pid = int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            existing_pid = None
        if existing_pid and _pid_is_running(existing_pid):
            print(f"Another collector instance is already running (PID {existing_pid}) - exiting.")
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_singleton_lock() -> None:
    with contextlib.suppress(OSError):
        LOCK_FILE.unlink()

CHANNEL_URL_RE = re.compile(r"youtube\.com/(@[\w.-]+|channel/[\w-]+|user/[\w-]+)/?$")
VIDEO_URL_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_urls_from_queue() -> tuple[list[str], list[str]]:
    """Every URL found on an unchecked `- [ ]` line, split into (priority_urls,
    normal_urls) based on whether it's under a heading containing "PRIORITY".
    Returned as a tuple rather than one concatenated list (2026-07-26) so
    callers can also identify which specific video IDs came from a priority
    channel later - a real gap in the first version of this fix: retry-eligible
    videos (see _build_worklist) are looked up by ID from the whole
    collected-history dict, not re-derived from this function's ordering, so
    concatenating the two lists here only prioritized brand-new channel videos
    and silently left retries (which is where almost an entire priority
    channel's backlog ends up, once it's been attempted and failed once)
    unprioritized."""
    priority_urls = []
    normal_urls = []
    in_priority_section = False
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_priority_section = "PRIORITY" in stripped.upper()
            continue
        if not stripped.startswith("- [ ]"):
            continue
        match = re.search(r"https?://\S+", line)
        if match:
            url = match.group(0).rstrip(")")
            (priority_urls if in_priority_section else normal_urls).append(url)
    return priority_urls, normal_urls


def is_channel_url(url: str) -> bool:
    return bool(CHANNEL_URL_RE.search(url)) and "watch" not in url


def excluded_channel_slugs() -> set[str]:
    data = load_json(EXCLUDED_CHANNELS_FILE, {})
    return set(data.keys())


def channel_slug(url: str) -> str:
    match = re.search(r"(@[\w.-]+|channel/[\w-]+|user/[\w-]+)", url)
    if not match:
        return url
    return match.group(1).lstrip("@").replace("channel/", "").replace("user/", "").lower()


def list_channel_video_ids(channel_url: str) -> list[str]:
    videos_url = channel_url.rstrip("/") + "/videos"
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", videos_url],
        capture_output=True, text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def extract_video_id(url: str) -> str | None:
    match = VIDEO_URL_RE.search(url)
    return match.group(1) if match else None


def fetch_metadata(video_id: str) -> dict:
    result = subprocess.run(
        ["yt-dlp", "--skip-download",
         "--print", "title", "--print", "channel", "--print", "upload_date",
         "--print", "duration_string", "--print", "view_count", "--print", "like_count",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True,
    )
    lines = result.stdout.splitlines()
    keys = ["title", "channel", "upload_date", "duration", "view_count", "like_count"]
    padded = lines + [""] * (len(keys) - len(lines))
    return dict(zip(keys, padded, strict=True))


# --- Parallel worker pool -------------------------------------------------
# Real efficiency win (2026-07-25): the old design ran one collect_one() at a
# time, each spawning a fresh fetch_transcript_auto.py -> whisper_transcribe.py
# subprocess chain that reloads the Whisper model from scratch every single
# video. With 12 CPU cores typically idle during a single-video run, this
# leaves most of the machine unused. The parallel path below runs N worker
# processes, each loading its Whisper model exactly ONCE (via _worker_init,
# called by ProcessPoolExecutor when each worker starts) and reusing it across
# every video that worker is assigned - both across-video parallelism AND
# eliminating repeated model-load overhead. Workers are pure functions with no
# shared state; only the main process ever touches collected_ids.json, so the
# same singleton-lock/single-writer guarantees from the 2026-07-25 concurrency
# incident still hold - the pool lives entirely inside one locked process.
_worker_model = None
_podcast_title_index: list[tuple[str, str]] = []


def _worker_init(model_size: str, cpu_threads: int) -> None:
    global _worker_model, _podcast_title_index
    sys.path.insert(0, str(SCRIPTS_DIR))  # spawned worker processes don't inherit this
    from whisper_transcribe import load_model
    _worker_model = load_model(model_size, cpu_threads)
    # Loaded once per worker, not once per video - the podcast collector's
    # own state file only grows slowly relative to a worker's video count,
    # so a per-worker snapshot (rather than re-reading the file every video)
    # is the right tradeoff. A video that's covered by a podcast episode
    # collected mid-run (after this worker started) just gets processed
    # normally instead of matched - acceptable, not worth a live re-read.
    _podcast_title_index = load_podcast_title_index(PODCAST_STATE_FILE)


def _process_one_video(video_id: str) -> dict:
    """Runs inside a worker process - pure function, returns a result dict.
    The main process is the only writer to shared state/disk."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from fetch_transcript_auto import try_official_captions
    from whisper_transcribe import transcribe_video

    meta = fetch_metadata(video_id)

    # Cross-collector dedup (2026-07-25): RSS-based podcast collection is
    # faster and more reliable for the same episode content - if this video
    # is very likely already covered by a collected podcast episode, skip
    # the redundant transcription work entirely.
    podcast_match = find_matching_podcast_episode(
        meta.get("title", ""), meta.get("upload_date", ""), _podcast_title_index
    )
    if podcast_match:
        return {
            "video_id": video_id, "status": "skipped-covered-by-podcast",
            "reason": f"matches podcast episode: {podcast_match}",
            "title": meta.get("title", ""), "meta": meta,
        }

    transcript, method = try_official_captions(video_id)
    if not transcript:
        try:
            transcript = transcribe_video(video_id, batched_model=_worker_model)
            method = "local whisper"
        except Exception as exc:  # noqa: BLE001 - report any failure reason plainly to the main process
            return {"video_id": video_id, "status": "failed", "reason": f"whisper fallback failed: {exc}"[:300], "title": meta.get("title", ""), "meta": meta}

    qc_warning = qc_check_transcript(video_id, meta.get("title", ""), meta.get("channel", ""), meta.get("duration", ""), method, transcript)
    if qc_warning:
        return {"video_id": video_id, "status": "qc-failed", "reason": qc_warning, "title": meta.get("title", ""), "meta": meta}

    return {"video_id": video_id, "status": "ok", "title": meta.get("title") or video_id, "transcript": transcript, "method": method, "meta": meta}


def safe_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[\s]+", " ", slug)
    return slug[:80]


def duration_to_seconds(duration_str: str) -> float | None:
    """yt-dlp's duration_string is 'H:MM:SS' or 'M:SS' - parse to seconds."""
    if not duration_str:
        return None
    parts = duration_str.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return float(seconds)


def qc_check_transcript(video_id: str, title: str, channel: str, duration_str: str, method: str, transcript: str) -> str | None:
    """Real-time version of the QC check that only existed as a batched, after-the-fact
    script during the 2026-07-25 corruption incident - catches the same class of
    problem (error text saved as if it were a real transcript) per-video, as it
    happens, instead of discovering it days later across tens of thousands of files."""
    import pandas as pd
    from schemas import raw_transcript_metadata_schema, validate_or_report

    row = {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "duration_seconds": duration_to_seconds(duration_str),
        "char_count": len(transcript),
        "word_count": len(transcript.split()),
        "transcript_method": method if method in ("official captions", "local whisper") else "unknown",
    }
    ok, messages = validate_or_report(raw_transcript_metadata_schema, pd.DataFrame([row]), "qc")
    return None if ok else "; ".join(messages)


def write_result_to_disk(result: dict, collected: dict) -> str:
    """Main-process-side only: takes a worker's result dict, writes the file
    (if any) and updates the shared `collected` state. This is the ONLY place
    that touches disk/shared state, regardless of how many parallel workers
    produced results - preserves the single-writer guarantee."""
    video_id = result["video_id"]
    if result["status"] == "skipped-covered-by-podcast":
        record_result(collected, video_id, "skipped-covered-by-podcast", result["reason"], result.get("title", ""))
        return f"skipped-covered-by-podcast ({result['reason']})"
    if result["status"] == "failed":
        record_result(collected, video_id, "failed", result["reason"], result.get("title", ""))
        final_status = collected[video_id]["status"]  # record_result may demote to permanently-failed
        if final_status == "permanently-failed":
            return f"permanently-failed after {collected[video_id]['retry_count']} attempts ({result['reason']})"
        return f"failed ({result['reason']})"
    if result["status"] == "qc-failed":
        record_result(collected, video_id, "qc-failed", result["reason"], result.get("title", ""))
        return f"qc-failed ({result['reason']})"

    meta = result["meta"]
    title = result["title"]
    method = result["method"]
    out_path = RAW_DIR / f"{safe_slug(title)} [{video_id}]_full.txt"
    header = (
        f"video_id: {video_id}\n"
        f"title: {title}\n"
        f"channel: {meta.get('channel', '')}\n"
        f"upload_date: {meta.get('upload_date', '')}\n"
        f"duration: {meta.get('duration', '')}\n"
        f"view_count: {meta.get('view_count', '')}\n"
        f"like_count: {meta.get('like_count', '')}\n"
        f"transcript_method: {method}\n"
        f"url: https://www.youtube.com/watch?v={video_id}\n"
        f"---\n\n"
    )
    out_path.write_text(header + result["transcript"], encoding="utf-8")
    record_result(collected, video_id, "ok", title=title, extra={"file": out_path.name})
    return f"ok -> {out_path.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=2,
                         help="Number of worker processes (each loads its own Whisper model once). "
                              "Default 2 (cpu-threads=3 -> 6 threads) - halved from an earlier 4/12 default "
                              "2026-07-25 once podcast_collector.py started running as a second concurrent "
                              "scheduled task on the same 12-core machine; 4+4 workers oversubscribed the "
                              "machine (24 threads for 12 cores) and measurably slowed both down.")
    parser.add_argument("--model", default="small", help="whisper.cpp model size")
    parser.add_argument("--cpu-threads", type=int, default=4,
                         help="CPU threads per worker's Whisper model - keep (parallel * cpu-threads, summed "
                              "across every collector that might run at the same time) near your core count. "
                              "Default 4 as of 2026-08-08 (was 3) - the actual 2026-07-27 controlled sweep found "
                              "4 threads/process is the true optimum under two-collector contention (see "
                              "CLAUDE.md), and both wrapper scripts already pass --cpu-threads 4 explicitly; "
                              "this bare default only mattered for a manual invocation outside the wrappers, "
                              "which was silently using the stale pre-sweep value.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not acquire_singleton_lock():
        return 1
    try:
        return _run(args.parallel, args.model, args.cpu_threads)
    finally:
        release_singleton_lock()


def _build_worklist(collected: dict) -> list[str]:
    """Enumerate every not-yet-collected video ID across all queue lines
    (channels + single videos). Channel enumeration (one yt-dlp --flat-playlist
    call per channel) is I/O-bound, not CPU-bound - real bug found 2026-07-25:
    running these sequentially meant the transcription pool sat completely idle
    while dozens of queued channels were enumerated one at a time, potentially
    for minutes, before any actual (parallelizable) transcription work began.
    A thread pool (not the process pool used for transcription - no GIL
    contention issue here since these are just waiting on subprocess I/O) fixes
    this cheaply."""
    priority_urls, normal_urls = extract_urls_from_queue()
    urls = priority_urls + normal_urls
    channel_urls = [u for u in urls if is_channel_url(u)]
    priority_channel_urls = {u for u in priority_urls if is_channel_url(u)}
    single_urls = [u for u in urls if not is_channel_url(u)]

    new_video_ids = []
    # video_id -> channel_url, not a flat set (2026-07-27 fix - see below):
    # retry ordering needs to know WHICH priority channel a video came from,
    # not just that it came from some priority channel.
    priority_video_ids: dict[str, str] = {}
    if channel_urls:
        # Enumeration itself still runs concurrently (I/O-bound, no reason to
        # serialize it) but results are assembled back out in channel_urls'
        # own (priority-first) order, not whichever channel's yt-dlp call
        # happens to finish first - as_completed() order would otherwise
        # silently defeat the priority-section sort above.
        results_by_url = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(channel_urls))) as executor:
            futures = {executor.submit(list_channel_video_ids, url): url for url in channel_urls}
            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                channel_video_ids = future.result()
                print(f"channel {url}: {len(channel_video_ids)} videos")
                results_by_url[url] = channel_video_ids
                if url in priority_channel_urls:
                    for vid in channel_video_ids:
                        priority_video_ids[vid] = url
        for url in channel_urls:
            new_video_ids.extend(vid for vid in results_by_url.get(url, []) if vid not in collected)

    for url in single_urls:
        vid = extract_video_id(url)
        if vid and vid not in collected:
            new_video_ids.append(vid)

    # Failed-video retry system (2026-07-25): a video that failed once is not
    # gone forever - if the pipeline has since changed (version bump) or
    # enough backoff time has passed, retry it alongside genuinely new videos.
    retry_ids = retry_eligible_ids(collected)
    if retry_ids:
        print(f"{len(retry_ids)} previously-failed video(s) eligible for retry this pass.")

    # Real gap found 2026-07-26, then a deeper version of the same gap found
    # 2026-07-27 - three iterations to get this right, all kept here so the
    # reasoning isn't lost:
    #   v1 (2026-07-26): sorted priority-ness WITHIN new and WITHIN retry
    #   separately, but put ALL new videos (any channel) ahead of ALL retries -
    #   a fully-enumerated priority channel (nothing "new" left) still lost to
    #   an unrelated channel's brand-new videos.
    #   v2 (2026-07-26, later): grouped priority-as-a-block ahead of
    #   non-priority-as-a-block, new-vs-retry second - fixed the above, but
    #   `retry_eligible_ids()` returns videos in raw historical dict-insertion
    #   order with no channel awareness, so WITHIN the priority-retry block,
    #   a lower-ranked priority channel's retries could land ahead of a
    #   higher-ranked one's.
    #   v3 (2026-07-27): fixed v2's internal retry-block ordering by channel
    #   rank - but this exposed a THIRD, deeper gap: `priority_new` still came
    #   entirely ahead of `priority_retry` as separate tiers, so a channel that
    #   simply publishes on an ongoing basis (Peter Attia's podcast) could
    #   perpetually generate brand-new episodes that jump the entire queue
    #   ahead of Huberman/Vigorous Steve's whole retry backlog (422/427 and
    #   674/674 videos respectively, from the 2026-07-25 mass-failure
    #   incident) - forever, since there's always another new Attia episode.
    #   Confirmed live: even after the v3-only fix and a collector restart,
    #   the very first video processed was still a brand-new Peter Attia
    #   episode, not Huberman/Vigorous Steve, exactly this failure mode.
    # Final structure: channel rank is the primary sort key for ALL priority
    # videos (new and retry together), new-before-retry only as a tiebreaker
    # within the same channel - so Huberman's entire catalog (new + retry)
    # is exhausted before Vigorous Steve's, before Ben Winney's, etc., and a
    # lower-ranked priority channel's fresh content can never preempt a
    # higher-ranked channel's backlog.
    channel_rank = {url: i for i, url in enumerate(channel_urls)}
    priority_all = sorted(
        [(v, False) for v in new_video_ids if v in priority_video_ids]
        + [(v, True) for v in retry_ids if v in priority_video_ids],
        key=lambda item: (channel_rank.get(priority_video_ids[item[0]], len(channel_rank)), item[1]),
    )
    priority_ordered = [v for v, _is_retry in priority_all]
    other_new = [v for v in new_video_ids if v not in priority_video_ids]
    other_retry = [v for v in retry_ids if v not in priority_video_ids]
    if priority_ordered:
        print(f"{len(priority_ordered)} video(s) from priority channels (new + retry combined) - sorted to the very front, by channel rank.")
    video_ids = priority_ordered + other_new + other_retry

    # de-dupe while preserving order, in case the same video appears via
    # multiple queue lines (a channel plus an individually-queued video from it)
    seen = set()
    deduped = []
    for vid in video_ids:
        if vid not in seen:
            seen.add(vid)
            deduped.append(vid)
    return deduped


def _run(parallel: int = 2, model_size: str = "small", cpu_threads: int = 4) -> int:
    collected = load_json(COLLECTED_IDS_FILE, {})
    video_ids = _build_worklist(collected)
    print(f"{len(video_ids)} new video(s) to process, {parallel} parallel worker(s).")

    total_ok, total_failed, total_qc_failed, total_permanent, total_podcast_skip = 0, 0, 0, 0, 0

    if not video_ids:
        print("\nNothing new to collect this pass.")
        return 0

    pool_broken = False
    remaining_unprocessed = 0
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=parallel, initializer=_worker_init, initargs=(model_size, cpu_threads)
    ) as executor:
        futures = {executor.submit(_process_one_video, vid): vid for vid in video_ids}
        pending = set(futures)
        for future in concurrent.futures.as_completed(futures):
            pending.discard(future)
            vid = futures[future]
            try:
                result = future.result()
            except concurrent.futures.BrokenExecutor as exc:
                # Real incident 2026-07-26: one worker crash (OOM, segfault) makes the
                # WHOLE pool permanently broken - every other pending/future submission
                # raises this same error instantly, not just the video that triggered it.
                # The old blanket `except Exception` here silently recorded every one of
                # those as a genuine per-video "failed" result, burning through an entire
                # multi-thousand-video worklist in minutes with zero real work done and
                # needlessly consuming each video's limited retry budget. Stop immediately
                # instead - leave every not-yet-completed video untouched (still "new" for
                # the next run, no retry count spent) and let the wrapper script's loop
                # restart with a fresh, healthy pool.
                print(
                    f"\nProcess pool broken ({exc}) - stopping this pass early. "
                    f"{len(pending)} video(s) left unprocessed (not marked failed - "
                    "will be attempted fresh next run, not treated as a retry)."
                )
                pool_broken = True
                remaining_unprocessed = len(pending)
                break
            except Exception as exc:  # noqa: BLE001 - a single worker crash shouldn't take down the whole pool/lose other results
                result = {"video_id": vid, "status": "failed", "reason": f"worker crashed: {exc}"[:300], "title": ""}
                outcome = write_result_to_disk(result, collected)
                print(f"{vid}: {outcome}")
                if outcome.startswith("failed"):
                    total_failed += 1
                elif outcome.startswith("permanently-failed"):
                    total_permanent += 1
                save_json(COLLECTED_IDS_FILE, collected)
                continue
            outcome = write_result_to_disk(result, collected)
            print(f"{vid}: {outcome}")
            if outcome.startswith("ok"):
                total_ok += 1
            elif outcome.startswith("skipped-covered-by-podcast"):
                total_podcast_skip += 1
            elif outcome.startswith("permanently-failed"):
                total_permanent += 1
            elif outcome.startswith("failed"):
                total_failed += 1
            elif outcome.startswith("qc-failed"):
                total_qc_failed += 1
            save_json(COLLECTED_IDS_FILE, collected)  # after every result - a crash loses at most one in-flight video

    if pool_broken:
        print(
            f"\nStopped early after a broken process pool: {total_ok} ok, {total_failed} failed, "
            f"{remaining_unprocessed} left for the next attempt. Exiting so the wrapper script "
            "restarts with a fresh pool rather than continuing to churn through guaranteed failures."
        )
        return 1

    print(
        f"\nDone this pass: {len(video_ids)} new attempted, {total_ok} raw transcripts saved, "
        f"{total_podcast_skip} skipped (already covered by a collected podcast episode), "
        f"{total_failed} failed (will retry later), {total_permanent} gave up permanently after {MAX_RETRIES} attempts, "
        f"{total_qc_failed} QC-flagged (suspiciously short vs. duration - review before trusting)."
    )
    append_checkpoint_log(CHECKPOINT_LOG_FILE, {
        "attempted": len(video_ids), "ok": total_ok, "skipped_covered_by_podcast": total_podcast_skip,
        "failed": total_failed, "permanently_failed": total_permanent, "qc_failed": total_qc_failed,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
