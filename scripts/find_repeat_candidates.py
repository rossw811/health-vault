"""Zero-Claude-cost pre-pass (2026-08-20) flagging videos/episodes likely to
cover already-documented claims from the SAME channel/creator.

Ross's explicit refinement on this idea: a flagged item is never skipped -
/process-raw-transcripts and /finish-draft-notes still process it in full -
but the flag lets the agent calibrate effort the same way the vault already
does for its "content-fidelity" discipline (see development.md's 2026-08-17
"Content-fidelity sweep, pass 1" entry): a fast cross-check confirming
already-documented claims still match, with real extraction effort
concentrated on identifying whatever the new item adds that the existing
note(s) don't already have.

Matching is plain keyword/tag overlap (Jaccard over frontmatter `tags:` +
title words), scoped to the SAME channel only - cross-channel overlap is a
different, unrelated citation, not a repeat, and out of scope here.
Deliberately no embeddings/new dependency, same "cheap and local" bar as
find_cross_stream_duplicates.py, which this script's structure mirrors.

Run before a /process-raw-transcripts or /finish-draft-notes batch, same as
find_cross_stream_duplicates.py. Output: Research/.repeat_candidates.json,
keyed by video_id/episode_guid:
  {"likely_repeat_of": "<note path>", "channel": "...",
   "overlap_score": 0.xx, "confidence": "high" | "medium",
   "matched_on": "draft-themes" | "title-only"}
Absence means no same-channel overlap found above the reporting floor -
still worth the agent's own judgment on read, this script only narrows it.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

VAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YT_NOTES = os.path.join(VAULT_ROOT, "Research", "YouTube")
POD_NOTES = os.path.join(VAULT_ROOT, "Research", "Podcasts")
YT_RAW = os.path.join(YT_NOTES, "Raw")
POD_RAW = os.path.join(POD_NOTES, "Raw")
OUT_PATH = os.path.join(VAULT_ROOT, "Research", ".repeat_candidates.json")

# Reporting floor and the high/medium split - deliberately conservative:
# below FLOOR we say nothing (better silent than a noisy false flag), and
# only a strong majority-overlap gets "high" (treat the cross-check as a
# fast formality); "medium" still means genuinely look for what's new, just
# with less certainty that this IS a repeat at all.
FLOOR = 0.25
HIGH = 0.45

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "this", "that", "how", "your", "you", "what", "why", "vs",
    "part", "not", "but", "from", "at", "as", "be", "it", "its", "do",
    "does", "did", "can", "will", "should", "into", "about", "than",
}


def _words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def _frontmatter_field(text: str, field: str) -> str:
    m = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip().strip('"')


def _frontmatter_tags(text: str) -> list[str]:
    m = re.search(r"^tags:\s*\[(.*?)\]", text, re.MULTILINE)
    if not m:
        return []
    return [t.strip() for t in m.group(1).split(",") if t.strip()]


def build_channel_index(notes_dir: str) -> dict[str, list[dict]]:
    """channel (lowercased) -> list of {"path", "title", "words"} for every
    already-written note in this stream's notes folder (not Raw/)."""
    index: dict[str, list[dict]] = {}
    for path in glob.glob(os.path.join(notes_dir, "*.md")):
        try:
            text = open(path, encoding="utf-8", errors="ignore").read(4000)
        except OSError:
            continue
        channel = _frontmatter_field(text, "channel")
        if not channel:
            continue
        title = _frontmatter_field(text, "title")
        words = _words(title) | {w.lower() for w in _frontmatter_tags(text)}
        index.setdefault(channel.lower(), []).append(
            {"path": os.path.relpath(path, VAULT_ROOT), "title": title, "words": words}
        )
    return index


def _parse_raw_header(path: str) -> dict:
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
    return fields


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return {}


def candidate_words(header: dict, draft: dict | None) -> tuple[set[str], str]:
    """Prefer the richer signal (Ollama-drafted themes/key_points) when a
    draft already exists for this item; fall back to title-only words when
    it doesn't (e.g. a /process-raw-transcripts run with no Stage-6-alt
    draft), which is a weaker but still real signal."""
    if draft:
        theme_text = " ".join(draft.get("themes", []) + draft.get("key_points", []))
        words = _words(theme_text)
        if words:
            return words, "draft-themes"
    return _words(header.get("title", "")), "title-only"


def scan_stream(raw_dir: str, id_field: str, notes_index: dict[str, list[dict]], results: dict) -> int:
    processed_state = _load_json(os.path.join(raw_dir, ".processed_ids.json"))
    drafted_state = _load_json(os.path.join(raw_dir, ".drafted_ids.json"))
    drafts_dir = os.path.join(raw_dir, ".drafts")

    scanned = 0
    for path in glob.glob(os.path.join(raw_dir, "*_full.txt")):
        header = _parse_raw_header(path)
        item_id = header.get(id_field)
        if not item_id or item_id in processed_state:
            continue  # already has a real note - no longer a "candidate to process"
        channel = (header.get("channel") or "").lower()
        same_channel_notes = notes_index.get(channel)
        if not same_channel_notes:
            continue

        draft = None
        if item_id in drafted_state:
            draft_path = os.path.join(raw_dir, ".drafts", f"{item_id}.json")
            draft = _load_json(draft_path) if os.path.exists(draft_path) else None

        words, matched_on = candidate_words(header, draft)
        if not words:
            continue
        scanned += 1

        best = None
        for note in same_channel_notes:
            other = note["words"]
            if not other:
                continue
            union = words | other
            if not union:
                continue
            score = len(words & other) / len(union)
            if best is None or score > best[0]:
                best = (score, note)

        if best is None or best[0] < FLOOR:
            continue
        score, note = best
        results[item_id] = {
            "likely_repeat_of": note["path"],
            "channel": header.get("channel", ""),
            "overlap_score": round(score, 3),
            "confidence": "high" if score >= HIGH else "medium",
            "matched_on": matched_on,
        }
    return scanned


def main() -> int:
    yt_index = build_channel_index(YT_NOTES)
    pod_index = build_channel_index(POD_NOTES)

    results: dict = {}
    yt_scanned = scan_stream(YT_RAW, "video_id", yt_index, results)
    pod_scanned = scan_stream(POD_RAW, "episode_guid", pod_index, results)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_note": "regenerate before each batch, do not trust a stale copy",
                "note": "a flagged item is never skipped - process fully, calibrate effort only",
                "youtube_candidates_scanned": yt_scanned,
                "podcast_candidates_scanned": pod_scanned,
                "candidates": results,
            },
            f,
            indent=2,
        )

    high = sum(1 for v in results.values() if v["confidence"] == "high")
    medium = sum(1 for v in results.values() if v["confidence"] == "medium")
    print(f"Scanned {yt_scanned} unprocessed YouTube + {pod_scanned} unprocessed podcast candidates with a same-channel note pool.")
    print(f"Flagged {len(results)} likely-repeat candidate(s): {high} high-overlap, {medium} medium-overlap.")
    print(f"Written to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
