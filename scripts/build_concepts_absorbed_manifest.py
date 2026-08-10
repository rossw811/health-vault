"""Build/refresh the concepts-absorption manifest and per-note banners.

Why this exists: multiple Concepts-catchup passes on 2026-08-08/09 each had
to re-discover "was this video/podcast note's content already folded into
Concepts/?" via ad-hoc grep/reads - real token cost paid repeatedly for the
same answer. This vault already has the right per-note mechanism for this
(a `> [!info]` "Absorbed into Concepts" banner, per
.claude/commands/process-raw-transcripts.md step 3) but it was only applied
inconsistently - many notes absorbed into Concepts/ over past sessions never
got the banner, and a same-day batch of catchup agents run strictly
read-only on Research/ (correctly, to avoid duplicating note-writing work)
couldn't add it either.

This script closes that gap using real ground truth already sitting in the
vault: every Concepts/*.md (and Optimization/, Protocols/) file that cites a
Research/YouTube/*.md or Research/Podcasts/*.md note via a wikilink is
treated as proof that note's content was actually used. For each such
Research/ note:
  1. Add the `> [!info] Absorbed into Concepts` banner if not already present
     (a single-line addition right after frontmatter - never touches the
     rest of the note's content).
  2. Record it in Research/.concepts_absorbed.json, keyed by relative path,
     so a future catchup pass can check one small JSON file instead of
     opening hundreds of individual notes.

Idempotent and safe to re-run anytime (e.g. after a new Stage-2 batch or a
new Concepts-catchup pass) - only adds what's missing, never removes or
rewrites existing content.
"""

import json
import re
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = VAULT_ROOT / "Research" / ".concepts_absorbed.json"

# Directories whose wikilinks count as "this Research/ note was actually used"
CITING_DIRS = ["Concepts", "Optimization", "Protocols"]
SOURCE_DIRS = ["Research/YouTube", "Research/Podcasts"]

LINK_RE = re.compile(r"\[\[([^\]|#]+)")
BANNER_TEXT = "> [!info] Absorbed into Concepts\n> This note's content has been folded into the Concepts/ layer (see the citing note(s) for which). Safe to skip on a future concept-catchup pass unless re-reading the raw content specifically is needed."


def find_citing_files():
    files = []
    for d in CITING_DIRS:
        p = VAULT_ROOT / d
        if p.exists():
            files.extend(p.rglob("*.md"))
    return files


def find_source_notes():
    """Map: basename (no ext) -> relative path, for every Research/YouTube
    and Research/Podcasts note (top-level only, not Raw/)."""
    out = {}
    for d in SOURCE_DIRS:
        p = VAULT_ROOT / d
        if not p.exists():
            continue
        for f in p.glob("*.md"):
            out[f.stem] = f.relative_to(VAULT_ROOT).as_posix()
    return out


def already_absorbed(text):
    return "Absorbed into Concepts" in text


def insert_banner(text):
    m = re.match(r"^(---\n.*?\n---\n)", text, re.DOTALL)
    if m:
        head = m.group(1)
        rest = text[len(head):]
        return head + "\n" + BANNER_TEXT + "\n" + rest
    return BANNER_TEXT + "\n\n" + text


def main():
    source_notes = find_source_notes()
    citing_files = find_citing_files()

    absorbed = {}  # relative_path -> {citing_from: [...], checked_at: ...}
    for cf in citing_files:
        try:
            text = cf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            base = target.rsplit("/", 1)[-1]
            base = base[:-3] if base.lower().endswith(".md") else base
            if base in source_notes:
                rel = source_notes[base]
                absorbed.setdefault(rel, {"citing_from": []})
                citer_rel = cf.relative_to(VAULT_ROOT).as_posix()
                if citer_rel not in absorbed[rel]["citing_from"]:
                    absorbed[rel]["citing_from"].append(citer_rel)

    banners_added = 0
    for rel_path in absorbed:
        full = VAULT_ROOT / rel_path
        if not full.exists():
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        if not already_absorbed(text):
            full.write_text(insert_banner(text), encoding="utf-8")
            banners_added += 1

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "note": "Auto-built by scripts/build_concepts_absorbed_manifest.py - re-run anytime, safe/idempotent.",
        "total_absorbed": len(absorbed),
        "notes": absorbed,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Source notes scanned: {len(source_notes)}")
    print(f"Citing files scanned: {len(citing_files)}")
    print(f"Notes confirmed absorbed (cited from Concepts/Optimization/Protocols): {len(absorbed)}")
    print(f"Banners newly added this run: {banners_added}")
    print(f"Manifest written: {MANIFEST_PATH.relative_to(VAULT_ROOT)}")


if __name__ == "__main__":
    main()
