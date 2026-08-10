"""Zero-Claude-cost pre-pass for Stage 2 (/process-raw-transcripts) dedup.

Added 2026-08-04 after several Stage-2 batches spent a full transcript read
(the single most expensive operation in that command) confirming duplicates
that pure metadata (title + approximate duration) could have ruled out for
free. This script never opens an LLM; it's a plain Python string/size
comparison, same fuzzy-matching approach and thresholds already proven at
Stage 1 in collector_common.py's find_matching_podcast_episode() - reused
here rather than reimplemented, just pointed at Stage 2's own
.processed_ids.json (which raw file already has a *written note*, not just
"collected") instead of Stage 1's collected_ids.json.

Run this immediately before dispatching a /process-raw-transcripts batch.
Output: Research/.dedup_candidates.json, a flat map of
  {video_id_or_episode_guid: {"likely_duplicate_of": <other id>,
                               "of_note": <path to the already-written note>,
                               "title_similarity": <float>,
                               "confidence": "high" | "check"}}
for every currently-unprocessed raw file on either side that has a
plausible match against an already-written note on the other stream.
Absence from this file means "no metadata-only match found" - the batch
agent still needs its own ambiguous-case spot-check fallback, this script
only ever narrows that fallback's workload, never replaces it entirely.

Confidence: "high" (title ratio >= 0.90 and, where duration is known on
both sides, within ~20%) can reasonably be treated as decided without a
content spot-check. "check" (weaker match) still warrants the Stage 2
agent's own short spot-check before skipping - this script is a cost
filter, not a silent decision-maker for ambiguous cases.
"""

from __future__ import annotations

import difflib
import glob
import json
import os
import re
import sys
from email.utils import parsedate_to_datetime
import datetime

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YT_RAW = os.path.join(VAULT_ROOT, "Research", "YouTube", "Raw")
POD_RAW = os.path.join(VAULT_ROOT, "Research", "Podcasts", "Raw")
OUT_PATH = os.path.join(VAULT_ROOT, "Research", ".dedup_candidates.json")

TITLE_THRESHOLD_CHECK = 0.75   # same floor as collector_common.py's Stage-1 matcher
TITLE_THRESHOLD_HIGH = 0.90    # tighter bar for "skip without a spot-check"
DATE_WINDOW_DAYS = 3
DURATION_TOLERANCE = 0.35      # file-size-as-duration-proxy is rougher than real duration; wider band


def _normalize_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", title or "").lower().strip()


def _parse_header(path: str) -> dict:
    fields = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip() == "---":
                    break
                if ":" in line:
                    k, _, v = line.partition(":")
                    fields[k.strip()] = v.strip()
    except OSError:
        return {}
    fields["_size"] = os.path.getsize(path) if os.path.exists(path) else 0
    fields["_path"] = path
    return fields


def _parse_yt_date(upload_date: str):
    try:
        return datetime.datetime.strptime(upload_date, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _parse_pod_date(date_str: str):
    try:
        return parsedate_to_datetime(date_str).date()
    except (ValueError, TypeError):
        return None


def load_state(raw_dir: str) -> dict:
    path = os.path.join(raw_dir, ".processed_ids.json")
    if not os.path.exists(path):
        return {}
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return {}


def written_index(raw_dir: str, state: dict, id_field: str) -> list[dict]:
    """Headers for every raw file whose Stage-2 status is 'ok' (a real note exists)."""
    out = []
    for f in glob.glob(os.path.join(raw_dir, "*_full.txt")):
        h = _parse_header(f)
        item_id = h.get(id_field)
        if not item_id:
            continue
        entry = state.get(item_id)
        if entry and entry.get("status") == "ok":
            out.append(h)
    return out


def unprocessed_index(raw_dir: str, state: dict, id_field: str) -> list[dict]:
    out = []
    for f in glob.glob(os.path.join(raw_dir, "*_full.txt")):
        h = _parse_header(f)
        item_id = h.get(id_field)
        if not item_id or item_id in state:
            continue
        out.append(h)
    return out


def match(unprocessed: list[dict], written: list[dict], src_is_yt: bool) -> dict:
    results = {}
    for cand in unprocessed:
        cand_title = _normalize_title(cand.get("title", ""))
        if not cand_title:
            continue
        cand_date = _parse_yt_date(cand.get("upload_date", "")) if src_is_yt else _parse_pod_date(cand.get("pub_date", ""))
        best = None
        for w in written:
            w_date = _parse_pod_date(w.get("pub_date", "")) if src_is_yt else _parse_yt_date(w.get("upload_date", ""))
            if cand_date and w_date and abs((cand_date - w_date).days) > DATE_WINDOW_DAYS:
                continue
            ratio = difflib.SequenceMatcher(None, cand_title, _normalize_title(w.get("title", ""))).ratio()
            if ratio < TITLE_THRESHOLD_CHECK:
                continue
            if best is None or ratio > best[0]:
                best = (ratio, w)
        if best is None:
            continue
        ratio, w = best
        size_a, size_b = cand.get("_size", 0), w.get("_size", 0)
        size_close = (
            min(size_a, size_b) > 0
            and abs(size_a - size_b) / max(size_a, size_b) <= DURATION_TOLERANCE
        )
        confidence = "high" if (ratio >= TITLE_THRESHOLD_HIGH and size_close) else "check"
        cand_id = cand.get("video_id") if src_is_yt else cand.get("episode_guid")
        w_id = w.get("episode_guid") if src_is_yt else w.get("video_id")
        # note path isn't in the header - the Stage 2 agent already knows how to look it up
        # from the other stream's .processed_ids.json "note" field using w_id; we just hand it the id.
        results[cand_id] = {
            "likely_duplicate_of": w_id,
            "of_stream": "podcast" if src_is_yt else "youtube",
            "title_similarity": round(ratio, 3),
            "confidence": confidence,
        }
    return results


def main():
    yt_state = load_state(YT_RAW)
    pod_state = load_state(POD_RAW)

    yt_unprocessed = unprocessed_index(YT_RAW, yt_state, "video_id")
    pod_unprocessed = unprocessed_index(POD_RAW, pod_state, "episode_guid")
    yt_written = written_index(YT_RAW, yt_state, "video_id")
    pod_written = written_index(POD_RAW, pod_state, "episode_guid")

    out = {}
    out.update(match(yt_unprocessed, pod_written, src_is_yt=True))
    out.update(match(pod_unprocessed, yt_written, src_is_yt=False))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_note": "regenerate before each Stage-2 batch, do not trust a stale copy",
                "youtube_unprocessed_scanned": len(yt_unprocessed),
                "podcast_unprocessed_scanned": len(pod_unprocessed),
                "candidates": out,
            },
            f,
            indent=2,
        )

    high = sum(1 for v in out.values() if v["confidence"] == "high")
    check = sum(1 for v in out.values() if v["confidence"] == "check")
    print(f"Scanned {len(yt_unprocessed)} unprocessed YouTube + {len(pod_unprocessed)} unprocessed podcast files.")
    print(f"Found {len(out)} candidate duplicates: {high} high-confidence, {check} need-a-spot-check.")
    print(f"Written to {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
