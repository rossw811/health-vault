#!/usr/bin/env python3
"""
export_safe_copy.py - produce a safe-to-share copy of one or more vault notes
by stripping `[!hidden]` callout blocks (the in-note privacy convention added
2026-09-02, see CLAUDE.md's "In-note privacy" section).

This is the missing piece that convention explicitly flagged as not yet
built: `[!hidden]-` callouts fold content out of Obsidian's default view, but
the raw text is still sitting in the .md file - this script is the actual
"produce a copy safe to hand to someone else" step.

What it does:
  1. Reads a note (or every .md file under a given folder).
  2. Removes every `[!hidden]` callout block in full (the callout line plus
     every contiguous blockquote-continuation line under it), replacing each
     one with a single visible marker line so a reader can tell content was
     removed rather than silently getting a smaller note.
  3. Runs a best-effort heuristic scan of what's LEFT for likely-still-personal
     content that was never marked `[!hidden]` (the vault's own name, links
     into inherently-personal folders, common personal-data patterns) and
     prints those as warnings - this script strips what was marked, it does
     not and cannot guarantee everything personal WAS marked. Read the
     warnings before actually sharing anything.
  4. Writes the result under `Exports/` (mirroring the source's relative
     path), never overwriting vault content in place.

This does NOT touch git, does NOT publish or send anything anywhere - it only
writes a local file for a human to review and decide whether to actually
share. Exports/ is vault content like everything else: gitignored, local-only
until a human moves it somewhere on purpose.

Usage:
    python scripts/export_safe_copy.py "Concepts/Glycine.md"
    python scripts/export_safe_copy.py "Optimization/Insulin Sensitivity.md" --out-name my-share.md
    python scripts/export_safe_copy.py --folder Concepts
    python scripts/export_safe_copy.py "Concepts/Glycine.md" --vault "C:/Users/RossW/Projects/Health"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# A `[!hidden]` callout line, any fold-state suffix (`-` collapsed, `+`
# expanded, or none), optional title text after it.
HIDDEN_CALLOUT_START_RE = re.compile(
    r"^(?P<indent>[ \t]*)>\s*\[!hidden\][-+]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
# A blockquote continuation line (belongs to the callout block above it).
BLOCKQUOTE_LINE_RE = re.compile(r"^[ \t]*>")

# Folders whose content is inherently personal - a link INTO these from an
# otherwise-general note is a real signal the surrounding text may be
# personal too, even if nobody wrapped it in [!hidden].
PERSONAL_FOLDER_LINK_RE = re.compile(
    r"\[\[(Protocols/My Profile|Bloodwork/[^\]]*|Daily/[^\]]*|People/[^\]]*)\]?\]?",
    re.IGNORECASE,
)

# Cheap, deliberately narrow heuristics - false negatives are expected (this
# is not a substitute for a human actually reading the output before
# sharing it), false positives are acceptable since these are warnings, not
# automatic redactions.
PERSONAL_NAME_RE = re.compile(r"\bRoss\b")
DOSE_LIKE_RE = re.compile(
    r"\b\d+(\.\d+)?\s?(mg|mcg|iu|iu/day|ml|mL)\b.{0,25}\b(Ross|self[- ]reported|current(ly)? (dos|tak)ing)\b",
    re.IGNORECASE,
)

DEFAULT_EXPORT_ROOT_NAME = "Exports"


@dataclass
class ExportResult:
    source: Path
    dest: Path
    hidden_blocks_removed: int
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def strip_hidden_callouts(text: str) -> tuple[str, int]:
    """Remove every [!hidden] callout block, replacing each with a marker
    line. Returns (new_text, count_removed)."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HIDDEN_CALLOUT_START_RE.match(line.rstrip("\r\n"))
        if not m:
            out.append(line)
            i += 1
            continue

        # Consume this callout's start line plus every contiguous
        # blockquote-continuation line under it (Obsidian callout syntax:
        # the block ends at the first line that isn't `>`-prefixed, blank
        # lines included since a blank `>` line is still a continuation but
        # a truly blank line is not).
        i += 1
        while i < len(lines) and BLOCKQUOTE_LINE_RE.match(lines[i]):
            i += 1

        removed += 1
        indent = m.group("indent")
        out.append(
            f"{indent}> [!hidden]- *[private content removed for this export "
            f"- see the source note in the vault]*\n"
        )
        # Preserve a following blank line if the original had one, so
        # spacing doesn't collapse note-to-note.
        if i < len(lines) and lines[i].strip() == "":
            out.append(lines[i])
            i += 1

    return "".join(out), removed


