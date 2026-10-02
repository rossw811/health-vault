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

**Extended 2026-08-20** with four Ross-approved efficiency ideas, none of
which relax the anti-fabrication bar above:
  1. **Structural pre-mapping** (`structure_map`) - the transcript is
     pre-divided into a few numbered segments (real char offsets computed
     in Python, never invented by the model) and the model classifies each
     as substantive/filler/sponsor/tangent - a rough reading-effort hint,
     `structure_map_confirmed: false` until Claude checks it, same pattern
     as `signal_density_guess`/`signal_density_confirmed`.
  2. **Conservative filler stripping** (`collector_common.strip_filler_text`)
     - a deterministic, zero-meaning-risk pass (exact 3+ word stutters,
     standalone "um"/"uh"-type tokens, exact-duplicate consecutive
     sentences) applied to the transcript BODY before it reaches Ollama.
     The result is written to a separate derived file (`.lite/<id>_lite.txt`)
     - the raw file on disk is never modified - and quote verification
     always re-checks against the untouched original body, never the
     stripped copy.
  3. **Cross-video repeat detection** lives in a separate zero-cost script,
     `scripts/find_repeat_candidates.py`, run by the finishing commands
     (`/process-raw-transcripts`, `/finish-draft-notes`) as a batch
     pre-pass, not by this script - see that script's own docstring.
  4. **Junk-filter confidence** - `relevant_confidence` (the model's own
     confidence in its `relevant` judgment) plus `known_low_value_pattern`/
     `low_value_pattern_reasons` (deterministic, NOT from the model - real
     evidence-based patterns from this vault's own history, see
     `detect_low_value_pattern()`).

Usage:
    python scripts/generate_draft_notes.py youtube [--batch-size 20]
    python scripts/generate_draft_notes.py podcast [--batch-size 20]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collector_common import strip_filler_text
from tag_low_value_notes import LOW_VALUE_CHANNELS  # reuse the one real, evidence-based list - never re-derive it

VAULT_ROOT = Path(__file__).resolve().parent.parent

TARGETS = {
    "youtube": {
        "raw_dir": VAULT_ROOT / "Research" / "YouTube" / "Raw",
    },
    "podcast": {
        "raw_dir": VAULT_ROOT / "Research" / "Podcasts" / "Raw",
    },
}

# Same 7 channels as collect_raw_transcripts.py's IMMEDIATE PRIORITY section
# (YouTube Queue.md) - kept as a literal list here rather than re-parsing the
# queue file, since this script only needs channel-name matching, not URLs.
PRIORITY_CHANNELS = (
    "Ben Winney", "Huberman", "VigorousSteve", "Nick Norwitz",
    "Peter Attia", "Renaissance Periodization", "Bryan Johnson",
)

# OLLAMA_HOST (set by the systemd units) points at the boot-safe GPU server
# healthvault-ollama-gpu.service on :11435 - see that unit for why (2026-10-01).
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/generate"
MODEL = "qwen2.5:14b"
# Real context need: multi-hour Huberman/Attia episodes can run 30-40K+
# tokens (see the migration plan's Phase 4 note). 16384 is a practical
# middle ground given this model's 9.5GB weight footprint already uses most
# of the 4080's 16GB VRAM - a much larger context multiplies KV-cache memory
# fast. Transcripts longer than TRANSCRIPT_CHAR_CAP are now CHUNKED (see
# query_ollama_chunked, fixed 2026-09-25 after a real audit found 27.7% of
# the podcast backlog - and 4.1% of YouTube - was silently getting a
# truncated single call, meaning content past ~120K chars was never shown
# to the model at all for those files) rather than truncated to a single
# call or silently failing/OOMing.
# Tiered context, added 2026-08-21 after checking the REAL transcript-length
# distribution across all 3,510 raw files on disk: median is ~8.7K chars (~2.2K
# tokens), p90 is ~52K chars (~13K tokens), p95 jumps to ~127K chars (~32K
# tokens). A single fixed NUM_CTX=32768 for every file (the prior approach)
# pre-allocates the SAME large KV-cache footprint even for the median 2K-token
# file - correct for the long tail, wasteful for the other ~90%. Real Ollama
# behavior confirmed live: model weights (~9GB) are loaded once; VRAM scales
# with the requested num_ctx per-request via KV cache. Two fixed tiers, not a
# continuous per-file value, deliberately - alternating context sizes on
# every single request risks the runner reloading/reallocating between
# requests, which would cost more than it saves; two tiers means the SMALL
# tier's candidates get grouped and run together (same context, no thrash).
NUM_CTX_SMALL = 16384  # covers p90 (~13K tokens) with real margin
NUM_CTX_LARGE = 32768  # qwen2.5:14b's real max (confirmed via `ollama show`), for the
                        # genuine long tail (multi-hour Attia/Huberman-style episodes)
