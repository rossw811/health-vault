"""Run the YouTube raw-transcript collector through the Windows laptop's
Tailscale exit node, in paced, watchdog-guarded windows. Added 2026-10-01.

Why: YouTube flagged CachyOS's public IP as a bot ("Sign in to confirm you're
not a bot" even with fresh logged-in cookies and current yt-dlp), and no
YouTube transcript was collected from 2026-09-13 to 2026-10-01. The same
videos download fine from the Windows laptop's IP. Ross approved routing
YouTube collection through it.

Safety design - the laptop sleeps, and its IP is also Ross's own browsing IP:
  - The exit node is set ONLY for a collection window and cleared afterwards,
    so CachyOS's other traffic (podcast collector, pulls) is direct the rest
    of the time.
  - Before each window: the laptop must answer `tailscale ping`, and the
    public egress IP must actually change after switching - otherwise skip.
  - During a window a watchdog pings the laptop every 20 s; on any failure
    the exit node is cleared immediately and the collector's whole process
    group is terminated (killing only the parent orphans ProcessPool workers
    - see CLAUDE.md's automated-maintenance lessons).
  - Paced: 1 worker, WINDOW_MIN on / GAP_MIN off. If any new failure in a
    window mentions YouTube's bot check, cool down COOLDOWN_H hours rather
    than risk getting the laptop's IP flagged too.

Needs (one-time, Ross): `sudo tailscale set --operator=rw` on CachyOS and
the laptop approved as an exit node in the Tailscale admin console.

Usage: python scripts/youtube_via_exit_node.py   (runs forever; systemd unit
healthvault-youtube-via-windows.service)
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
RAW = VAULT / "Research" / "YouTube" / "Raw"
LOG = VAULT / "Logs" / "youtube-via-exit-node.log"
EXIT_NODE = os.environ.get("YT_EXIT_NODE", "")  # Tailscale IP of the exit-node machine (set in the unit/.env)
WINDOW_MIN, GAP_MIN, COOLDOWN_H = 30, 30, 12
WATCHDOG_S = 20


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def ts(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["tailscale", *args], capture_output=True, text=True, timeout=timeout)


def peer_up() -> bool:
    try:
        return ts("ping", "-c", "1", "--timeout", "5s", EXIT_NODE, timeout=15).returncode == 0
    except Exception:
        return False


def public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as r:
            return r.read().decode().strip()
    except Exception:
        return ""


def set_exit(on: bool) -> bool:
    args = ["set", f"--exit-node={EXIT_NODE if on else ''}"]
    if on:
        args.append("--exit-node-allow-lan-access=true")
    r = ts(*args)
    if r.returncode != 0:
        log(f"tailscale set failed ({'on' if on else 'off'}): {r.stderr.strip()[:200]}")
    return r.returncode == 0


def failures_snapshot() -> dict:
    try:
        d = json.loads((RAW / ".collected_ids.json").read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if isinstance(v, dict) and v.get("status") == "failed"}
    except Exception:
        return {}


def run_window(direct_ip: str) -> str:
    """Returns 'ok', 'skipped', 'peer-lost' or 'botcheck'."""
    if not peer_up():
        log("laptop not reachable - skipping window")
        return "skipped"
    if not set_exit(True):
        return "skipped"
    try:
        time.sleep(5)
        ip = public_ip()
        if not ip or ip == direct_ip:
            log(f"egress IP did not change ({ip or 'none'}) - not collecting")
            return "skipped"
        log(f"window start via exit node, egress {ip}")
        before = failures_snapshot()
        proc = subprocess.Popen(
            [sys.executable, str(VAULT / "scripts" / "collect_raw_transcripts.py"), "--parallel", "1", "--cpu-threads", "4"],
            cwd=VAULT, start_new_session=True)
        end = time.time() + WINDOW_MIN * 60
        outcome = "ok"
        while time.time() < end and proc.poll() is None:
            time.sleep(WATCHDOG_S)
            if not peer_up():
                log("laptop dropped mid-window - clearing exit node and stopping collector")
                set_exit(False)
                outcome = "peer-lost"
                break
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        after = failures_snapshot()
        new = [v for k, v in after.items() if k not in before or after[k] != before.get(k)]
        bot = [v for v in new if "not a bot" in str(v.get("reason", ""))]
        log(f"window end: {outcome}, new/updated failures {len(new)}, bot-check {len(bot)}")
        return "botcheck" if bot else outcome
    finally:
        set_exit(False)


def main() -> int:
    if not EXIT_NODE:
        log("YT_EXIT_NODE not set - nothing to do")
        return 2
    set_exit(False)
    direct_ip = public_ip()
    log(f"=== youtube_via_exit_node starting; direct egress {direct_ip}, exit node {EXIT_NODE}")
    while True:
        result = run_window(direct_ip)
        if result == "botcheck":
            log(f"YouTube bot check seen through the laptop - cooling down {COOLDOWN_H} h to protect its IP")
            time.sleep(COOLDOWN_H * 3600)
        elif result == "skipped":
            time.sleep(10 * 60)
        else:
            time.sleep(GAP_MIN * 60)


if __name__ == "__main__":
    sys.exit(main())
