"""Collect raw podcast episode transcripts - the audio-native sibling of
collect_raw_transcripts.py. No Claude involvement, no note-writing.

Podcast audio is a direct public HTTP download from the feed's own
<enclosure> URL - no yt-dlp, no IP-block/anti-bot fighting, no ffmpeg
extraction step needed (most podcast feeds serve mp3/m4a directly). This
also means podcasts can surface bonus/extended content some creators publish
there but not to YouTube.

Reads "Podcast Queue.md" (same `- [ ]`/`- [x]` convention as YouTube Queue.md),
each unchecked line a podcast RSS feed URL. Writes one file per episode to
Research/Podcasts/Raw/, named "<title> [<guid-hash>]_full.txt". Reuses the
same singleton-lock, parallel-worker-pool, and checkpoint/retry machinery as
collect_raw_transcripts.py via collector_common.py.

Usage:
    python scripts/podcast_collector.py [--parallel 4] [--model small]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collector_common import append_checkpoint_log, is_eligible_for_retry, record_result

# Real incident 2026-07-26: printing an episode title containing a non-cp1252
# character (e.g. accented foreign names) crashed the whole process with
# UnicodeEncodeError when stdout was piped through the Windows Task Scheduler
# wrapper (console encoding defaults to cp1252, not UTF-8) - killed the entire
# collector run after the crashing print, not just that one episode's log line
# (the result itself was already written to disk beforehand, so no data was
# lost, but the run died and had to be restarted manually). reconfigure() is
# Python 3.7+; safe here since the rest of this script already assumes 3.10+.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

VAULT_ROOT = Path(__file__).resolve().parent.parent  # portable — see NEW-MACHINE-SETUP.md, 2026-08-15
QUEUE_FILE = VAULT_ROOT / "Podcast Queue.md"
RAW_DIR = VAULT_ROOT / "Research" / "Podcasts" / "Raw"
COLLECTED_IDS_FILE = RAW_DIR / ".collected_ids.json"
CHECKPOINT_LOG_FILE = RAW_DIR / ".checkpoint_log.jsonl"
LOCK_FILE = RAW_DIR / ".collector.lock"
SCRIPTS_DIR = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (compatible; HealthVaultPodcastCollector/1.0)"


def _pid_is_running(pid: int) -> bool:
    """See the identical fix + rationale in collect_raw_transcripts.py's own
    _pid_is_running (added 2026-08-15 for the CachyOS side) - POSIX has a
    real portable liveness check via os.kill(pid, 0), Windows doesn't."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        else:
            return True
    result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
    return str(pid) in result.stdout


def acquire_singleton_lock() -> bool:
    """Same lock discipline as collect_raw_transcripts.py - see that file's
    2026-07-25 incident note for why this matters."""
    if LOCK_FILE.exists():
        try:
            existing_pid = int(LOCK_FILE.read_text().strip())
        except (ValueError, OSError):
            existing_pid = None
        if existing_pid and _pid_is_running(existing_pid):
            print(f"Another podcast collector instance is already running (PID {existing_pid}) - exiting.")
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_singleton_lock() -> None:
    with contextlib.suppress(OSError):
        LOCK_FILE.unlink()


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


def extract_feed_urls_from_queue() -> list[str]:
    """Every RSS feed URL on an unchecked `- [ ]` line, with URLs under a
    heading containing "PRIORITY" moved to the front - same fix as
    collect_raw_transcripts.py's extract_urls_from_queue() (2026-07-26), for
    the same reason: a priority heading is advisory-only unless something
    actually sorts by it, since feed parsing runs through a thread pool whose
    completion order doesn't match file order."""
    priority_urls = []
    normal_urls = []
    in_priority_section = False
    if not QUEUE_FILE.exists():
        return priority_urls
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
    return priority_urls + normal_urls


def safe_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[\s]+", " ", slug)
    return slug[:80]


def episode_id(guid: str) -> str:
    """Podcast GUIDs are often long URLs/UUIDs - hash to a short stable ID
    for filenames and the collected-state key, same role video_id plays for
    YouTube."""
    return hashlib.sha256(guid.encode("utf-8")).hexdigest()[:16]


def parse_rss_feed(feed_url: str) -> list[dict]:
    """Returns every episode with a usable audio enclosure: {guid, title,
    audio_url, pub_date, channel}. Real RSS feeds vary in strictness - skip
    malformed items rather than crashing the whole feed on one bad entry."""
    req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    channel = root.find("channel")
    channel_title = channel.findtext("title", "").strip() if channel is not None else ""

    episodes = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None
        if not audio_url or not title:
            continue
        guid = (item.findtext("guid") or title).strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        episodes.append({
            "guid": guid, "title": title, "audio_url": audio_url,
            "pub_date": pub_date, "channel": channel_title,
        })
    return episodes