NUM_CTX_THRESHOLD_CHARS = 60000  # ~90th percentile cutoff - puts roughly the top 10%
                                  # of files (by real measured length) into the LARGE tier
TRANSCRIPT_CHAR_CAP = 120000  # matches NUM_CTX_LARGE after prompt overhead - the ceiling
                               # for the minority of files that need it


def choose_num_ctx(transcript_char_len: int) -> int:
    return NUM_CTX_LARGE if transcript_char_len > NUM_CTX_THRESHOLD_CHARS else NUM_CTX_SMALL
MAX_QUOTES_MERGED = 12  # cap on pooled notable_quotes across chunks - verification still filters, this just bounds prompt/draft size
MAX_KEY_POINTS_MERGED = 10
MAX_THEMES_MERGED = 8
# Real incident (see development.md, 2026-08-20 CachyOS session): an earlier
# prompt change that added fields without a generation length cap let one
# response run past 3,400 tokens and blow through the whole 16K context
# window mid-generation. num_predict is the hard backstop - bumped slightly
# from that incident's 3072 fix to 3584 to leave room for the structure_map
# field added below, but every list in the schema is still explicitly capped
# so this ceiling should rarely if ever actually get hit.
NUM_PREDICT = 3584
# Real finding, 2026-08-21 (two consecutive real ground-truth tests): a FIXED 6-segment
# count meant a 2h38m interview got ~25,000-char segments - even an 800-char preview only
# samples ~3% of a segment that size, and structure_map still labeled the whole thing
# "substantive" on real adversarial testing while the model's own separate holistic guess
# correctly caught it as "mixed". Fix: scale segment count with transcript length instead
# of a flat value, so long videos get more, smaller, better-sampled segments - this also
# gives long videos a genuinely finer-grained map, not just a better-sampled coarse one.
STRUCTURE_MAP_SEGMENTS_MIN = 6   # unchanged floor for short/typical videos - no regression there
STRUCTURE_MAP_SEGMENTS_MAX = 16  # ceiling - keeps prompt size/segment-preview cost bounded
STRUCTURE_MAP_CHARS_PER_SEGMENT = 8000  # target segment size a preview can meaningfully sample

# Junk-filter title patterns (2026-08-20, idea #4) - real, evidence-based
# patterns this vault has already confirmed low-value by direct sampling
# (see tag_low_value_notes.py's own docstring and development.md's
# 2026-08-08/09 Concepts-catchup entries), not guessed from a channel name
# alone. This is a HINT that boosts confidence for the finishing pass's
# relevance/signal-density confirmation - never a hard skip; every flagged
# video still gets a real (just faster) confirmation pass, per CLAUDE.md's
# non-negotiable anti-fabrication/no-hard-skip constraint.
_LIFT_LOG_TITLE_RE = re.compile(r"\b\d+\s*(lbs?|kg)\s+for\s+\d+\s+reps?\b", re.IGNORECASE)
_ADMIN_TITLE_RE = re.compile(r"\b(giveaway|announcement)\b", re.IGNORECASE)
# Real finding, 2026-08-21 test batch: a "life update"/"wrapup" vlog sub-genre
# (a real ~100-min "Olympia Wrapup" and ~75-min "Life Updates" video, both
# genuinely low-density, lifestyle/networking chatter, incorrectly labeled
# high-substantive by structure_map before the segment-preview fix) is a
# real, repeatable trap this pattern list didn't catch. Not channel-specific -
# this vlog-title shape shows up across creators, so it's a title pattern,
# not added to LOW_VALUE_CHANNELS.
_VLOG_UPDATE_TITLE_RE = re.compile(r"\b(life\s*update|wrap\s*up|vlog|day\s+in\s+(the\s+)?life)\b", re.IGNORECASE)
# Deliberately NOT including "Q&A" here - that's a real, substantive-content
# format on many channels, not evidenced as low-value by the actual finding
# above; adding it would risk false-positiving genuinely good content.


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


