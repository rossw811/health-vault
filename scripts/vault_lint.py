#!/usr/bin/env python3
"""
vault_lint.py - fast, cheap, no-Claude-cost structural/hygiene linter for the
Health vault.

Complementary to (not a replacement for):
  - /concept-audit          - expensive, adversarial claim-verification (mechanism,
                               evidence, contrarian lenses + /research verification)
  - /obsidian-health         - the bundled obsidian-second-brain skill's health check
                               (wanted-notes triage, contradiction/staleness *semantic*
                               scans via Claude, freshness-policy enforcement, etc.)

This script does none of that. It is a real "lint" in the software sense: pure
Python + regex, no LLM calls, no network calls. It checks structure and hygiene,
not semantic correctness or claim quality. It should run in well under a minute
and never modifies any vault content - it only reports.

Usage:
    python scripts/vault_lint.py [--vault PATH]

Output:
    - Prints a scannable report to stdout.
    - Writes the same report to Logs/vault-lint-YYYY-MM-DD.log (creates Logs/ if
      it somehow doesn't exist, though this vault already has that convention).
"""

from __future__ import annotations

import argparse
import difflib
import io
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Folders whose notes are expected to follow the vault's ai-first schema in
# full (frontmatter + "## For future Claude" preamble). Per CLAUDE.md's note
# architecture and the ai-first-rules.md schema this vault follows. People/
# is deliberately excluded from the frontmatter/preamble checks below (its
# frontmatter schema is legitimately different - no `date` field in practice -
# see scripts/vault_lint.py investigation notes in development.md) but IS
# included in the broader structural checks (orphan links, orphan notes,
# duplicate filenames, TBD scan) since it's still a real content folder.
AI_FIRST_DIRS = ["Concepts", "Optimization", "Protocols", "Synthesis"]
BROAD_CONTENT_DIRS = ["Concepts", "Optimization", "Protocols", "Synthesis", "People"]

# Directories to skip entirely when walking the vault for full link-resolution
# purposes (generated output, VCS/plugin internals, state files).
EXCLUDE_DIR_NAMES = {
    ".git", ".obsidian", "node_modules", "__pycache__", ".state",
    "Dashboard", ".tmp_work", ".vault-config",
}

# Non-.md extensions we still want to be able to resolve wikilinks/embeds
# against (attachments) so we don't false-positive on ![[image.png]].
ATTACHMENT_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".webp", ".mp3", ".mp4",
    ".m4a", ".wav", ".xlsx", ".csv", ".drawio", ".canvas",
}

WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
TBD_RE = re.compile(r"\bTBD\b")
CONTRADICTION_RE = re.compile(r"\[!contradiction\]")
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

FUTURE_CLAUDE_HEADING_RE = re.compile(
    r"^##\s+For future Claude\s*$", re.MULTILINE
)

DUP_NAME_RATIO_THRESHOLD = 0.84


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def should_skip_dir(dirpath: Path) -> bool:
    return dirpath.name in EXCLUDE_DIR_NAMES or dirpath.name.startswith(".")


def walk_all_files(vault_root: Path):
    """Yield every file in the vault, skipping excluded directories."""
    for dirpath, dirnames, filenames in _os_walk(vault_root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(Path(dirpath) / d)]
        for fn in filenames:
            yield Path(dirpath) / fn


def _os_walk(root: Path):
    import os
    for dirpath, dirnames, filenames in os.walk(root):
        yield dirpath, dirnames, filenames


