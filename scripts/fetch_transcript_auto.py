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


def extract_video_id(video_id_or_url: str) -> str:
    if not video_id_or_url.startswith("http"):
        return video_id_or_url
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", video_id_or_url)
    if match:
        return match.group(1)
    return video_id_or_url


def try_official_captions(video_id: str) -> tuple[str | None, str]:
    """Returns (transcript_or_None, diagnostic_message)."""
    script = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from scripts.research.lib.youtube import get_transcript\n"
        "result = get_transcript(sys.argv[1])\n"
        "sys.stdout.buffer.write((result or '').encode('utf-8'))\n"
    )
    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        ["uv", "run", "--directory", SKILL_ROOT, "python", "-c", script, video_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    output = result.stdout.strip()
    diagnostics = result.stderr.strip()

    # BUG (found 2026-07-25): get_transcript() doesn't raise or return empty on
    # failure - it returns the error itself as a non-empty descriptive string
    # (e.g. "[YouTube transcript unavailable: IpBlocked: ...]"). The old check
    # here was just `if output:`, which happily accepted that error text as a
    # "successful" transcript and saved it to disk as if it were real content.
    # Must explicitly check the output ITSELF for failure signatures first.
    is_error_wrapped = output.startswith("[YouTube transcript unavailable") or any(
        sig in output for sig in BLOCKED_SIGNATURES
    )

    if output and not is_error_wrapped:
        return output, "official captions"

    combined = output + diagnostics
    if any(sig in combined for sig in BLOCKED_SIGNATURES):
        return None, f"blocked ({combined[:200]})"
    return None, f"no captions available ({combined[:200] or 'empty result'})"


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
