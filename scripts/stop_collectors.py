"""Linux port of scripts/stop-collectors.ps1, added 2026-08-15 as part of the
two-machine migration (see NEW-MACHINE-SETUP.md). Stops EVERYTHING, including
healthy running collectors - for routine health checks use reap_orphans.py
instead, which only touches confirmed-dead-parent orphans.

Real incident this exists to prevent (2026-07-25, documented in the original
.ps1): force-killing just the main collector process does NOT clean up its
ProcessPoolExecutor worker children, each still holding a loaded Whisper
model in memory. ALWAYS use this script to stop the collectors, never an
ad-hoc kill of just the main process.

Usage:
    python scripts/stop_collectors.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import psutil

VAULT_ROOT = Path(__file__).resolve().parent.parent

MAIN_PATTERN = "|".join([
    "run_collector_loop",
    "collect_raw_transcripts",
    "podcast_collector",
    "fetch_transcript_auto",
    "whisper_transcribe",
])

SYSTEMD_UNITS = [
    "healthvault-youtube-loop.service",
    "healthvault-podcast-loop.service",
]


def stop_systemd_units() -> None:
    for unit in SYSTEMD_UNITS:
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True)


def kill_matching(pattern_check) -> int:
    killed = 0
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            name = proc.info["name"] or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if pattern_check(cmdline, name):
            try:
                proc.kill()
                killed += 1
            except psutil.NoSuchProcess:
                pass
    return killed


def main() -> int:
    stop_systemd_units()

    import re

    main_killed = kill_matching(
        lambda cmdline, name: bool(re.search(MAIN_PATTERN, cmdline))
    )

    # Orphaned ProcessPoolExecutor workers don't have the script name in their
    # command line anymore (relaunched via multiprocessing's own spawn
    # bootstrap) - match on that bootstrap signature instead, same as
    # reap_orphans.py.
    orphan_killed = kill_matching(lambda cmdline, name: "spawn_main" in cmdline)

    # whisper-cli (Linux binary name) - plain subprocess child, no spawn_main
    # signature, doesn't have the script name in its command line either.
    whisper_killed = kill_matching(lambda cmdline, name: name == "whisper-cli")

    for lock_file in [
        VAULT_ROOT / "Research" / "YouTube" / "Raw" / ".collector.lock",
        VAULT_ROOT / "Research" / "Podcasts" / "Raw" / ".collector.lock",
    ]:
        lock_file.unlink(missing_ok=True)

    print(
        f"Stopped {main_killed} main process(es), {orphan_killed} orphaned worker(s), "
        f"and {whisper_killed} whisper-cli process(es)."
    )
    mem = psutil.virtual_memory()
    print(f"FreeGB: {round(mem.available / (1024**3), 1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
