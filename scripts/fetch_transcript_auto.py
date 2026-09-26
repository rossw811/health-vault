"""Single entry point for transcript fetching - tries the fast official-caption
path first, silently falls back to local Whisper transcription if that fails.

This exists so the calling process (a `/youtube-channel` or `/youtube-queue` run)
never has to detect an IpBlocked/RequestBlocked/429 error and decide to switch
strategies itself - it just calls this one script and always gets a real
transcript back (or a clear failure if genuinely nothing is available), with a
marker on stderr saying which method actually produced it.

Usage:
    python scripts/fetch_transcript_auto.py <video_id_or_url> [--whisper-model small]

Prints the transcript to stdout on success. Prints which method was used, and
any fallback reasoning, to stderr (so stdout stays a clean transcript you can
redirect straight to a file). Exit code 0 on success, 1 if both methods failed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def find_skill_root() -> str:
    """Version-agnostic obsidian-second-brain plugin cache lookup, added
    2026-08-15 as part of the two-machine migration (see NEW-MACHINE-SETUP.md) -
    same pattern already proven for the ffmpeg winget-folder lookup in
    run-youtube-queue-loop.ps1 (2026-08-08 fix, see buglog.md): a hardcoded
    version-pinned path silently breaks on any plugin/package update, so scan
    for the actual installed version directory instead of assuming one. Uses
    Path.home() rather than a hardcoded OS-specific root so this resolves
    correctly on both this vault's Windows and CachyOS machines."""
    cache_root = Path.home() / ".claude" / "plugins" / "cache" / "obsidian-second-brain" / "obsidian-second-brain"
    if cache_root.exists():
        versions = sorted(cache_root.glob("*"), key=lambda p: p.name, reverse=True)
        if versions:
            return str(versions[0])
    # Last-known-good fallback if no version directory is found at all -
    # keeps this from hard-failing on a machine where the plugin cache
    # hasn't been populated yet, even though callers should expect this to
    # fail loudly downstream in that case (no directory to run uv against).
    return str(cache_root / "0.14.0")


SKILL_ROOT = find_skill_root()

BLOCKED_SIGNATURES = ("IpBlocked", "RequestBlocked", "429", "Too Many Requests")

# Real fix 2026-08-19: an anonymous (unauthenticated) request is far more
# rate-limit-prone than one attributable to a real logged-in account -
# confirmed live (Ross's own Firefox "HealthVaultYT" profile cookies let a
# yt-dlp request through cleanly while anonymous requests were 429/IpBlocked
# at the same moment). youtube-transcript-api takes an `http_client` (a
# requests.Session), not a cookies-file path directly, so cookies.txt
# (Netscape format, the same file yt-dlp's --cookies flag also uses) gets
# loaded into a Session via MozillaCookieJar and shared across every call.
COOKIES_FILE = Path.home() / "Health" / ".youtube_cookies.txt"


def _cookie_authenticated_session():
    """Returns a requests.Session with cookies loaded from COOKIES_FILE if it
    exists, otherwise a plain anonymous Session (graceful degradation - this
    machine's cookie file might not exist yet, or might expire/need
    refreshing; anonymous requests still work, just more rate-limit-prone)."""
    import http.cookiejar
    import requests

    session = requests.Session()
    if COOKIES_FILE.exists():
        jar = http.cookiejar.MozillaCookieJar(str(COOKIES_FILE))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = jar
        except Exception:  # noqa: BLE001 - a malformed/expired cookie file shouldn't crash the collector, just fall back to anonymous
            pass
    return session


def extract_video_id(video_id_or_url: str) -> str:
    if not video_id_or_url.startswith("http"):
        return video_id_or_url
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", video_id_or_url)
    if match:
        return match.group(1)
    return video_id_or_url


def try_official_captions(video_id: str) -> tuple[str | None, str]:
    """Returns (transcript_or_None, diagnostic_message).

    Real incident 2026-08-19 (CachyOS migration gap): this used to shell out
    via `uv run --directory SKILL_ROOT` into the obsidian-second-brain
    plugin's own youtube.py library - but that plugin was NEVER installed on
    the CachyOS machine (only on Windows), so SKILL_ROOT pointed at a
    directory that doesn't exist there. Every single video on CachyOS was
    silently forced through the much heavier whisper-fallback path (audio
    download + local transcription) since the 2026-08-15 migration - not
    because captions were unavailable, but because the lookup mechanism
    itself was broken. Confirmed via a live test: `find_skill_root()`
    resolved to a nonexistent path, causing an immediate "No such file or
    directory" failure on every call.

    Fixed by calling the `youtube-transcript-api` library directly (pip
    package, installed 2026-08-19 into this vault's own .venv) instead of
    routing through an external plugin's cache via a cross-process `uv run`
    call - removes an unnecessary fragile indirection (one less moving part:
    no dependency on a plugin cache existing, no cross-process subprocess
    call for what's fundamentally a library import) and works identically on
    both the Windows and CachyOS machines without any plugin-installation
    prerequisite. Same public signature and BLOCKED_SIGNATURES-based
    diagnostic-message convention preserved so callers (and their 429/
    IpBlocked detection logic) don't need to change."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import CouldNotRetrieveTranscript

    try:
        api = YouTubeTranscriptApi(http_client=_cookie_authenticated_session())
        fetched = api.fetch(video_id)
        text = " ".join(segment.text for segment in fetched)
        if text.strip():
            return text, "official captions"
        return None, "no captions available (empty transcript)"
    except CouldNotRetrieveTranscript as exc:
        msg = str(exc)
        if any(sig in msg for sig in BLOCKED_SIGNATURES) or type(exc).__name__ in BLOCKED_SIGNATURES:
            return None, f"blocked ({type(exc).__name__}: {msg[:200]})"
        return None, f"no captions available ({type(exc).__name__}: {msg[:200]})"
    except Exception as exc:  # noqa: BLE001 - report any unexpected failure plainly rather than crashing the worker
        return None, f"no captions available (unexpected {type(exc).__name__}: {str(exc)[:200]})"


def try_whisper_fallback(video_id: str, model: str) -> tuple[str | None, str]:
    script_path = Path(__file__).parent / "whisper_transcribe.py"
    result = subprocess.run(
        [sys.executable, str(script_path), video_id, "--model", model],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip(), "local whisper"
    return None, f"whisper fallback failed ({result.stderr.strip()[:200]})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="YouTube video ID or full URL")
    parser.add_argument("--whisper-model", default="small", help="faster-whisper model size if fallback is needed")
    args = parser.parse_args()

    video_id = extract_video_id(args.video)

    transcript, note = try_official_captions(video_id)
    if transcript:
        print(f"method: {note}", file=sys.stderr)
        sys.stdout.buffer.write(transcript.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return 0

    print(f"official captions unavailable: {note} - falling back to local whisper", file=sys.stderr)

    transcript, note = try_whisper_fallback(video_id, args.whisper_model)
    if transcript:
        print(f"method: {note}", file=sys.stderr)
        sys.stdout.buffer.write(transcript.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return 0

    print(f"ERROR: both transcript methods failed - {note}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
