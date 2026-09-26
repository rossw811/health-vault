"""Shared checkpoint/retry logic for this vault's raw-content collectors
(YouTube: collect_raw_transcripts.py, podcasts: podcast_collector.py, and any
future collector). Factored out 2026-07-25 after two real, separate problems
in collect_raw_transcripts.py that any collector following the same pattern
would eventually hit too:

1. A failed video was permanently excluded from retry forever (the dedup
   check only looked at "is this video_id in the state file at all", not
   "did it actually succeed") - so a transient failure (network hiccup, a
   bug since fixed) stayed failed permanently unless someone manually edited
   the state file. Real incident: 43 videos stuck failed with a stale error
   message from before a same-day bug fix, discovered only by manually
   grepping error text.
2. No way to tell whether a failure happened under old, since-fixed
   collector code vs. current code - PIPELINE_VERSION exists so a version
   bump automatically makes every existing failure eligible for an immediate
   retry (bypassing backoff), instead of requiring a manual state-file audit
   each time a real bug gets fixed.
"""

from __future__ import annotations

import datetime
import difflib
import json
import re
from email.utils import parsedate_to_datetime
from pathlib import Path

# Bump this whenever a fix changes collection behavior in a way that could
# turn a past failure into a future success (env/dependency fixes, retry
# logic changes, etc.) - NOT for unrelated changes (e.g. adding a new
# platform). Every failed entry with an older version becomes immediately
# retry-eligible, regardless of backoff timing.
PIPELINE_VERSION = 4  # 2026-07-26: three real fixes bundled into this bump - (1) priority-section
# queue ordering actually respected now (extract_urls_from_queue/extract_feed_urls_from_queue),
# (2) BrokenExecutor detected and stopped early instead of burning thousands of guaranteed
# failures through a dead process pool, (3) yt-dlp's Whisper-fallback audio download fixed
# (--js-runtimes node) after a yt-dlp update broke it for every video with "No supported
# JavaScript runtime could be found." All 426 Huberman videos and ~14,947 broken-pool-era
# entries were stuck in backoff with zero real chance of succeeding under the old code -
# this bump makes them retry-eligible immediately rather than waiting out 1-30 day windows.
# Was 3 before this bump: 2026-07-25 (later) worker count reduced 4->2 + stop-collectors.ps1.

MAX_RETRIES = 5
RETRY_BACKOFF_DAYS = [1, 3, 7, 14, 30]  # index by retry_count, clamped to last entry


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def is_eligible_for_retry(entry: dict) -> bool:
    """A 'failed' entry is worth retrying if the pipeline has changed since
    its last attempt (version bump - always eligible, bypasses backoff), or
    if its backoff window has elapsed and it hasn't exhausted MAX_RETRIES."""
    if entry.get("status") != "failed":
        return False  # "ok", "qc-failed", and "permanently-failed" are never auto-retried

    if entry.get("pipeline_version", 0) < PIPELINE_VERSION:
        return True

    retry_count = entry.get("retry_count", 0)
    if retry_count >= MAX_RETRIES:
        return False

    last_attempt = entry.get("last_attempt_at")
    if not last_attempt:
        return True  # no timestamp recorded (pre-checkpoint-system entry) - eligible now

    try:
        last_dt = datetime.datetime.fromisoformat(last_attempt)
    except ValueError:
        return True  # unparseable timestamp - don't let a bad value block retry forever

    backoff_days = RETRY_BACKOFF_DAYS[min(retry_count, len(RETRY_BACKOFF_DAYS) - 1)]
    return datetime.datetime.now() >= last_dt + datetime.timedelta(days=backoff_days)


def record_result(collected: dict, item_id: str, status: str, reason: str = "", title: str = "", extra: dict | None = None) -> None:
    """Update collected[item_id] for this attempt, tracking retry_count/
    last_attempt_at/pipeline_version. Call this instead of writing to
    `collected` directly so retry bookkeeping never gets skipped by accident.
    `status` should be "ok", "failed", or "qc-failed" - permanently-failed
    demotion (after MAX_RETRIES) happens here automatically."""
    prior = collected.get(item_id, {})
    retry_count = prior.get("retry_count", 0)

    if status == "failed":
        retry_count += 1
        if retry_count >= MAX_RETRIES:
            status = "permanently-failed"

    entry = {
        "status": status,
        "title": title,
        "reason": reason,
        "retry_count": retry_count,
        "last_attempt_at": now_iso(),
        "pipeline_version": PIPELINE_VERSION,
        "first_failed_at": prior.get("first_failed_at") or (now_iso() if status in ("failed", "permanently-failed") else None),
    }
    if extra:
        entry.update(extra)
    collected[item_id] = entry


def retry_eligible_ids(collected: dict) -> list[str]:
    """Every currently-failed item_id worth retrying this run."""
    return [item_id for item_id, entry in collected.items() if is_eligible_for_retry(entry)]