def walk_md_files(vault_root: Path, subdirs: list[str]):
    out = []
    for sub in subdirs:
        base = vault_root / sub
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            if any(should_skip_dir(parent) for parent in p.parents):
                continue
            out.append(p)
    return sorted(out)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> dict | None:
    """Very small, tolerant YAML-frontmatter-key scanner. We don't need a real
    YAML parser - just to detect presence/absence of top-level keys, which is
    all the checks below need."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)
    keys = {}
    for line in block.splitlines():
        km = re.match(r"^([A-Za-z_\-]+)\s*:\s*(.*)$", line)
        if km:
            keys[km.group(1).strip()] = km.group(2).strip()
    return keys


def extract_wikilinks(text: str) -> list[tuple[int, str]]:
    """Return list of (1-based line number, raw target) for every [[...]] or
    ![[...]] occurrence, with heading/alias parts stripped."""
    results = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in WIKILINK_RE.finditer(line):
            raw = m.group(1)
            target = raw.split("|", 1)[0].split("#", 1)[0].strip()
            if not target:
                continue  # pure in-file anchor link like [[#Heading]]
            results.append((lineno, target))
    return results


# ---------------------------------------------------------------------------
# Link resolution index
# ---------------------------------------------------------------------------

@dataclass
class VaultIndex:
    vault_root: Path
    by_relpath_lower: dict[str, Path] = field(default_factory=dict)   # "concepts/foo.md" -> Path
    by_basename_lower: dict[str, list[Path]] = field(default_factory=dict)  # "foo" -> [Path, ...]

    def add(self, path: Path):
        rel = path.relative_to(self.vault_root).as_posix().lower()
        self.by_relpath_lower[rel] = path
        stem = path.stem.lower()
        self.by_basename_lower.setdefault(stem, []).append(path)
        # also index without extension variant for the full rel path (some
        # links use folder/Note without .md)
        rel_noext = rel.rsplit(".", 1)[0] if "." in rel else rel
        self.by_relpath_lower.setdefault(rel_noext, path)

    def resolve(self, target: str) -> bool:
        t = target.strip().lstrip("./")
        t_lower = t.lower()
        # normalize backslashes some Windows-authored links use
        t_lower = t_lower.replace("\\", "/")
        if t_lower in self.by_relpath_lower:
            return True
        if (t_lower + ".md") in self.by_relpath_lower:
            return True
        # bare filename resolution (Obsidian's flexible resolution): match by
        # basename anywhere in the vault
        base = t_lower.rsplit("/", 1)[-1]
        base_noext = base.rsplit(".", 1)[0] if "." in base and not base.endswith((".md",)) else base
        base_noext = base_noext[:-3] if base_noext.endswith(".md") else base_noext
        if base_noext in self.by_basename_lower:
            return True
        if base in self.by_basename_lower:
            return True
        return False


def build_vault_index(vault_root: Path) -> VaultIndex:
    idx = VaultIndex(vault_root=vault_root)
    for p in walk_all_files(vault_root):
        if p.is_file():
            idx.add(p)
    return idx


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_orphaned_links(vault_root: Path, idx: VaultIndex, scan_dirs: list[str]):
    """Item 1: every [[wikilink]] that doesn't resolve to a real file."""
    findings = []
    for md in walk_md_files(vault_root, scan_dirs):
        text = read_text(md)
        for lineno, target in extract_wikilinks(text):
            if not idx.resolve(target):
                findings.append((md.relative_to(vault_root).as_posix(), lineno, target))
    return findings


def check_missing_preamble(vault_root: Path, scan_dirs: list[str]):
    """Item 2: missing '## For future Claude' section."""
    findings = []
    for md in walk_md_files(vault_root, scan_dirs):
        text = read_text(md)
        if not FUTURE_CLAUDE_HEADING_RE.search(text):
            findings.append(md.relative_to(vault_root).as_posix())
    return findings


def check_missing_frontmatter(vault_root: Path, scan_dirs: list[str]):
    """Item 3: missing/incomplete frontmatter (type, date/created/updated, tags,
    ai-first: true)."""
    findings = []  # (relpath, [missing fields])
    for md in walk_md_files(vault_root, scan_dirs):
        text = read_text(md)
        keys = parse_frontmatter(text)
        rel = md.relative_to(vault_root).as_posix()
        if keys is None:
            findings.append((rel, ["<no frontmatter block found>"]))
            continue
        missing = []
        if "type" not in keys:
            missing.append("type")
        if not any(k in keys for k in ("date", "created", "updated")):
            missing.append("date/created/updated")
        if "tags" not in keys:
            missing.append("tags")
        if keys.get("ai-first", "").lower() != "true":
            missing.append("ai-first: true")
        if missing:
            findings.append((rel, missing))
    return findings


def check_tbd_markers(vault_root: Path, scan_dirs: list[str]):
    """Item 4: literal TBD markers left in prose/tables."""
    findings = []  # (relpath, count, [line numbers up to a cap])
    for md in walk_md_files(vault_root, scan_dirs):
        text = read_text(md)
        lines = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if TBD_RE.search(line):
                lines.append(lineno)
        if lines:
            findings.append((md.relative_to(vault_root).as_posix(), len(lines), lines[:10]))
    return findings


