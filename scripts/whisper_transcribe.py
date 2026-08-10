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
        # Real incident 2026-07-26: a yt-dlp update now requires executing a JS
        # challenge to get a playable format, and only auto-detects "deno" for
        # that - deno isn't installed on this machine, so every single audio
        # download failed with "No supported JavaScript runtime could be found"
        # (this Whisper fallback path was completely non-functional, not just
        # slow, for the whole time this went unnoticed). Node.js IS already
        # installed here (C:\Program Files\nodejs) - telling yt-dlp to use it
        # explicitly fixes this without installing anything new.
        "--js-runtimes", "node",
        # Real incident 2026-07-27: intermittent "403 Forbidden"/"Requested
        # format is not available" failures traced (via isolated flag-by-flag
        # testing, including ruling out an authenticated-cookies path as
        # unnecessary) to yt-dlp needing an updated JS challenge-solver script
        # it doesn't bundle by default - this flag lets it download that
        # component (from yt-dlp's own GitHub releases) on demand. Confirmed
        # this alone (no cookies needed) turns a real previously-failing video
        # back into a successful download.
        "--remote-components", "ejs:github",
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


# whisper.cpp engine (swapped in 2026-07-27, replacing faster-whisper/CTranslate2 -
# see buglog.md 2026-07-27 for the full A/B testing history behind this change).
# Built from source (ggml-org/whisper.cpp, CMake+clang, arm64-windows-llvm-release
# preset) since no official Windows ARM64 build exists; native ARM64 confirmed via
# its own system_info banner (NEON/ARM_FMA/MATMUL_INT8/DOTPROD all 1). Rigorously
# A/B tested against the CTranslate2 baseline on two independent samples with a
# systematic word-level diff (not just eyeballing): 95.4%/98.4% similarity vs.
# baseline, with remaining differences almost entirely cosmetic (filler-word
# capture, "cause"/"because" spelling) rather than dropped content - the one real
# miss (a 2-word "motivation, discipline" omission on sample 2) was judged an
# acceptable, isolated ASR variance rather than a systematic quality regression.
# A parallel same-night attempt at NPU-accelerated inference (Qualcomm QNN
# execution provider, hand-rolled beam search against precompiled ONNX models)
# was rejected instead: despite being faster in naive greedy mode, even with
# proper beam search it was both slower than whisper.cpp AND measurably less
# accurate (93-94% similarity, with real dropped clauses like "and then to
# practice not eating, which they call fasting" vanishing entirely) - not
# deployed. See buglog.md for the complete comparison.
WHISPER_CPP_DIR = Path.home() / "AppData" / "Local" / "HealthVault-Tools" / "whisper-cpp"
WHISPER_CPP_BIN = WHISPER_CPP_DIR / "build-arm64-windows-llvm-release" / "bin" / "whisper-cli.exe"
WHISPER_CPP_MODELS = {"small": WHISPER_CPP_DIR / "models" / "ggml-small.bin"}


def load_model(model_size: str, cpu_threads: int = 4):
    """whisper.cpp has no persistent in-process model object to preload - the
    model lives in a separate compiled binary invoked per call via subprocess.
    Returns a lightweight config dict so callers' existing call pattern (load
    once per worker, pass the result to transcribe()) still works cheaply, and
    fails fast here (once per worker) rather than on the first real video if the
    binary/model got moved."""
    if not WHISPER_CPP_BIN.exists():
        raise RuntimeError(f"whisper.cpp binary not found at {WHISPER_CPP_BIN}")
    if model_size not in WHISPER_CPP_MODELS:
        raise RuntimeError(f"no whisper.cpp model file configured for size {model_size!r} - only {list(WHISPER_CPP_MODELS)} tested/validated so far")
    if not WHISPER_CPP_MODELS[model_size].exists():
        raise RuntimeError(f"whisper.cpp model not found at {WHISPER_CPP_MODELS[model_size]}")
    return {"model_size": model_size, "cpu_threads": cpu_threads}


def transcribe(audio_path: Path, model_size: str = "small", batched_model=None, cpu_threads: int = 4) -> str:
    """Transcribe via whisper.cpp's whisper-cli.exe (native ARM64, NPU-adjacent
    NEON/DOTPROD/MATMUL_INT8 kernels). beam_size=5 matches the CTranslate2
    baseline's setting (the A/B testing above was done at this setting - do not
    lower it without re-running that comparison, per the standing "revert ASAP
    on any quality change" rule). Thread count is passed through from the
    caller rather than hardcoded here - a controlled 2-concurrent-process sweep
    (2026-07-27, see buglog.md) found 4 threads/process as the true optimum
    under the real deployment topology (both collectors running at once), a
    clear parabolic minimum (4: 127s/152s: better than both 3 and 2 threads,
    and dramatically better than 6/8, which suffer severe thread-contention
    thrashing well before this hardware's 12 cores are actually saturated) -
    the wrapper scripts (run-youtube-queue-loop.ps1/run-podcast-queue-loop.ps1)
    pass 4, not the 8-threads-found-optimal-in-isolation number from the
    original single-process test. Do not assume "more threads / evenly split
    cores" without re-running that sweep if this ever needs revisiting."""
    cfg = batched_model or load_model(model_size, cpu_threads)
    threads = cfg.get("cpu_threads", cpu_threads)
    model_path = WHISPER_CPP_MODELS[cfg.get("model_size", model_size)]

    with tempfile.TemporaryDirectory(prefix="whispercpp_out_") as tmp:
        out_prefix = str(Path(tmp) / "out")
        cmd = [
            str(WHISPER_CPP_BIN),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-bs", "5",
            "-t", str(threads),
            "--no-timestamps",
            "-otxt",
            "-of", out_prefix,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"whisper.cpp transcription failed: {result.stderr.strip()}")
        out_file = Path(out_prefix + ".txt")
        if not out_file.exists():
            raise RuntimeError("whisper.cpp reported success but produced no output file")
        return out_file.read_text(encoding="utf-8").strip()


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
        help="whisper.cpp model size - only 'small' is currently downloaded/supported "
             "(see WHISPER_CPP_MODELS). Corrected 2026-08-08 - this used to list "
             "faster-whisper's tiny/base/small/medium/large-v3 options, stale since the "
             "2026-07-27 engine swap to whisper.cpp.",
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