def download_audio_direct(audio_url: str, dest_dir: Path) -> Path:
    """Direct HTTP download of the feed's own enclosure URL - a real
    efficiency win over the YouTube path: no yt-dlp, no anti-bot IP-block
    fighting, no ffmpeg extraction step (podcast feeds serve compressed audio
    directly, already in a format faster-whisper/ffmpeg can read as-is)."""
    ext = ".mp3" if ".mp3" in audio_url.lower() else ".m4a" if ".m4a" in audio_url.lower() else ".audio"
    dest_path = dest_dir / f"episode{ext}"
    req = urllib.request.Request(audio_url, headers={"User-Agent": USER_AGENT})
    try:
        # Stream in 1MB chunks instead of resp.read() - added 2026-08-08. A
        # podcast episode can be 50-200MB; reading the whole body into memory
        # before writing (the prior behavior) meant up to --parallel
        # concurrent workers could each be holding a full episode in RAM at
        # once, on top of their own loaded Whisper model - a plausible
        # undiagnosed contributor to this vault's documented OOM incidents
        # (buglog.md, 2026-07-25) even though it wasn't confirmed as the
        # direct trigger of any specific one.
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"podcast audio download failed: {exc}") from exc
    return dest_path


# --- Parallel worker pool (mirrors collect_raw_transcripts.py) ------------
_worker_model = None


def _worker_init(model_size: str, cpu_threads: int) -> None:
    global _worker_model
    sys.path.insert(0, str(SCRIPTS_DIR))
    from whisper_transcribe import load_model
    _worker_model = load_model(model_size, cpu_threads)


def _process_one_episode(episode: dict) -> dict:
    """Runs inside a worker process - pure function, returns a result dict."""
    import tempfile

    sys.path.insert(0, str(SCRIPTS_DIR))
    from whisper_transcribe import transcribe

    eid = episode_id(episode["guid"])
    try:
        with tempfile.TemporaryDirectory(prefix="podcast_dl_") as tmp:
            audio_path = download_audio_direct(episode["audio_url"], Path(tmp))
            transcript = transcribe(audio_path, batched_model=_worker_model)
    except Exception as exc:  # noqa: BLE001 - report any failure reason plainly to the main process
        return {"episode_id": eid, "status": "failed", "reason": str(exc)[:300], "title": episode["title"], "episode": episode}

    return {"episode_id": eid, "status": "ok", "title": episode["title"], "transcript": transcript, "episode": episode}


def write_result_to_disk(result: dict, collected: dict) -> str:
    """Main-process-side only - see collect_raw_transcripts.py's identical
    single-writer discipline."""
    eid = result["episode_id"]
    if result["status"] == "failed":
        record_result(collected, eid, "failed", result["reason"], result.get("title", ""))
        final_status = collected[eid]["status"]
        if final_status == "permanently-failed":
            return f"permanently-failed after {collected[eid]['retry_count']} attempts ({result['reason']})"
        return f"failed ({result['reason']})"

    episode = result["episode"]
    title = result["title"]
    out_path = RAW_DIR / f"{safe_slug(title)} [{eid}]_full.txt"
    header = (
        f"episode_guid: {episode['guid']}\n"
        f"title: {title}\n"
        f"channel: {episode.get('channel', '')}\n"
        f"pub_date: {episode.get('pub_date', '')}\n"
        f"audio_url: {episode['audio_url']}\n"
        f"transcript_method: local whisper (direct RSS audio download)\n"
        f"---\n\n"
    )
    out_path.write_text(header + result["transcript"], encoding="utf-8")
    record_result(collected, eid, "ok", title=title, extra={"file": out_path.name})
    return f"ok -> {out_path.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", type=int, default=2,
                         help="Halved from an earlier default of 4 (2026-07-25): this collector and "
                              "collect_raw_transcripts.py's YouTube collector now often run at the same "
                              "time as two separate scheduled tasks on the same machine - 4+4 workers "
                              "oversubscribed a 12-core machine (24 threads) and measurably slowed both down.")
    parser.add_argument("--model", default="small")
    parser.add_argument("--cpu-threads", type=int, default=4,
                         help="Default 4 as of 2026-08-08 (was 3) - matches the 2026-07-27 controlled-sweep "
                              "optimum (see CLAUDE.md) that both wrapper scripts already pass explicitly.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not acquire_singleton_lock():
        return 1
    try:
        return _run(args.parallel, args.model, args.cpu_threads)
    finally:
        release_singleton_lock()


def _build_worklist(collected: dict) -> list[dict]:
    """The episode dict (guid/title/audio_url/etc) only exists transiently
    from parsing the feed - unlike YouTube's video_id (a stable ID we can
    retry with nothing but the ID itself), a podcast episode needs its full
    dict again to retry. So retry eligibility is checked here, against each
    freshly-parsed episode, rather than as a separate ID-only list."""
    feed_urls = extract_feed_urls_from_queue()  # priority-section feeds already sorted first
    episodes = []
    retry_count_this_pass = 0
    if feed_urls:
        # Parsing itself still runs concurrently, but results are assembled
        # back out in feed_urls' own (priority-first) order, not whichever
        # feed happens to parse fastest - as_completed() order would
        # otherwise silently defeat the priority-section sort above (same
        # fix as collect_raw_transcripts.py's _build_worklist, 2026-07-26).
        episodes_by_url = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(feed_urls))) as executor:
            futures = {executor.submit(parse_rss_feed, url): url for url in feed_urls}
            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                try:
                    feed_episodes = future.result()
                except Exception as exc:  # noqa: BLE001 - one bad feed shouldn't stop the others
                    print(f"feed {url}: FAILED to parse - {exc}")
                    continue
                print(f"feed {url}: {len(feed_episodes)} episodes")
                episodes_by_url[url] = feed_episodes
        for url in feed_urls:
            for ep in episodes_by_url.get(url, []):
                eid = episode_id(ep["guid"])
                if eid not in collected:
                    episodes.append(ep)
                elif is_eligible_for_retry(collected[eid]):
                    episodes.append(ep)
                    retry_count_this_pass += 1

    if retry_count_this_pass:
        print(f"{retry_count_this_pass} previously-failed episode(s) eligible for retry this pass.")

    return episodes