def scan_for_unmarked_personal_content(text: str) -> list[str]:
    """Best-effort warnings about content that looks personal but wasn't
    inside a [!hidden] block. Never modifies anything - just flags."""
    warnings: list[str] = []

    name_hits = len(PERSONAL_NAME_RE.findall(text))
    if name_hits:
        warnings.append(
            f"Contains \"Ross\" {name_hits} time(s) outside any [!hidden] "
            f"block - review whether those mentions are identifying."
        )

    folder_hits = sorted(set(m.group(1) for m in PERSONAL_FOLDER_LINK_RE.finditer(text)))
    if folder_hits:
        preview = ", ".join(folder_hits[:5])
        more = f" (+{len(folder_hits) - 5} more)" if len(folder_hits) > 5 else ""
        warnings.append(
            f"Links into inherently-personal folders outside any [!hidden] "
            f"block: {preview}{more}"
        )

    if DOSE_LIKE_RE.search(text):
        warnings.append(
            "Contains what looks like a specific personal dose/self-report "
            "outside any [!hidden] block - double-check before sharing."
        )

    return warnings


def export_one(source: Path, vault_root: Path, export_root: Path, out_name: str | None) -> ExportResult:
    text = source.read_text(encoding="utf-8")
    new_text, removed = strip_hidden_callouts(text)
    warnings = scan_for_unmarked_personal_content(new_text)

    rel = source.relative_to(vault_root)
    dest = export_root / rel.parent / (out_name if out_name else rel.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(new_text, encoding="utf-8")

    return ExportResult(source=source, dest=dest, hidden_blocks_removed=removed, warnings=warnings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("note", nargs="?", help="Path to a single note (relative to --vault, or absolute)")
    parser.add_argument("--folder", help="Export every .md file under this folder (relative to --vault) instead of a single note")
    parser.add_argument("--out-name", help="Override the output filename (single-note mode only)")
    parser.add_argument("--vault", default=".", help="Vault root (default: current directory)")
    args = parser.parse_args()

    if not args.note and not args.folder:
        parser.error("pass a note path or --folder")
    if args.note and args.folder:
        parser.error("pass either a note path or --folder, not both")

    vault_root = Path(args.vault).resolve()
    export_root = vault_root / DEFAULT_EXPORT_ROOT_NAME

    if args.folder:
        src_dir = (vault_root / args.folder).resolve()
        if not src_dir.is_dir():
            print(f"Not a folder: {src_dir}", file=sys.stderr)
            return 1
        sources = sorted(src_dir.rglob("*.md"))
        if not sources:
            print(f"No .md files found under {src_dir}")
            return 0
    else:
        note_path = Path(args.note)
        source = note_path if note_path.is_absolute() else (vault_root / note_path)
        source = source.resolve()
        if not source.is_file():
            print(f"Not a file: {source}", file=sys.stderr)
            return 1
        sources = [source]

    results: list[ExportResult] = []
    for src in sources:
        out_name = args.out_name if len(sources) == 1 else None
        results.append(export_one(src, vault_root, export_root, out_name))

    total_removed = sum(r.hidden_blocks_removed for r in results)
    total_warned = sum(len(r.warnings) for r in results)

    print(f"Exported {len(results)} note(s) to {export_root}\n")
    for r in results:
        rel_dest = r.dest.relative_to(vault_root)
        print(f"  {r.source.relative_to(vault_root)} -> {rel_dest}")
        print(f"    [!hidden] blocks removed: {r.hidden_blocks_removed}")
        if r.hidden_blocks_removed == 0:
            print(
                "    NOTE: zero [!hidden] blocks found - this is an unmodified "
                "copy, not evidence the note is actually safe to share."
            )
        for w in r.warnings:
            print(f"    WARNING: {w}")
        print()

    print(
        f"Summary: {total_removed} block(s) stripped across {len(results)} "
        f"note(s), {total_warned} warning(s) raised. This tool marks and "
        f"strips what it can find - it is not a substitute for actually "
        f"reading the exported file before sharing it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
