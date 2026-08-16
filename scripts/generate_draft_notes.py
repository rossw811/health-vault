"""Local-LLM assisted-draft pipeline (Phase 6-alt), added 2026-08-15 as part of
the two-machine migration (see NEW-MACHINE-SETUP.md).

Runs on CachyOS only (needs Ollama + the RTX 4080). Per the real Phase 5 A/B
validation against 9 already-Claude-processed videos (2026-08-15): qwen2.5:14b
only matched Claude's own signal-density judgment on 3/9 videos (33%, and
systematically biased toward over-rating density, not random noise), and only
13/26 (50%) of its claimed-verbatim quotes were actually exact substrings of
the source transcript. That fails the bar for unsupervised note-writing (see
the Phase 5/6 decision gate in the migration plan) - so this script does NOT
write finished notes. It writes lower-trust structured DRAFTS that a Claude
Code batch reads instead of the full raw transcript to finish the real note -
meaningfully less context per file, real efficiency gain, without pretending
the local model's output is trustworthy unsupervised.

The one thing this script does NOT compromise on: every candidate quote is
programmatically verified as an exact (whitespace-normalized) substring of
the actual transcript before it's allowed into a draft. A quote that fails
verification is dropped, never forwarded. This is the concrete anti-
fabrication safeguard the Phase 5 numbers showed is genuinely load-bearing,
not optional scaffolding - the model's own 50% verbatim rate makes it clear
this can't be skipped.

Usage:
    python scripts/generate_draft_notes.py youtube [--batch-size 20]
    python scripts/generate_draft_notes.py podcast [--batch-size 20]
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent

TARGETS = {
    "youtube": {
        "raw_dir": VAULT_ROOT / "Research" / "YouTube" / "Raw",
    },
    "podcast": {
        "raw_dir": VAULT_ROOT / "Research" / "Podcasts" / "Raw",
    },
}

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:14b"
# Real context need: multi-hour Huberman/Attia episodes can run 30-40K+
# tokens (see the migration plan's Phase 4 note). 16384 is a practical
# middle ground given this model's 9.5GB weight footprint already uses most
# of the 4080's 16GB VRAM - a much larger context multiplies KV-cache memory
# fast. Transcripts longer than this get truncated (see TRANSCRIPT_CHAR_CAP)
# rather than silently failing or OOMing.
NUM_CTX = 16384
TRANSCRIPT_CHAR_CAP = 60000  # ~roughly matches NUM_CTX after prompt overhead


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def extract_video_id(filename: str) -> str | None:
    m = re.search(r"\[([\w-]+)\]_full\.txt$", filename)
    return m.group(1) if m else None


def query_ollama(transcript: str, title: str) -> dict:
    prompt = f"""You are analyzing a transcript titled "{title}" for a personal health/fitness/mental-health research vault. Respond ONLY with valid JSON, no other text, no markdown fences.

Transcript:
{transcript[:TRANSCRIPT_CHAR_CAP]}

Return JSON with this exact structure:
{{
  "relevant": true or false (is this genuinely about health, fitness/performance, or mental health? Off-topic content like gaming, unrelated vlogging, etc. is false),
  "signal_density": "high" or "mixed" or "low" (ratio of substantive/citable content to total runtime),
  "themes": [list of 2-5 short topic/theme tags],
  "key_points": [list of 3-6 substantive points, EXCLUDING any sponsor/ad/promotional content],
  "notable_quotes": [list of 2-5 candidate EXACT verbatim quotes copied character-for-character from the transcript above - never paraphrase, these will be independently verified]
}}"""

    data = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": NUM_CTX},
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    return json.loads(result["response"])


def verify_and_filter_quotes(quotes: list, transcript: str) -> tuple[list[str], int]:
    """The real anti-fabrication gate. A quote that isn't a genuine substring
    of the source (after whitespace normalization) is dropped entirely, not
    forwarded with a warning label - per the Phase 5 finding, roughly half of
    this model's claimed-verbatim quotes fail this check, so silently
    trusting them is not an option."""
    normalized_source = " ".join(transcript.split())
    verified = []
    dropped = 0
    for q in quotes:
        normalized_q = " ".join(str(q).split())
        if normalized_q and normalized_q in normalized_source:
            verified.append(str(q))
        else:
            dropped += 1
    return verified, dropped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["youtube", "podcast"])
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()

    cfg = TARGETS[args.target]
    raw_dir = cfg["raw_dir"]
    processed_ids_file = raw_dir / ".processed_ids.json"
    drafted_ids_file = raw_dir / ".drafted_ids.json"
    drafts_dir = raw_dir / ".drafts"

    processed = read_json(processed_ids_file)
    drafted = read_json(drafted_ids_file)

    candidates = []
    for f in raw_dir.glob("*_full.txt"):
        vid = extract_video_id(f.name)
        if not vid:
            continue
        if vid in processed:
            continue  # already has a real Claude-written note, no draft needed
        if vid in drafted:
            continue  # already drafted
        candidates.append((vid, f))

    candidates = candidates[: args.batch_size]
    print(f"{len(candidates)} file(s) to draft this run (target={args.target})")

    total_quotes_offered = 0
    total_quotes_verified = 0

    for i, (vid, raw_file) in enumerate(candidates, 1):
        transcript = raw_file.read_text(encoding="utf-8", errors="ignore")
        title = raw_file.stem
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            result = query_ollama(transcript, title)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"{timestamp} [{i}/{len(candidates)}] {vid}: FAILED ({exc})")
            continue

        quotes_raw = result.get("notable_quotes", [])
        quotes_verified, dropped = verify_and_filter_quotes(quotes_raw, transcript)
        total_quotes_offered += len(quotes_raw)
        total_quotes_verified += len(quotes_verified)

        draft = {
            "video_id": vid,
            "source_file": raw_file.name,
            "title": title,
            "generated_at": timestamp,
            "model": MODEL,
            "relevant": result.get("relevant"),
            "signal_density_guess": result.get("signal_density"),
            "signal_density_confirmed": False,  # unconfirmed per the migration plan's design - Claude confirms during finishing
            "themes": result.get("themes", []),
            "key_points": result.get("key_points", []),
            "notable_quotes_verified": quotes_verified,
            "notable_quotes_dropped_count": dropped,
        }

        write_json_atomic(drafts_dir / f"{vid}.json", draft)
        drafted[vid] = {"status": "drafted", "draft_file": f".drafts/{vid}.json", "generated_at": timestamp}
        write_json_atomic(drafted_ids_file, drafted)  # checkpoint after every file, same discipline as the collectors

        print(f"{timestamp} [{i}/{len(candidates)}] {vid}: drafted "
              f"(relevant={draft['relevant']}, density={draft['signal_density_guess']}, "
              f"quotes {len(quotes_verified)}/{len(quotes_raw)} verified)")

    if candidates:
        print(f"\nQuote verification rate this run: {total_quotes_verified}/{total_quotes_offered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
