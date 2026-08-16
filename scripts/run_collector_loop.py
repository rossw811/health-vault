"""Cross-platform replacement for run-youtube-queue-loop.ps1/run-podcast-queue-loop.ps1,
added 2026-08-15 as part of the two-machine migration (see NEW-MACHINE-SETUP.md).

The original .ps1 wrappers' actual logic is thin - call the Python collector
in a loop, log, sleep, cap at 50 attempts, stop early once the queue is fully
processed - but they're PowerShell-specific and CachyOS has no PowerShell.
Rather than hand-maintain a separate .sh implementation that would drift from
the Windows version over time, this one script replaces both: same behavior,
same log format, works on either machine.

Usage:
    python scripts/run_collector_loop.py youtube
    python scripts/run_collector_loop.py podcast
"""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
IS_LINUX = platform.system() == "Linux"

TARGETS = {
    "youtube": {
        "queue_file": VAULT_ROOT / "YouTube Queue.md",
        "log_file": VAULT_ROOT / "Logs" / "youtube-queue-loop.log",
        "script": VAULT_ROOT / "scripts" / "collect_raw_transcripts.py",
        "label": "raw collector, no Claude",
    },
    "podcast": {
        "queue_file": VAULT_ROOT / "Podcast Queue.md",
        "log_file": VAULT_ROOT / "Logs" / "podcast-queue-loop.log",
        "script": VAULT_ROOT / "scripts" / "podcast_collector.py",
        "label": "podcast collector, no Claude",
    },
}

MAX_ATTEMPTS = 50
PAUSE_SECONDS = 15

# --parallel worker count: the Windows machine runs --parallel 1 (down from
# the collector's own default of 2) specifically because of a real 2026-07-26
# memory-pressure incident (see buglog.md) - running both collectors' workers
# concurrently on that machine's 15.6GB RAM, each loading a CPU-resident
# Whisper model, drove it to 0GB free and caused ProcessPoolExecutor OOM
# crashes. That constraint doesn't hold on CachyOS: whisper.cpp's CUDA build
# keeps the model in GPU VRAM (measured 487MB per process, verified
# 2026-08-15), not system RAM, and this machine has 46GB RAM / 16GB VRAM with
# 43GB/15.8GB free while both collector loops were already running.
# --parallel 3 is a real, deliberate increase given that headroom - not the
# collector's own bare default, and not left at the Windows-tuned 1.
PARALLEL_WORKERS = 1 if not IS_LINUX else 3


def get_unchecked_count(queue_file: Path) -> int:
    content = queue_file.read_text(encoding="utf-8")
    return len(re.findall(r"(?m)^- \[ \]", content))


def find_ffmpeg_dir() -> str | None:
    """Same discipline as whisper_transcribe.py's find_ffmpeg_dir() - PATH
    first, Windows-winget-location fallback only on Windows. On Linux ffmpeg
    is a normal system package already on PATH, so this is a no-op there."""
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    if IS_LINUX:
        return None
    winget_packages = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.exists():
        matches = list(winget_packages.glob("*FFmpeg*/**/ffmpeg.exe"))
        if matches:
            return str(matches[0].parent)
    return None


def write_log(log_file: Path, message: str) -> None:
    print(message)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["youtube", "podcast"])
    args = parser.parse_args()

    cfg = TARGETS[args.target]
    cfg["log_file"].parent.mkdir(parents=True, exist_ok=True)

    import os

    env = os.environ.copy()
    ffmpeg_dir = find_ffmpeg_dir()
    if ffmpeg_dir:
        env["PATH"] = f"{ffmpeg_dir}{os.pathsep}{env.get('PATH', '')}"
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    for i in range(1, MAX_ATTEMPTS + 1):
        remaining = get_unchecked_count(cfg["queue_file"])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if remaining == 0:
            write_log(cfg["log_file"], f"{timestamp} - queue fully processed, stopping loop (checked before attempt {i})")
            break

        write_log(cfg["log_file"], f"{timestamp} - attempt {i} starting ({cfg['label']}), {remaining} unchecked line(s) remaining")

        # --cpu-threads 4 verified 2026-08-15 via a real controlled sweep on
        # this exact CPU (i7-10700K) - 2/4/8/16 threads measured 5.59s/5.13s/
        # 5.48s/6.84s on an identical real audio clip, confirming 4 remains
        # the true optimum here too, not just blindly ported from the
        # original ARM machine's own separate sweep. PARALLEL_WORKERS is
        # platform-aware - see its own definition above for the real
        # measured reasoning (Windows RAM-constrained, CachyOS GPU-backed).
        result = subprocess.run(
            [sys.executable, str(cfg["script"]), "--parallel", str(PARALLEL_WORKERS), "--cpu-threads", "4"],
            cwd=str(VAULT_ROOT),
            env=env,
        )

        timestamp2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_log(cfg["log_file"], f"{timestamp2} - attempt {i} finished, exit code {result.returncode}")

        time.sleep(PAUSE_SECONDS)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
