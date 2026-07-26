"""Local fallback transcription for YouTube videos when youtube-transcript-api /
yt-dlp's caption endpoint is IP-blocked.

Downloads only the audio track (confirmed NOT subject to the caption-endpoint
IP block - see buglog.md 2026-07-22) via yt-dlp, then transcribes it locally
with faster-whisper. Produces our own derivative transcript from audio we
legitimately downloaded, rather than depending on any third party's transcript
redistribution (which carries real, demonstrated legal risk - see buglog.md).

Usage:
    python scripts/whisper_transcribe.py <video_id_or_url> [--model small]

Prints the transcript to stdout. Cleans up the downloaded audio file when done
(pass --keep-audio to retain it for debugging).
"""

from __future__ import annotations

import os

# Must be set before faster_whisper/ctranslate2 loads its native OpenMP libs -
# an unattended/scheduled process doesn't inherit this from an interactive
# shell where it was exported manually (same PATH-independence issue as
# find_ffmpeg_dir() below - see CLAUDE.md "Always test whatever is built").
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_ffmpeg_dir() -> str | None:
    """Locate the directory containing ffmpeg without relying on PATH.

    A scheduled/unattended process does not inherit an interactive shell's PATH
    additions (see CLAUDE.md "Always test whatever is built" - this is the exact
    failure mode that rule was written for: ffmpeg installed via winget resolved
    fine in an interactive shell but not in the actual scheduled-task process,
    so yt-dlp's internal ffmpeg call silently failed there). Check PATH first
    (works once/if it's ever fixed system-wide), then fall back to scanning the
    winget install location directly.
    """
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    winget_packages = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.exists():
        matches = list(winget_packages.glob("*FFmpeg*/**/ffmpeg.exe"))
        if matches:
            return str(matches[0].parent)
    return None


# Categories removed via yt-dlp's SponsorBlock integration before transcription -
# real speedup (skip transcribing audio we'd discard anyway during note-writing's
# own ad-filtering pass) plus a small accuracy win (no sponsor-read text polluting
# the transcript). Deliberately conservative: only unambiguous promotional/filler
# content, never "intro"/"outro"/"music" which can carry real spoken content on
# some channels.
SPONSORBLOCK_CATEGORIES = "sponsor,selfpromo,interaction"


def download_audio(video_id_or_url: str, dest_dir: Path) -> Path:
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    out_template = str(dest_dir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "9",  # lowest usable quality - whisper doesn't need audiophile input, only faster download/decode
        "--sponsorblock-remove", SPONSORBLOCK_CATEGORIES,
        "-o", out_template,
    ]
    ffmpeg_dir = find_ffmpeg_dir()
    if ffmpeg_dir is None:
        raise RuntimeError("ffmpeg not found on PATH or in winget install location - install it or check the winget path")
    cmd += ["--ffmpeg-location", ffmpeg_dir, url]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp audio download failed: {result.stderr.strip()}")

    audio_files = list(dest_dir.glob("audio.*"))
    if not audio_files:
        raise RuntimeError("yt-dlp reported success but no audio file was found")
    return audio_files[0]


def load_model(model_size: str, cpu_threads: int = 4):
    """Load a batched-inference model once - the expensive part of each call.
    Callers that process many videos (the parallel worker pool in
    collect_raw_transcripts.py) should call this ONCE per worker process and
    reuse the returned pipeline, instead of reloading per video."""
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=cpu_threads)
    return BatchedInferencePipeline(model=model)


def transcribe(audio_path: Path, model_size: str = "small", batched_model=None, cpu_threads: int = 4) -> str:
    """Transcribe with VAD filtering (skips silence - real speedup on any video
    with pauses/intros) and batched inference (3-4x faster than the plain
    sequential decode faster-whisper defaults to). Pass a pre-loaded
    `batched_model` (from load_model()) to skip the ~2-5s model-load cost per
    call - critical when processing many videos back to back."""
    pipeline = batched_model or load_model(model_size, cpu_threads)
    segments, _info = pipeline.transcribe(str(audio_path), beam_size=5, vad_filter=True, batch_size=8)
    return " ".join(segment.text.strip() for segment in segments)


def transcribe_video(video_id_or_url: str, model_size: str = "small", batched_model=None,
                      cpu_threads: int = 4, keep_audio: bool = False) -> str:
    """End-to-end: download audio, transcribe. Importable for use inside a
    persistent worker (pass batched_model) or standalone (loads fresh)."""
    with tempfile.TemporaryDirectory(prefix="whisper_transcribe_") as tmp:
        tmp_dir = Path(tmp)
        audio_path = download_audio(video_id_or_url, tmp_dir)
        transcript = transcribe(audio_path, model_size, batched_model, cpu_threads)
        if keep_audio:
            kept_path = Path.cwd() / audio_path.name
            audio_path.replace(kept_path)
            print(f"(audio kept at {kept_path})", file=sys.stderr)
        return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="YouTube video ID or full URL")
    parser.add_argument(
        "--model", default="small",
        help="faster-whisper model size (tiny/base/small/medium/large-v3). "
             "Default 'small' balances speed and accuracy on CPU.",
    )
    parser.add_argument(
        "--keep-audio", action="store_true",
        help="Keep the downloaded audio file instead of deleting it after transcription",
    )
    args = parser.parse_args()

    try:
        transcript = transcribe_video(args.video, args.model, keep_audio=args.keep_audio)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any transcription failure plainly
        print(f"ERROR: transcription failed: {exc}", file=sys.stderr)
        return 1

    print(transcript)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
