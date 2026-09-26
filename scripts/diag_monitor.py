#!/usr/bin/env python3
"""Lightweight resource-state sampler for active freeze/MCE diagnosis
(deployed 2026-08-20). Every crashed boot tonight has one thing in common:
the journal goes completely silent at the moment of the freeze - no OOM
message, no panic, sometimes no kernel message at all. This means we have
zero visibility into system state in the seconds leading up to a freeze.

This script samples CPU/GPU temps, load average, memory, and per-process
CPU% every few seconds and appends to a log file, flushing after every line
so a hard freeze loses at most one sample, not the whole session. If it
freezes again, the last few lines of this log are the closest thing to a
black-box flight recorder we have - what temps/load/memory looked like right
before everything went silent.

Run as: python3 diag_monitor.py (foreground) or via the accompanying
systemd unit (healthvault-diag-monitor.service) for persistence across
reboots during the diagnosis window. Not meant to run forever - this is a
temporary diagnostic tool, remove once the freeze cause is confirmed.
"""
import subprocess
import time
from datetime import datetime
from pathlib import Path

LOG_FILE = Path.home() / "Health" / "Logs" / "diag-monitor.log"
SAMPLE_INTERVAL_SECONDS = 5


def read_temps() -> str:
    try:
        out = subprocess.run(["sensors", "-A"], capture_output=True, text=True, timeout=5).stdout
        pkg = next((l.split(":")[1].strip().split()[0] for l in out.splitlines() if "Package id 0" in l), "?")
        return pkg
    except Exception as e:
        return f"err({e})"


def read_load() -> str:
    try:
        return Path("/proc/loadavg").read_text().split()[0:3]
    except Exception as e:
        return [f"err({e})"]


def read_mem() -> str:
    try:
        out = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5).stdout
        line = [l for l in out.splitlines() if l.startswith("Mem:")][0].split()
        return f"used={line[2]}MB free={line[3]}MB avail={line[6]}MB"
    except Exception as e:
        return f"err({e})"


def read_gpu() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return out
    except Exception as e:
        return f"err({e})"


def read_top_cpu_procs(n: int = 3) -> str:
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,pcpu,comm", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=5,
        ).stdout.splitlines()[1:n + 1]
        return " | ".join(l.strip() for l in out)
    except Exception as e:
        return f"err({e})"


def main() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n=== diag-monitor started {datetime.now().isoformat()} ===\n")
        f.flush()
        while True:
            ts = datetime.now().isoformat(timespec="seconds")
            line = (
                f"{ts} cpu_pkg={read_temps()}C load={read_load()} "
                f"mem=[{read_mem()}] gpu=[{read_gpu()}] top=[{read_top_cpu_procs()}]\n"
            )
            f.write(line)
            f.flush()
            time.sleep(SAMPLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