def normalize_stem(stem: str) -> str:
    s = stem.lower()
    s = re.sub(r"\(.*?\)", "", s)          # drop parenthetical qualifiers
    s = re.sub(r"[^a-z0-9]+", " ", s)      # punctuation -> space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def check_duplicate_filenames(vault_root: Path, scan_dirs: list[str]):
    """Item 5: near-identical filenames within the same folder (simple string
    similarity, not semantic)."""
    findings = []  # (folder, name_a, name_b, ratio)
    for sub in scan_dirs:
        base = vault_root / sub
        if not base.exists():
            continue
        files = [p for p in base.rglob("*.md") if not any(should_skip_dir(par) for par in p.parents)]
        norm = [(p, normalize_stem(p.stem)) for p in files]
        n = len(norm)
        for i in range(n):
            for j in range(i + 1, n):
                p1, s1 = norm[i]
                p2, s2 = norm[j]
                if not s1 or not s2 or s1 == s2:
                    if s1 == s2 and p1 != p2:
                        findings.append((sub, p1.name, p2.name, 1.0))
                    continue
                ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
                if ratio >= DUP_NAME_RATIO_THRESHOLD:
                    findings.append((sub, p1.name, p2.name, round(ratio, 3)))
    findings.sort(key=lambda f: -f[3])
    return findings


def check_orphan_notes(vault_root: Path, idx: VaultIndex, scan_dirs: list[str]):
    """Item 6: notes with zero inbound AND zero outbound [[wikilinks]].
    Inbound is computed against the whole vault (a note in Concepts/ might
    legitimately only be linked from a Daily/ note), outbound only counts
    links found in the note itself."""
    all_md = [p for p in walk_all_files(vault_root) if p.suffix.lower() == ".md"]
    outbound_count: dict[Path, int] = {}
    inbound_count: dict[Path, int] = {p: 0 for p in all_md}

    for md in all_md:
        text = read_text(md)
        links = extract_wikilinks(text)
        outbound_count[md] = len(links)
        for _, target in links:
            for resolved in _resolve_to_paths(idx, target):
                if resolved in inbound_count:
                    inbound_count[resolved] += 1

    findings = []
    for md in walk_md_files(vault_root, scan_dirs):
        out_c = outbound_count.get(md, 0)
        in_c = inbound_count.get(md, 0)
        if out_c == 0 and in_c == 0:
            findings.append(md.relative_to(vault_root).as_posix())
    return findings


def _resolve_to_paths(idx: VaultIndex, target: str) -> list[Path]:
    t_lower = target.strip().lstrip("./").replace("\\", "/").lower()
    if t_lower in idx.by_relpath_lower:
        return [idx.by_relpath_lower[t_lower]]
    if (t_lower + ".md") in idx.by_relpath_lower:
        return [idx.by_relpath_lower[t_lower + ".md"]]
    base = t_lower.rsplit("/", 1)[-1]
    base_noext = base[:-3] if base.endswith(".md") else base
    return idx.by_basename_lower.get(base_noext, idx.by_basename_lower.get(base, []))


