#!/usr/bin/env python3
"""Option B fallback downloader: when yt-dlp fails a video with an anti-bot
error even after Option A's cookie refresh, load the video in a real
Playwright browser context (the seeded profile from playwright_cookie_refresh.py)
and capture the audio-track network response directly, rather than
reimplementing YouTube's player/cipher logic ourselves.

Real scope decision: YouTube's player resolves signed, ciphered stream URLs
that change with player-version updates - re-deriving those URLs ourselves
(what a from-scratch scraper would need) is a significant, ongoing
maintenance burden, which is exactly the job yt-dlp's own large community
already does continuously. Instead of doing that work, this script lets a
REAL browser do the resolving (it has to, to play the video at all) and
just captures the resulting audio response bytes via Playwright's network
listener - a much smaller, more durable surface than re-deriving URLs.

Usage:
    python scripts/playwright_audio_fallback.py <video_id> <output_mp3_path>

Exit code 0 + file written on success, non-zero + no file on failure (mirrors
whisper_transcribe.py's existing yt-dlp download step's contract, so it can
be swapped in as a fallback without changing the caller's error handling).

Status: prototype for direct comparison against Option A - not yet wired
into the production collector. Run manually against real currently-failing
video IDs to see which approach actually clears the "Sign in to confirm
you're not a bot" block, then decide whether to deploy this as an automatic
fallback tier or as a manual-only escape hatch for stubborn failures.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VAULT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = VAULT_ROOT / ".playwright_profile"

# YouTube serves audio via googlevideo.com URLs with a 'mime' param identifying
# the track type - filtering on this in the response listener, rather than
# trying to predict the exact request URL shape in advance, is what makes this
# robust to YouTube changing its internal request patterns.
AUDIO_MIME_MARKERS = ("audio/webm", "audio/mp4")


def fetch_audio(video_id: str, output_path: Path, timeout_ms: int = 45000) -> bool:
    if not PROFILE_DIR.exists():
        print("No seeded Playwright profile found - run playwright_cookie_refresh.py --seed first.",
              file=sys.stderr)
        return False

    captured = {"body": None, "mime": None}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = context.new_page()

        def on_response(response):
            if captured["body"] is not None:
                return  # already got what we need
            ctype = response.headers.get("content-type", "")
            if "googlevideo.com" in response.url and any(m in ctype for m in AUDIO_MIME_MARKERS):
                try:
                    captured["body"] = response.body()
                    captured["mime"] = ctype
                except Exception:
                    pass  # response may have been evicted/aborted - just skip it, keep listening

        page.on("response", on_response)
        try:
            page.goto(f"https://www.youtube.com/watch?v={video_id}", timeout=timeout_ms, wait_until="domcontentloaded")
            # Playback has to actually start for the audio stream request to fire -
            # a loaded-but-paused player won't request media segments.
            try:
                page.click("button.ytp-large-play-button", timeout=5000)
            except Exception:
                pass  # may already be autoplaying, or button not present in this UI state
            page.wait_for_timeout(8000)  # give the audio request time to fire and resolve
        except Exception as e:
            print(f"Playback/navigation failed for {video_id}: {e}", file=sys.stderr)
        finally:
            context.close()

    if captured["body"] is None:
        print(f"No audio response captured for {video_id} - block likely still in effect, "
              f"or playback never started.", file=sys.stderr)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(captured["body"])
    print(f"Captured {len(captured['body'])} bytes ({captured['mime']}) -> {output_path}")
    return True


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: playwright_audio_fallback.py <video_id> <output_path>", file=sys.stderr)
        return 2
    video_id, output_path = sys.argv[1], Path(sys.argv[2])
    return 0 if fetch_audio(video_id, output_path) else 1


if __name__ == "__main__":
    sys.exit(main())
