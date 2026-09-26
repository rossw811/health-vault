"""Check real Stage-1 completion for the 7 explicitly-prioritized channels
(2026-08-19 user request: Steve, Huberman, Winney, Norwitz, Attia, RP, BJ).

"Complete" = every video is either collected ("ok") or terminally failed
("permanently-failed"/"qc-failed", which the collector never auto-retries) -
NOT just "checked off", per this vault's own documented distinction between
those two things (development.md / CLAUDE.md YouTube backlog gap).

Usage: python3 check_priority_completion.py
Exit code 0 + prints ALL_COMPLETE if done, exit 1 + prints remaining counts otherwise.
"""
import json
import subprocess
import sys
from pathlib import Path

VAULT = Path("/home/rw/Health")
COLLECTED_IDS = VAULT / "Research/YouTube/Raw/.collected_ids.json"
RAW_DIR = VAULT / "Research/YouTube/Raw"

CHANNELS = {
    "Ben Winney": "https://www.youtube.com/@BenWinney",
    "Huberman": "https://www.youtube.com/@hubermanlab",
    "Vigorous Steve": "https://www.youtube.com/@VigorousSteve",
    "Nick Norwitz": "https://www.youtube.com/@nicknorwitzMDPhD",
    "Peter Attia": "https://www.youtube.com/@PeterAttiaMD",
    "Renaissance Periodization": "https://www.youtube.com/@RenaissancePeriodization",
    "Bryan Johnson": "https://www.youtube.com/@BryanJohnson",
}

TERMINAL_DONE_STATUS = {"ok", "permanently-failed", "qc-failed", "skipped-covered-by-podcast"}


def build_raw_file_id_set() -> set[str]:
    """Real successes are represented by the raw file's existence, not a
    collected_ids.json 'ok' entry (only 3 such entries exist vault-wide -
    that JSON is predominantly a failure/retry tracker, not a success log)."""
    ids = set()
    import re
    pat = re.compile(r"\[([\w-]+)\]_full\.txt$")
    for f in RAW_DIR.glob("*_full.txt"):
        m = pat.search(f.name)
        if m:
            ids.add(m.group(1))
    return ids


def get_channel_video_ids(url: str) -> list[str]:
    videos_url = url.rstrip("/") + "/videos"
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s", videos_url],
        capture_output=True, text=True, timeout=120,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    collected = json.loads(COLLECTED_IDS.read_text(encoding="utf-8")) if COLLECTED_IDS.exists() else {}
    raw_file_ids = build_raw_file_id_set()

    all_done = True
    lines = []
    for name, url in CHANNELS.items():
        try:
            ids = get_channel_video_ids(url)
        except Exception as e:
            lines.append(f"{name}: ERROR enumerating channel ({e})")
            all_done = False
            continue

        total = len(ids)
        done = sum(
            1 for vid in ids
            if vid in raw_file_ids or collected.get(vid, {}).get("status") in TERMINAL_DONE_STATUS
        )
        pending = total - done
        status = "COMPLETE" if pending == 0 else f"{pending} still pending"
        lines.append(f"{name}: {done}/{total} terminal ({status})")
        if pending > 0:
            all_done = False

    print("\n".join(lines))
    print()
    if all_done:
        print("ALL_COMPLETE")
        return 0
    else:
        print("NOT_COMPLETE")
        return 1


if __name__ == "__main__":
    sys.exit(main())