def check_old_contradictions(vault_root: Path, scan_dirs: list[str], today: datetime):
    """Item 7: [!contradiction] callouts, flagged with age if a date can be
    found nearby (same line, a heading above it, or the 3 lines before it)."""
    findings = []  # (relpath, lineno, snippet, date_str_or_None, age_days_or_None)
    for md in walk_md_files(vault_root, scan_dirs):
        text = read_text(md)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if CONTRADICTION_RE.search(line):
                snippet = line.strip()[:120]
                date_str = None
                dm = DATE_RE.search(line)
                if dm:
                    date_str = dm.group(1)
                else:
                    for back in range(1, 4):
                        idx_back = i - back
                        if idx_back < 0:
                            break
                        dm2 = DATE_RE.search(lines[idx_back])
                        if dm2:
                            date_str = dm2.group(1)
                            break
                age_days = None
                if date_str:
                    try:
                        d = datetime.strptime(date_str, "%Y-%m-%d")
                        age_days = (today - d).days
                    except ValueError:
                        pass
                findings.append((
                    md.relative_to(vault_root).as_posix(), i + 1, snippet, date_str, age_days
                ))
    return findings


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(vault_root: Path) -> str:
    today = datetime.now()
    out = io.StringIO()

    def p(s=""):
        print(s, file=out)

    idx = build_vault_index(vault_root)

    orphaned_links = check_orphaned_links(vault_root, idx, BROAD_CONTENT_DIRS)
    missing_preamble = check_missing_preamble(vault_root, AI_FIRST_DIRS)
    missing_frontmatter = check_missing_frontmatter(vault_root, AI_FIRST_DIRS)
    tbd_markers = check_tbd_markers(vault_root, BROAD_CONTENT_DIRS)
    dup_filenames = check_duplicate_filenames(vault_root, BROAD_CONTENT_DIRS)
    orphan_notes = check_orphan_notes(vault_root, idx, BROAD_CONTENT_DIRS)
    old_contradictions = check_old_contradictions(vault_root, BROAD_CONTENT_DIRS, today)

    p("=" * 78)
    p(f"VAULT LINT REPORT - {today.strftime('%Y-%m-%d %H:%M')}")
    p(f"Vault: {vault_root}")
    p("=" * 78)
    p()
    p("Structural/mechanical checks only (pure Python + regex, no LLM calls).")
    p("Complementary to /concept-audit (claim verification) and /obsidian-health")
    p("(the bundled skill's semantic health check). This never modifies content.")
    p()
    p("-" * 78)
    p("SUMMARY")
    p("-" * 78)
    p(f"  1. Orphaned wikilinks (unresolved [[...]])........ {len(orphaned_links)}")
    p(f"  2. Missing '## For future Claude' preamble......... {len(missing_preamble)}")
    p(f"  3. Missing/incomplete frontmatter................... {len(missing_frontmatter)}")
    p(f"  4. Files with stale TBD markers...................... {len(tbd_markers)}"
      f" ({sum(c for _, c, _ in tbd_markers)} total occurrences)")
    p(f"  5. Near-duplicate filename pairs..................... {len(dup_filenames)}")
    p(f"  6. Orphan notes (0 inbound + 0 outbound links)....... {len(orphan_notes)}")
    p(f"  7. [!contradiction] callouts found (age-flagged)..... {len(old_contradictions)}")
    p()

    p("-" * 78)
    p("1. ORPHANED WIKILINKS")
    p("-" * 78)
    if not orphaned_links:
        p("  none")
    else:
        for rel, lineno, target in orphaned_links:
            p(f"  {rel}:{lineno}  ->  [[{target}]]")
    p()

    p("-" * 78)
    p("2. MISSING '## For future Claude' PREAMBLE")
    p("-" * 78)
    if not missing_preamble:
        p("  none")
    else:
        for rel in missing_preamble:
            p(f"  {rel}")
    p()

    p("-" * 78)
    p("3. MISSING/INCOMPLETE FRONTMATTER")
    p("-" * 78)
    if not missing_frontmatter:
        p("  none")
    else:
        for rel, missing in missing_frontmatter:
            p(f"  {rel}  ->  missing: {', '.join(missing)}")
    p()

    p("-" * 78)
    p("4. STALE TBD MARKERS")
    p("-" * 78)
    if not tbd_markers:
        p("  none")
    else:
        for rel, count, lines in tbd_markers:
            more = "" if count <= len(lines) else f" (+{count - len(lines)} more)"
            p(f"  {rel}  ->  {count} occurrence(s) at lines {lines}{more}")
    p()

    p("-" * 78)
    p("5. NEAR-DUPLICATE FILENAMES")
    p("-" * 78)
    if not dup_filenames:
        p("  none")
    else:
        for folder, a, b, ratio in dup_filenames:
            p(f"  [{folder}] '{a}'  ~=  '{b}'   (similarity {ratio})")
    p()

    p("-" * 78)
    p("6. ORPHAN NOTES (zero inbound + zero outbound wikilinks)")
    p("-" * 78)
    if not orphan_notes:
        p("  none")
    else:
        for rel in orphan_notes:
            p(f"  {rel}")
    p()

    p("-" * 78)
    p("7. [!contradiction] CALLOUTS (age-flagged, not resolved)")
    p("-" * 78)
    if not old_contradictions:
        p("  none")
    else:
        old_contradictions_sorted = sorted(
            old_contradictions, key=lambda f: (f[4] is None, -(f[4] or 0))
        )
        for rel, lineno, snippet, date_str, age_days in old_contradictions_sorted:
            if date_str:
                p(f"  {rel}:{lineno}  [{date_str}, {age_days}d old]  {snippet}")
            else:
                p(f"  {rel}:{lineno}  [no date found nearby]  {snippet}")
    p()

    p("=" * 78)
    p("END OF REPORT")
    p("=" * 78)

    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(description="Fast structural/hygiene linter for the Health vault.")
    ap.add_argument("--vault", type=str, default=None, help="Path to vault root (default: parent of scripts/)")
    args = ap.parse_args()

    if args.vault:
        vault_root = Path(args.vault).expanduser().resolve()
    else:
        vault_root = Path(__file__).resolve().parent.parent

    report = build_report(vault_root)
    print(report)

    logs_dir = vault_root / "Logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"vault-lint-{datetime.now().strftime('%Y-%m-%d')}.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport also written to: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