def parse_header_fields(raw_text: str) -> dict:
    """Raw files are `header\\n---\\n\\n<transcript>` (see
    collect_raw_transcripts.py/podcast_collector.py). Pulls the clean
    metadata fields (title, channel) out of that header rather than relying
    on the filename stem, which still carries the bracketed video ID and
    trailing "_full" - needed for accurate low-value-pattern matching below."""
    fields = {}
    for line in raw_text.split("\n", 30)[:30]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields


def split_header_body(raw_text: str) -> tuple[str, str]:
    """Separates the metadata header from the actual transcript body so
    filler-stripping/segmentation/the Ollama prompt only ever operate on
    real transcript content, never on metadata lines - both collectors write
    `header\\n---\\n\\n<transcript>` (see collect_raw_transcripts.py /
    podcast_collector.py), so the header block always ends at the first
    line that is exactly '---'. Falls back to treating the whole file as
    body if that marker is somehow missing (defensive, should not happen
    against files these collectors actually wrote)."""
    m = re.match(r"(.*?\n---\n\n?)", raw_text, re.DOTALL)
    if not m:
        return "", raw_text
    return m.group(1), raw_text[m.end():]


def build_segments(text: str, n: int | None = None) -> list[tuple[int, int]]:
    """Split text into n roughly-equal contiguous (start, end) char-offset
    ranges. Offsets are computed here in Python, not invented by the model -
    an LLM asked to produce its own character offsets is unreliable; asking
    it only to classify pre-defined, numbered segments (given a preview of
    each) is a much safer division of labor.

    n scales with transcript length (real fix, 2026-08-21) rather than being
    a flat value - see STRUCTURE_MAP_SEGMENTS_MIN/MAX/CHARS_PER_SEGMENT above
    for why a fixed count failed on long-form content."""
    length = len(text)
    if length == 0:
        return []
    if n is None:
        n = max(STRUCTURE_MAP_SEGMENTS_MIN,
                min(STRUCTURE_MAP_SEGMENTS_MAX, length // STRUCTURE_MAP_CHARS_PER_SEGMENT))
    seg_len = max(1, length // n)
    segments = []
    start = 0
    for i in range(n):
        end = length if i == n - 1 else min(length, start + seg_len)
        if start >= length:
            break
        segments.append((start, end))
        start = end
    return segments


def _segment_previews(text: str, segments: list[tuple[int, int]]) -> str:
    lines = []
    for i, (s, e) in enumerate(segments, 1):
        # Real fix, 2026-08-21, second pass: a flat 800-char preview was a real
        # improvement over the original 180 (proven via A/B test) but still wasn't
        # enough once segment count also scaled up (see build_segments) - with
        # dynamic segment sizing now targeting ~8000 chars/segment, a preview
        # proportional to actual segment size (bounded so it can't balloon on an
        # unusually large final segment, or vanish on a short one) gives real,
        # consistent ~1/8th coverage instead of a fixed absolute amount that meant
        # wildly different coverage percentages depending on how long the video was.
        seg_len = e - s
        preview_len = min(2000, max(800, seg_len // 8))
        preview = " ".join(text[s:min(e, s + preview_len)].split())
        lines.append(f"Segment {i} (chars {s}-{e}): \"{preview}...\"")
    return "\n".join(lines)


def query_ollama(transcript: str, title: str, num_ctx: int) -> dict:
    """Single-call path for a transcript slice that already fits within
    TRANSCRIPT_CHAR_CAP. Never called directly on a full transcript longer
    than that anymore - see query_ollama_chunked, which slices first and
    calls this once per chunk with a chunk_offset for global segment
    coordinates."""
    return _query_ollama_call(transcript, title, num_ctx, chunk_offset=0)


def _query_ollama_call(chunk_text: str, title: str, num_ctx: int, chunk_offset: int) -> dict:
    segments = build_segments(chunk_text)
    segment_previews = _segment_previews(chunk_text, segments)

    prompt = f"""You are analyzing a transcript titled "{title}" for a personal health/fitness/mental-health research vault. Respond ONLY with valid JSON, no other text, no markdown fences.

Transcript:
{chunk_text}

The transcript above has been pre-divided into {len(segments)} numbered segments for you:
{segment_previews}

Return JSON with this exact structure:
{{
  "relevant": true or false (is this genuinely about health, fitness/performance, or mental health? Off-topic content like gaming, unrelated vlogging, etc. is false),
  "relevant_confidence": "high" or "medium" or "low" (how confident are YOU in the relevant judgment above - "low" for genuinely ambiguous/borderline cases),
  "signal_density": "high" or "mixed" or "low" - use these concrete anchors, not a vibe:
    "high" = well over half the runtime is substantive/citable (a dense lecture, a focused explainer with minimal filler)
    "mixed" = roughly a third to half is substantive, the rest is filler/tangent/promotional/repetition
    "low" = well under a third is substantive (mostly vlogging, announcements, banter, ads, repeated points)
    Known calibration issue with this exact judgment (documented via real A/B testing against human-verified ratings): this
    model systematically OVER-rates density, calling "mixed" content "high" more often than not. If you are genuinely
    unsure between two tiers, pick the LOWER one - that correction is deliberate, not a suggestion to hedge everything down.,
  "themes": [list of 2-5 short topic/theme tags],
  "key_points": [list of 3-6 substantive points, EXCLUDING any sponsor/ad/promotional content],
  "notable_quotes": [list of 2-5 candidate EXACT verbatim quotes copied character-for-character from the transcript above - never paraphrase, these will be independently verified],
  "structure_map": [array of EXACTLY {len(segments)} strings, one per numbered segment above IN ORDER - use these
    concrete anchors, not a default:
    "substantive" = real information content: a claim, a mechanism, a number, a named study/protocol, real advice
    "filler" = repetition, stalling, verbal tics, restating the same point without adding anything
    "sponsor" = ad reads, product promotion, "use code X", patreon/channel-membership plugs
    "tangent" = real content, but off-topic from the video's stated subject (personal stories, unrelated banter, Q&A drift)
    Known issue with this exact judgment (found via real testing, 2026-08-21): this model has a strong default bias
    toward labeling every segment "substantive" regardless of actual content - a real 100-min vlog-style video and a
    real 2h38m interview both got 100% "substantive" segments on testing, which was wrong on both. Most videos of any
    real length have AT LEAST one segment that fits filler/sponsor/tangent better than substantive - if your answer is
    about to be "substantive" for every single segment, that is the specific failure mode already documented here,
    stop and re-read each segment's preview specifically looking for what does NOT fit "substantive" before finalizing.]
}}"""

    data = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": num_ctx, "num_predict": NUM_PREDICT},
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    parsed = json.loads(result["response"])

    # Attach the real (Python-computed) offsets to the model's per-segment
    # classification - never trust the model for the numeric ranges
    # themselves, only for the substantive/filler/sponsor/tangent label.
    raw_map = parsed.get("structure_map", [])
    valid_types = {"substantive", "filler", "sponsor", "tangent"}
    structure_map = []
    for i, (s, e) in enumerate(segments):
        label = raw_map[i] if i < len(raw_map) else "unknown"
        if label not in valid_types:
            label = "unknown"
        # chunk_offset shifts local (per-chunk) offsets into global
        # (whole-transcript) coordinates - 0 for the single-call path,
        # real for each chunk under query_ollama_chunked.
        structure_map.append({"start": s + chunk_offset, "end": e + chunk_offset, "type": label})
    parsed["structure_map"] = structure_map

    # Structure_map-derived density - EXPERIMENTAL, secondary only, NOT primary.
    # Real 2026-08-21 test found this computation was actually worse than the model's
    # own holistic guess when structure_map itself was still using 180-char previews
    # (see _segment_previews fix above) - it called 8/8 real files "high" density,
    # including 2 that were genuinely "low". Kept as a comparison field so the
    # segment-preview fix above can be re-evaluated for real before trusting this
    # again, rather than silently reintroducing a proven-worse value as primary.
    substantive_count = sum(1 for s in structure_map if s["type"] == "substantive")
    total_segments = len(structure_map) or 1
    substantive_fraction = substantive_count / total_segments
    if substantive_fraction > 0.5:
        computed_density = "high"
    elif substantive_fraction >= 0.33:
        computed_density = "mixed"
    else:
        computed_density = "low"
    parsed["signal_density_structuremap_guess"] = computed_density  # experimental, NOT used downstream yet
    # signal_density stays as the model's own holistic guess (parsed["signal_density"]
    # already holds this from the raw response) - reverted to primary per the real
    # test finding above.
    return parsed


_DENSITY_RANK = {"low": 0, "mixed": 1, "high": 2}
_DENSITY_FROM_RANK = {0: "low", 1: "mixed", 2: "high"}


def query_ollama_chunked(transcript: str, title: str, num_ctx: int) -> dict:
    """Real fix, 2026-09-25: transcripts longer than TRANSCRIPT_CHAR_CAP used
    to get hard-truncated to a single call (transcript[:TRANSCRIPT_CHAR_CAP])
    - everything past that character offset was never shown to the model at
    all. A real audit found this hit 27.7% of the podcast backlog and 4.1%
    of YouTube. Fix: slice into TRANSCRIPT_CHAR_CAP-sized chunks, run the
    existing single-call prompt on each (same num_ctx tier, no VRAM change -
    this does NOT raise context size, it runs the model more times instead,
    which is the safe lever given the 4080 is already near its VRAM ceiling
    at NUM_CTX_LARGE), and merge results with real global offsets rather
    than per-chunk-local ones.

    Merge policy, stated plainly since none of this is free of judgment calls:
    - relevant / relevant_confidence: taken from the FIRST chunk only. A
      transcript's topic is essentially always establishable from its
      opening portion; re-asking on every chunk would risk a later chunk's
      genuine tangent flipping the whole file's relevance for no real gain.
    - signal_density: combined by taking the LOWEST tier seen across chunks
      when chunks disagree by exactly one tier, but the actual rule applied
      is majority vote with ties broken toward the lower tier - consistent
      with this file's own already-documented finding that the model
      systematically OVER-rates density, so under-calling on a tie is the
      same deliberate correction already applied per-chunk, just extended
      across chunks.
    - themes / key_points / notable_quotes: pooled across all chunks
      (deduped for themes), capped at MAX_THEMES_MERGED / MAX_KEY_POINTS_MERGED
      / MAX_QUOTES_MERGED so a very long file doesn't produce an unbounded
      draft - notable_quotes still goes through the same exact-substring
      verification against the full original transcript regardless, so
      capping the candidate pool here is a size limit, not a trust decision.
    - structure_map: concatenated across chunks with real global offsets
      (chunk_offset already applied inside _query_ollama_call) - this is
      the field that most directly benefits from the fix, since it's now a
      genuine map of the WHOLE document instead of silently stopping at the
      old truncation point.
    """
    chunks = [transcript[i:i + TRANSCRIPT_CHAR_CAP] for i in range(0, len(transcript), TRANSCRIPT_CHAR_CAP)]
    chunk_results = []
    for idx, chunk_text in enumerate(chunks):
        chunk_offset = idx * TRANSCRIPT_CHAR_CAP
        chunk_results.append(_query_ollama_call(chunk_text, title, num_ctx, chunk_offset))

    first = chunk_results[0]
    merged_structure_map = []
    merged_themes: list[str] = []
    merged_key_points: list[str] = []
    merged_quotes: list[str] = []
    density_ranks = []
    for cr in chunk_results:
        merged_structure_map.extend(cr.get("structure_map", []))
        for t in cr.get("themes", []):
            if t not in merged_themes:
                merged_themes.append(t)
        merged_key_points.extend(cr.get("key_points", []))
        merged_quotes.extend(cr.get("notable_quotes", []))
        rank = _DENSITY_RANK.get(cr.get("signal_density"))
        if rank is not None:
            density_ranks.append(rank)

    if density_ranks:
        counts = {r: density_ranks.count(r) for r in set(density_ranks)}
        max_count = max(counts.values())
        tied_ranks = [r for r, c in counts.items() if c == max_count]
        merged_density = _DENSITY_FROM_RANK[min(tied_ranks)]  # tie -> lower tier, per the calibration correction above
    else:
        merged_density = first.get("signal_density")

    substantive_count = sum(1 for s in merged_structure_map if s.get("type") == "substantive")
    total_segments = len(merged_structure_map) or 1
    substantive_fraction = substantive_count / total_segments
    if substantive_fraction > 0.5:
        merged_structuremap_guess = "high"
    elif substantive_fraction >= 0.33:
        merged_structuremap_guess = "mixed"
    else:
        merged_structuremap_guess = "low"

    return {
        "relevant": first.get("relevant"),
        "relevant_confidence": first.get("relevant_confidence"),
        "signal_density": merged_density,
        "signal_density_structuremap_guess": merged_structuremap_guess,
        "themes": merged_themes[:MAX_THEMES_MERGED],
        "key_points": merged_key_points[:MAX_KEY_POINTS_MERGED],
        "notable_quotes": merged_quotes[:MAX_QUOTES_MERGED],
        "structure_map": merged_structure_map,
        "chunked": True,
        "chunk_count": len(chunks),
    }


def detect_low_value_pattern(title: str, channel: str) -> list[str]:
    """Deterministic (no LLM) junk-filter hint (2026-08-20, idea #4) - real,
    evidence-based patterns already confirmed low-value in this vault's own
    history (see tag_low_value_notes.py and development.md's 2026-08-08/09
    Concepts-catchup entries). Returns the list of matched reasons (empty if
    none matched) so the finishing pass knows WHY something was flagged, not
    just that it was. This is a hint that speeds up confirmation, never a
    substitute for it - every flagged video still gets a real check."""
    reasons = []
    if channel and channel in LOW_VALUE_CHANNELS:
        reasons.append(f"channel '{channel}' previously confirmed low-signal-density (see tag_low_value_notes.py)")
    if (channel or "").strip().lower() == "kinobody" or "(kinobody)" in (title or "").lower():
        reasons.append("Kinobody channel - long confirmed history of thin/filler-heavy early clips (see development.md 2026-08-16/17)")
    if _LIFT_LOG_TITLE_RE.search(title or ""):
        reasons.append("title matches a bare lift-log pattern (weight for reps) - historically near-zero extractable content")
    if _ADMIN_TITLE_RE.search(title or ""):
        reasons.append("title matches an administrative/promotional pattern (giveaway/announcement), not substantive content")
    if _VLOG_UPDATE_TITLE_RE.search(title or ""):
        reasons.append("title matches a life-update/wrapup/vlog pattern - real 2026-08-21 finding: this shape is a repeatable "
                        "low-density trap (lifestyle/networking chatter, not substantive extractable content), even on channels "
                        "that are otherwise high-signal")
    return reasons


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
    lite_dir = raw_dir / ".lite"  # derived, filler-stripped copies - raw files themselves are never touched

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

    # Priority-first ordering, added 2026-08-21 per Ross's explicit request
    # ("do priority first"). Cheap partial read (first 512 bytes is enough to
    # cover the header's `channel:` line) rather than reading every candidate
    # file's full content just to sort - the backlog can be thousands of
    # files and most won't even make it into this batch.
    def _is_priority(f: Path) -> bool:
        try:
            head = f.open(encoding="utf-8", errors="ignore").read(512)
        except Exception:
            return False
        return any(f"channel: {c}" in head for c in PRIORITY_CHANNELS)

    candidates.sort(key=lambda item: 0 if _is_priority(item[1]) else 1)
    candidates = candidates[: args.batch_size]
    print(f"{len(candidates)} file(s) to draft this run (target={args.target})")

    total_quotes_offered = 0
    total_quotes_verified = 0
    total_filler_chars_removed = 0
    total_low_value_flagged = 0
    total_density_disagreements = 0  # model's own holistic guess vs. the computed-from-structure_map value

    for i, (vid, raw_file) in enumerate(candidates, 1):
        raw_text = raw_file.read_text(encoding="utf-8", errors="ignore")
        header = parse_header_fields(raw_text)
        title = header.get("title") or raw_file.stem
        channel = header.get("channel", "")
        header_block, body = split_header_body(raw_text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Idea #2 (2026-08-20): conservative, zero-meaning-risk filler
        # stripping BEFORE the transcript reaches either Ollama or Claude's
        # own reading - applied to the transcript BODY only, never the
        # metadata header. The raw file on disk is never modified - this
        # writes a separate derived copy. Quote verification below still
        # checks against the untouched `body`, never the stripped copy -
        # see collector_common.strip_filler_text's own docstring for why.
        lite_body, filler_chars_removed = strip_filler_text(body)
        total_filler_chars_removed += filler_chars_removed

        num_ctx = choose_num_ctx(len(lite_body))
        try:
            if len(lite_body) > TRANSCRIPT_CHAR_CAP:
                result = query_ollama_chunked(lite_body, title, num_ctx)
            else:
                result = query_ollama(lite_body, title, num_ctx)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"{timestamp} [{i}/{len(candidates)}] {vid}: FAILED ({exc})")
            continue

        quotes_raw = result.get("notable_quotes", [])
        quotes_verified, dropped = verify_and_filter_quotes(quotes_raw, body)
        total_quotes_offered += len(quotes_raw)
        total_quotes_verified += len(quotes_verified)

        low_value_reasons = detect_low_value_pattern(title, channel)
        if low_value_reasons:
            total_low_value_flagged += 1
        if result.get("signal_density_structuremap_guess") and result.get("signal_density_structuremap_guess") != result.get("signal_density"):
            total_density_disagreements += 1

        lite_path = lite_dir / f"{vid}_lite.txt"
        lite_dir.mkdir(parents=True, exist_ok=True)
        # Keep the same header a normal raw file has (so any script that
        # parses "header up to the first '---' line" still works unmodified
        # against this derived file) plus one marker line flagging it as
        # the filler-stripped derivative, never to be confused with the
        # immutable original.
        lite_path.write_text(header_block + "filler_stripped_derived_from: " + raw_file.name + "\n\n" + lite_body, encoding="utf-8")

        draft = {
            "video_id": vid,
            "source_file": raw_file.name,
            "lite_file": f".lite/{vid}_lite.txt",  # filler-stripped derived copy - read this instead of source_file to save tokens; fall back to source_file for exact quote re-verification or anything that looks truncated/off
            "filler_chars_removed": filler_chars_removed,
            "title": title,
            "generated_at": timestamp,
            "model": MODEL,
            "relevant": result.get("relevant"),
            "relevant_confidence": result.get("relevant_confidence"),  # model's own confidence - "low" means genuinely ambiguous, still verify but expect to spend real time on it
            "known_low_value_pattern": bool(low_value_reasons),  # deterministic, NOT from the model - see detect_low_value_pattern()
            "low_value_pattern_reasons": low_value_reasons,
            "signal_density_guess": result.get("signal_density"),  # the model's own holistic guess - reverted to primary 2026-08-21, see query_ollama
            "signal_density_structuremap_guess": result.get("signal_density_structuremap_guess"),  # experimental, secondary - not yet trusted as primary
            "signal_density_confirmed": False,  # unconfirmed per the migration plan's design - Claude confirms during finishing
            "themes": result.get("themes", []),
            "key_points": result.get("key_points", []),
            "notable_quotes_verified": quotes_verified,
            "notable_quotes_dropped_count": dropped,
            "structure_map": result.get("structure_map", []),  # rough substantive-vs-filler/sponsor/tangent map, offsets into lite_file - UNCONFIRMED hint, same status as signal_density_guess until Claude checks it
            "structure_map_confirmed": False,
            "chunked": result.get("chunked", False),  # true if this file exceeded TRANSCRIPT_CHAR_CAP and was processed via query_ollama_chunked (2026-09-25 fix) - see that function's docstring for merge policy
            "chunk_count": result.get("chunk_count", 1),
        }

        write_json_atomic(drafts_dir / f"{vid}.json", draft)
        drafted[vid] = {"status": "drafted", "draft_file": f".drafts/{vid}.json", "generated_at": timestamp}
        write_json_atomic(drafted_ids_file, drafted)  # checkpoint after every file, same discipline as the collectors

        chunk_note = f", chunked={draft['chunk_count']}x" if draft["chunked"] else ""
        print(f"{timestamp} [{i}/{len(candidates)}] {vid}: drafted "
              f"(relevant={draft['relevant']}/{draft['relevant_confidence']}, density={draft['signal_density_guess']}, "
              f"quotes {len(quotes_verified)}/{len(quotes_raw)} verified, "
              f"filler_chars_removed={filler_chars_removed}, low_value_pattern={draft['known_low_value_pattern']}, "
              f"num_ctx={num_ctx}{chunk_note})")

    if candidates:
        print(f"\nQuote verification rate this run: {total_quotes_verified}/{total_quotes_offered}")
        print(f"Density holistic-guess vs. structuremap-guess disagreement this run: {total_density_disagreements}/{len(candidates)}")
        print(f"Filler characters stripped this run (sum across all drafted files): {total_filler_chars_removed}")
        print(f"Files matching a known low-value pattern this run: {total_low_value_flagged}/{len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
