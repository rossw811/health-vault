"""Retroactively tag confirmed-low-value notes with signal_density: low.

Why: three separate Concepts-catchup agents on 2026-08-08/09 each
independently sampled a few notes from these channels/series, confirmed near-
zero extractable concept content, and skipped the rest by judgment call -
the same discovery paid for three times. These notes predate the
signal_density field (added 2026-08-01), so nothing currently lets a future
pass filter them out without re-sampling again.

Scope, deliberately narrow and evidence-based (channel field or explicit
title-series match, not a guess): Kinobody-branded YouTube videos (title
contains "(Kinobody)") and four confirmed-low-signal boxing/MMA-technique
channels (Matt Crawford Boxing, FightBoxing, Dynamic Striking, Combat
Athlete Physio) - all confirmed low-value by direct sampling this session,
not assumed from the channel name alone.

Only sets signal_density if the note doesn't already have one - never
overwrites an existing value. Idempotent, safe to re-run.
"""

import re
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
YT_DIR = VAULT_ROOT / "Research" / "YouTube"

LOW_VALUE_CHANNELS = [
    "Matt Crawford Boxing",
    "FightBoxing",
    "Dynamic Striking",
    "Combat Athlete Physio",
]


def is_kinobody(path):
    return "(Kinobody)" in path.name


def channel_of(text):
    m = re.search(r"^channel:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def has_signal_density(text):
    return re.search(r"^signal_density:", text, re.MULTILINE) is not None


def add_signal_density_low(text):
    # Insert right before the closing frontmatter '---'
    m = re.match(r"^(---\n.*?\n)(---\n)", text, re.DOTALL)
    if not m:
        return text
    head, close = m.group(1), m.group(2)
    addition = "signal_density: low  # confirmed low-value 2026-08-09, see buglog.md\n"
    return head + addition + close + text[m.end():]


def main():
    tagged = 0
    checked = 0
    for f in YT_DIR.glob("*.md"):
        checked += 1
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if has_signal_density(text):
            continue
        ch = channel_of(text)
        if is_kinobody(f) or (ch in LOW_VALUE_CHANNELS):
            f.write_text(add_signal_density_low(text), encoding="utf-8")
            tagged += 1

    print(f"YouTube notes checked: {checked}")
    print(f"Notes newly tagged signal_density: low: {tagged}")


if __name__ == "__main__":
    main()
