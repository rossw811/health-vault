"""Linux port of scripts/reap_orphans.ps1, added 2026-08-15 as part of the
two-machine migration (see NEW-MACHINE-SETUP.md). The Windows .ps1 stays as-is
for the Windows side; CachyOS has no PowerShell, so this is a real port using
psutil rather than a copy-paste translation.

Same safety properties as the original: only kills a worker whose PARENT is
confirmed dead - a healthy running collector's own workers are never touched.
Designed to run frequently/automatically (unlike stop_collectors.py, which
stops everything including healthy collectors).

Usage:
    python scripts/reap_orphans.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import psutil

VAULT_ROOT = Path(__file__).resolve().parent.parent
EXCLUSION_FILE = VAULT_ROOT / "Research" / "YouTube" / ".state" / "_excluded-channels.json"
LOG_FILE = VAULT_ROOT / "Logs" / "reap-orphans.log"


def parent_is_alive(parent_pid: int) -> bool:
    try:
        psutil.Process(parent_pid)
        return True
    except psutil.NoSuchProcess:
        return False


def reap_spawn_main_orphans() -> tuple[int, int]:
    """Same spawn_main-bootstrap-signature check as the original .ps1 -
    a ProcessPoolExecutor worker's own command line embeds its parent_pid,
    so this doesn't need /proc's ppid (which changes if the worker gets
    reparented to init on parent death, making the true original parent
    unrecoverable from ppid alone - the embedded parent_pid is the reliable
    source of truth here)."""
    checked = 0
    killed = 0
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "spawn_main" not in cmdline:
            continue
        checked += 1
        match = re.search(r"parent_pid=(\d+)", cmdline)
        if not match:
            continue
        parent_pid = int(match.group(1))
        if not parent_is_alive(parent_pid):
            try:
                proc.kill()
                killed += 1
            except psutil.NoSuchProcess:
                pass
    return checked, killed


def reap_whisper_cli_orphans() -> tuple[int, int]:
    """whisper-cli (Linux binary name, no .exe) is a plain subprocess child
    with no spawn_main signature - same real orphan risk documented in the
    original .ps1 (2026-07-27 incident, ~860MB held by an orphaned worker).
    Uses the real OS-level parent-pid relationship (psutil's own .ppid()),
    not command-line parsing, matching the original's ParentProcessId check."""
    checked = 0
    killed = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"] or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name != "whisper-cli":
            continue
        checked += 1
        try:
            parent_pid = proc.ppid()
        except psutil.NoSuchProcess:
            continue
        if not parent_is_alive(parent_pid):
            try:
                proc.kill()
                killed += 1
            except psutil.NoSuchProcess:
                pass
    return checked, killed


def fix_invalid_exclusions() -> int:
    """Same self-correcting guard as the original - age/inactivity must never
    be a valid channel-exclusion reason (CLAUDE.md's Source quality section,
    stated explicitly twice by the user). If one is ever found, remove it
    automatically rather than waiting for manual discovery."""
    if not EXCLUSION_FILE.exists():
        return 0
    try:
        data = json.loads(EXCLUSION_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0

    fixed = 0
    cleaned = {}
    for channel, entry in data.items():
        if isinstance(entry, dict) and entry.get("reason") == "inactive":
            fixed += 1
        else:
            cleaned[channel] = entry

    if fixed > 0:
        EXCLUSION_FILE.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return fixed


def main() -> int:
    checked1, killed1 = reap_spawn_main_orphans()
    checked2, killed2 = reap_whisper_cli_orphans()
    exclusion_fixed = fix_invalid_exclusions()

    total_checked = checked1 + checked2
    total_killed = killed1 + killed2

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = (
        f"{timestamp} - checked {total_checked} worker process(es), "
        f"killed {total_killed} orphan(s), removed {exclusion_fixed} invalid exclusion(s)"
    )
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")
    print(log_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
