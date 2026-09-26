#!/usr/bin/env python3
"""Real fix, 2026-08-22, for a bug found running the first large-scale Stage 2
batch: raw transcripts are stored as `header\n---\n\n<transcript>`, and the
transcript body is written as ONE giant single line (no internal newlines).
The Read tool's offset/limit is line-based, so it can't chunk a body over
~25K words at all - it hits a hard token-cap wall on the very first read
attempt for any long-form episode (Attia/Huberman/RP-length content).

This script pre-splits the body into numbered, Read-tool-friendly part files
under `.chunks/<video_id>/`, same derived-copy pattern as `.lite/` (raw file
on disk is never touched). Each part is capped well under a size any Read
call can handle in one shot, split on sentence boundaries where possible so
a part never cuts mid-sentence right at a chunk edge, which would risk a
quote spanning two parts being missed.

Usage:
    python scripts/chunk_long_transcript.py <raw_file_path> [--chunk-chars 20000]

Prints the list of part file paths written, in order - a caller (Claude,
during a real note-writing pass) reads each one in sequence to get 100% of
the transcript body, not a percentage sample.
"""
import argparse
import re
import sys
from pathlib import Path

DEFAULT_CHUNK_CHARS = 20000


def split_header_body(raw_text: str) -> tuple[str, str]:
    m = re.match(r"(.*?\n---\n\n?)", raw_text, re.DOTALL)
    if not m:
        return "", raw_text
    return m.group(1), raw_text[m.end():]


def chunk_body(body: str, chunk_chars: int) -> list[str]:
    """Split on sentence boundaries near each chunk_chars target, not a blind
    character cut - avoids splitting a sentence (and therefore a potential
    verbatim quote) across two part files."""
    if len(body) <= chunk_chars:
        return [body]
    chunks = []
    start = 0
    length = len(body)
    while start < length:
        target = min(start + chunk_chars, length)
        if target < length:
            # search forward a bit for the next sentence-ending punctuation
            # followed by a space, so we don't cut mid-sentence
            search_end = min(target + 500, length)
            m = re.search(r"[.!?]\s", body[target:search_end])
            if m:
                target = target + m.end()
        chunks.append(body[start:target])
        start = target
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw_file", type=Path)
    parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    args = parser.parse_args()

    if not args.raw_file.exists():
        print(f"File not found: {args.raw_file}", file=sys.stderr)
        return 1

    raw_text = args.raw_file.read_text(encoding="utf-8", errors="ignore")
    header, body = split_header_body(raw_text)

    m = re.search(r"\[([\w-]+)\]_full\.txt$", args.raw_file.name)
    video_id = m.group(1) if m else args.raw_file.stem

    chunks_dir = args.raw_file.parent / ".chunks" / video_id
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # Clean up any stale parts from a prior run against this file first, so a
    # re-run with a different chunk size doesn't leave orphaned old parts.
    for old in chunks_dir.glob("part*.txt"):
        old.unlink()

    parts = chunk_body(body, args.chunk_chars)
    written = []
    for i, chunk in enumerate(parts, 1):
        part_path = chunks_dir / f"part{i}_of_{len(parts)}.txt"
        part_path.write_text(
            f"{header}[chunk {i}/{len(parts)} of {args.raw_file.name} - derived, "
            f"filler-stripping/quote-verification always checks the ORIGINAL raw file, "
            f"never this chunk]\n\n{chunk}",
            encoding="utf-8",
        )
        written.append(str(part_path))

    for path in written:
        print(path)
    print(f"\n{len(written)} part(s) written, {len(body)} total body chars, "
          f"~{len(body) // max(1, len(written))} chars/part.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