def _run(parallel: int = 2, model_size: str = "small", cpu_threads: int = 4) -> int:
    collected = load_json(COLLECTED_IDS_FILE, {})
    episodes = _build_worklist(collected)
    print(f"{len(episodes)} new episode(s) to process, {parallel} parallel worker(s).")

    total_ok, total_failed, total_permanent = 0, 0, 0

    if not episodes:
        print("\nNothing new to collect this pass.")
        return 0

    pool_broken = False
    remaining_unprocessed = 0
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=parallel, initializer=_worker_init, initargs=(model_size, cpu_threads)
    ) as executor:
        futures = {executor.submit(_process_one_episode, ep): ep for ep in episodes}
        pending = set(futures)
        for future in concurrent.futures.as_completed(futures):
            pending.discard(future)
            ep = futures[future]
            eid = episode_id(ep["guid"])
            try:
                result = future.result()
            except concurrent.futures.BrokenExecutor as exc:
                # Same fix as collect_raw_transcripts.py, 2026-07-26: once one worker
                # crashes catastrophically, the whole pool is permanently broken and
                # every remaining submission raises this same error instantly - don't
                # record those as real per-episode failures (that burns their retry
                # budget for nothing). Stop this pass, leave the rest genuinely unattempted.
                print(
                    f"\nProcess pool broken ({exc}) - stopping this pass early. "
                    f"{len(pending)} episode(s) left unprocessed (not marked failed - "
                    "will be attempted fresh next run, not treated as a retry)."
                )
                pool_broken = True
                remaining_unprocessed = len(pending)
                break
            except Exception as exc:  # noqa: BLE001 - a single worker crash shouldn't take down the whole pool
                result = {"episode_id": eid, "status": "failed", "reason": f"worker crashed: {exc}"[:300], "title": ep.get("title", "")}
                outcome = write_result_to_disk(result, collected)
                print(f"{ep['title'][:60]}: {outcome}")
                if outcome.startswith("failed"):
                    total_failed += 1
                elif outcome.startswith("permanently-failed"):
                    total_permanent += 1
                save_json(COLLECTED_IDS_FILE, collected)
                continue
            outcome = write_result_to_disk(result, collected)
            print(f"{ep['title'][:60]}: {outcome}")
            if outcome.startswith("ok"):
                total_ok += 1
            elif outcome.startswith("permanently-failed"):
                total_permanent += 1
            elif outcome.startswith("failed"):
                total_failed += 1
            save_json(COLLECTED_IDS_FILE, collected)

    if pool_broken:
        print(
            f"\nStopped early after a broken process pool: {total_ok} ok, {total_failed} failed, "
            f"{remaining_unprocessed} left for the next attempt. Exiting so the wrapper script "
            "restarts with a fresh pool rather than continuing to churn through guaranteed failures."
        )
        return 1

    print(f"\nDone this pass: {len(episodes)} attempted, {total_ok} saved, {total_failed} failed (will retry), {total_permanent} gave up permanently.")
    append_checkpoint_log(CHECKPOINT_LOG_FILE, {
        "attempted": len(episodes), "ok": total_ok, "failed": total_failed, "permanently_failed": total_permanent,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
