"""Automated version of the manual audit that found ~3,000 videos of real
backlog hidden behind stale checked-off channel lines (2026-07-25 incident -
see buglog.md and feedback_no_age_based_exclusions.md / the
project_health_vault_youtube_backlog memory). Zero Claude cost - pure
yt-dlp + JSON comparison.

For every CHECKED-OFF channel line in YouTube Queue.md, compares its real
current video count (yt-dlp --flat-playlist) against how many of that
channel's videos actually appear in Research/YouTube/Raw/.collected_ids.json
with status "ok". If the gap is large, the channel line is automatically
unchecked (reopened) rather than just logged - self-healing, so this
exact bug class can't silently recur and require another manual discovery.

Usage:
    python scripts/backlog_health_check.py [--threshold 10]

Designed to run periodically via a scheduled task - registered directly as
HealthVault-BacklogHealthCheck, invoking this script's full path via
python.exe directly (no .cmd wrapper - confirmed 2026-08-08, corrected this
docstring which previously referenced a run-backlog-health-check.cmd that
was never created). Takes a while (one yt-dlp call per checked channel) so
isn't run every hour like reap_orphans.ps1, more like daily/weekly alongside
vault-update.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent  # portable — see NEW-MACHINE-SETUP.md, 2026-08-15
QUEUE_FILE = VAULT_ROOT / "YouTube Queue.md"
COLLECTED_IDS_FILE = VAULT_ROOT / "Research" / "YouTube" / "Raw" / ".collected_ids.json"
LOG_FILE = VAULT_ROOT / "Logs" / "backlog-health-check.log"

CHANNEL_LINE_RE = re.compile(r"^(- \[x\]) (https://www\.youtube\.com/(@[\w.-]+|channel/[\w-]+|user/[\w-]+))(/videos)?\s*(.*)$")


def list_channel_video_ids(channel_url: str) -> list[str]:
    videos_url = channel_url.rstrip("/") + "/videos"
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", videos_url],
        capture_output=True, text=True, timeout=60,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=10,
                         help="Minimum gap (real total - recorded ok count) before auto-reopening a channel")
    args = parser.parse_args()

    collected = json.loads(COLLECTED_IDS_FILE.read_text(encoding="utf-8")) if COLLECTED_IDS_FILE.exists() else {}
    ok_ids = {vid for vid, entry in collected.items() if entry.get("status") == "ok"}

    lines = QUEUE_FILE.read_text(encoding="utf-8").splitlines()
    reopened = []
    checked_count = 0

    for i, line in enumerate(lines):
        m = CHANNEL_LINE_RE.match(line)
        if not m:
            continue
        checked_count += 1
        channel_url = m.group(2)
        try:
            real_ids = set(list_channel_video_ids(channel_url))
        except Exception as exc:  # noqa: BLE001 - a single channel's yt-dlp failure shouldn't stop the whole audit
            print(f"  {channel_url}: yt-dlp failed ({exc}) - skipping")
            continue

        real_total = len(real_ids)
        actually_collected = len(real_ids & ok_ids)
        gap = real_total - actually_collected

        if gap >= args.threshold:
            rest_of_line = m.group(5)
            new_line = f"- [ ] {channel_url} (auto-reopened by backlog_health_check.py - {actually_collected}/{real_total} real videos actually collected, {gap} gap) {rest_of_line}".rstrip()
            lines[i] = new_line
            reopened.append((channel_url, actually_collected, real_total))
            print(f"  REOPENED {channel_url}: {actually_collected}/{real_total} collected, gap={gap}")
        else:
            print(f"  OK {channel_url}: {actually_collected}/{real_total} collected, gap={gap}")

    if reopened:
        QUEUE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    summary = f"{datetime.now().isoformat(timespec='seconds')} - checked {checked_count} channel(s), reopened {len(reopened)}: {reopened}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(summary + "\n")
    print(f"\n{summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