def append_checkpoint_log(log_path, summary: dict) -> None:
    """Append one JSON line per run to a persistent, human-inspectable log -
    distinct from the per-item state file, so run-over-run progress/health is
    visible without diffing a potentially huge JSON blob."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {"timestamp": now_iso(), "pipeline_version": PIPELINE_VERSION, **summary}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")


# --- Cross-collector dedup (2026-07-25) ------------------------------------
# RSS-based podcast collection is faster and more reliable than the YouTube
# path for the same underlying episode content (no anti-bot/IP-block fighting,
# no failed-captions-attempt-first overhead - straight to a direct audio
# download). Where a creator's podcast already covers an episode, the YouTube
# collector should skip re-transcribing it rather than doing the same work
# twice. Matching is fuzzy (title similarity + a date window) since the same
# episode's title/publish-date routinely differs slightly between platforms.


def _normalize_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", title or "").lower().strip()


def _parse_youtube_upload_date(upload_date: str):
    """yt-dlp's upload_date is YYYYMMDD."""
    try:
        return datetime.datetime.strptime(upload_date, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _parse_rfc2822_date(date_str: str):
    """Podcast RSS pubDate is RFC 2822 (e.g. 'Thu, 23 Jul 2026 08:00:00 -0000')."""
    try:
        return parsedate_to_datetime(date_str).date()
    except (ValueError, TypeError):
        return None


def load_podcast_title_index(podcast_state_file: Path) -> list[tuple[str, str]]:
    """Read-only cross-reference into the podcast collector's own state file -
    only that collector's process ever writes it, so this is a safe read from
    the YouTube collector's side. Returns (title, pub_date) for every
    successfully-collected episode."""
    if not podcast_state_file.exists():
        return []
    try:
        data = json.loads(podcast_state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        (entry.get("title", ""), entry.get("pub_date", ""))
        for entry in data.values()
        if entry.get("status") == "ok"
    ]


def find_matching_podcast_episode(
    yt_title: str, yt_upload_date: str, podcast_index: list[tuple[str, str]],
    title_threshold: float = 0.75, date_window_days: int = 3,
) -> str | None:
    """Returns the matching podcast episode title if this YouTube video is
    very likely the same content as an already-collected podcast episode,
    else None. Requires BOTH a close title match AND a close date match -
    title similarity alone risks false positives on generic titles
    ("Q&A", "Live Episode"), date alone obviously isn't enough on its own."""
    yt_date = _parse_youtube_upload_date(yt_upload_date)
    norm_yt_title = _normalize_title(yt_title)
    if not norm_yt_title:
        return None

    for pod_title, pod_pub_date in podcast_index:
        pod_date = _parse_rfc2822_date(pod_pub_date)
        if yt_date and pod_date and abs((yt_date - pod_date).days) > date_window_days:
            continue
        ratio = difflib.SequenceMatcher(None, norm_yt_title, _normalize_title(pod_title)).ratio()
        if ratio >= title_threshold:
            return pod_title
    return None


# --- Conservative, zero-meaning-risk filler stripping (2026-08-20) ---------
# Ross-approved idea #2 from the 2026-08-20 assisted-draft-pipeline session:
# a deterministic (no LLM) pre-processing pass that trims genuinely
# zero-information text BEFORE a transcript reaches either the local Ollama
# draft generator or Claude's own reading, so both save tokens on the same
# pass. Deliberately narrow scope - only three patterns, each individually
# incapable of altering meaning or removing something a future note might
# need to quote:
#   1. Exact-repeated whole-word stutters, 3+ consecutive occurrences only
#      ("I I I think" -> "I think", "the the the plan" -> "the plan"). A
#      2x repeat ("no no", "yes yes") is left untouched - that's frequently
#      deliberate emphasis a quote might legitimately want to preserve, and
#      only a genuine 3+ run is unambiguous transcription-artifact stutter.
#   2. Standalone filler tokens ("um", "uh", "uhh", "uhm", "erm") matched as
#      a whole word only - never a word merely containing one of these as a
#      substring.
#   3. An exact-duplicate consecutive sentence (verbatim repeat only, never
#      a paraphrase or a partial repeat) - the second copy is dropped, the
#      first is kept untouched.
# This NEVER runs on or replaces the raw file on disk - raw transcripts stay
# immutable per this vault's own rule. Callers write the *stripped* text to
# a separate derived file/string; the original is always still there,
# untouched, for anything that needs to fall back to it (e.g. the
# anti-fabrication quote-verification gate, which always checks a candidate
# quote against the real untouched transcript, never the stripped copy).

_STUTTER_RE = re.compile(r"\b(\w+)(?:\s+\1\b){2,}", re.IGNORECASE)
_FILLER_TOKEN_RE = re.compile(r"(?<!\w)(um+|uhh*|uhm+|erm+)(?!\w)[,]?\s*", re.IGNORECASE)


def strip_filler_text(text: str) -> tuple[str, int]:
    """Returns (stripped_text, chars_removed). Pure function, no I/O - callers
    decide where the result gets written (never overwriting the original)."""
    if not text:
        return text, 0
    original_len = len(text)
    out = text

    # 1. Exact whole-word stutters, 3+ consecutive repeats only.
    out = _STUTTER_RE.sub(lambda m: m.group(1), out)

    # 2. Standalone filler tokens ("um", "uh", "uhm", "erm").
    out = _FILLER_TOKEN_RE.sub("", out)

    # 3. Exact-duplicate consecutive sentences (verbatim only).
    # Split while keeping the delimiter so rejoining doesn't lose punctuation.
    parts = re.split(r"(?<=[.!?])\s+", out)
    deduped = []
    prev_norm = None
    for sentence in parts:
        norm = " ".join(sentence.split())
        if norm and norm == prev_norm:
            continue  # exact verbatim repeat of the immediately preceding sentence
        deduped.append(sentence)
        prev_norm = norm
    out = " ".join(deduped)

    # Cleanup: the two removals above can leave stray double-spaces or a
    # dangling space before punctuation - fix those artifacts only, nothing
    # that touches actual words.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.!?])", r"\1", out)

    return out, original_len - len(out)
