# Repeatedly invokes the raw-transcript collector (pure Python, zero Claude
# dependency) until the queue has no unchecked lines left. Switched over from
# calling `claude -p "/youtube-queue"` because that consumes Claude session
# budget for every single video (transcript fetch + full note-writing) - this
# version only fetches metadata + transcript and saves raw "_full.txt" files,
# with no note-writing/relevance-judgment/concept-linking at all. A future
# Claude session processes those raw files into real AI-first notes without
# re-fetching anything.
#
# Each "attempt" here is a full pass through every remaining queue line (the
# script's own main() loop already walks the whole queue), so this wrapper
# exists mainly for resilience against a crash/transient network error, not
# to work around a rate limit the way the old claude-based version did.

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\RossW\Projects\Health"

$logFile      = "C:\Users\RossW\Projects\Health\Logs\youtube-queue-loop.log"
$maxAttempts  = 50
$pauseSeconds = 15

# Version-agnostic ffmpeg lookup, added 2026-08-08 (was a version-pinned path
# to ffmpeg-8.1.2-full_build - a winget auto-update to a newer ffmpeg version
# changes that folder name and silently breaks PATH injection here, with
# nothing surfacing the failure until a run needs ffmpeg and can't find it).
# Falls back to the last-known pinned path if no match is found, so an
# already-working machine doesn't regress if the winget package layout ever
# changes shape entirely.
$ffmpegPackageRoot = "C:\Users\RossW\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
$ffmpegDir = $null
if (Test-Path $ffmpegPackageRoot) {
    $latest = Get-ChildItem $ffmpegPackageRoot -Directory -Filter "ffmpeg-*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if ($latest) { $ffmpegDir = Join-Path $latest.FullName "bin" }
}
if (-not $ffmpegDir -or -not (Test-Path $ffmpegDir)) {
    $ffmpegDir = "C:\Users\RossW\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
}

$env:PATH = "$ffmpegDir;$env:PATH"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"

function Get-UncheckedCount {
    $content = Get-Content "YouTube Queue.md" -Raw
    return ([regex]::Matches($content, '(?m)^- \[ \]')).Count
}

# Helper function to write to both console and log file
function Write-LogAndHost ($message) {
    Write-Host $message
    Add-Content $logFile $message
}

for ($i = 1; $i -le $maxAttempts; $i++) {
    $remaining = Get-UncheckedCount
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if ($remaining -eq 0) {
        Write-LogAndHost "$timestamp - queue fully processed, stopping loop (checked before attempt $i)"
        break
    }

    Write-LogAndHost "$timestamp - attempt $i starting (raw collector, no Claude), $remaining unchecked line(s) remaining"

    # IMPORTANT: never use `2>&1` on a native executable (python.exe) in PowerShell 5.1 -
    # it wraps every stderr line in an ErrorRecord and can disrupt the pipeline, even
    # when the process itself succeeds. Redirect stderr to its own file instead, then
    # append it to the log afterward - stdout still streams live via Tee-Object.
    $stderrTmp = "$logFile.stderr.tmp"
    # --parallel 1 (down from the script's own default of 2), 2026-07-26: confirmed via
    # live memory check that running this collector's 2 workers alongside
    # podcast_collector.py's own 2 (4 Whisper "small" models loaded concurrently) drove
    # this 15.6GB machine to 0GB free, which was directly causing worker OOM-crashes that
    # then broke the whole ProcessPoolExecutor for the rest of that pass (see buglog.md).
    # Revert to 2 if this machine's other memory pressure eases or gets its own headroom.
    # --cpu-threads 4, 2026-07-27: the whisper.cpp engine swap (see buglog.md)
    # made the old --cpu-threads 6 ("split the 12 cores 6/6 with the podcast
    # collector") stale and, it turns out, actively wrong for this engine - a
    # controlled 2-concurrent-process sweep (this collector's exact real-world
    # condition: both collectors' whisper-cli.exe running at once) found a
    # clear parabolic curve with 4 threads/process as the true minimum: 4/4
    # threads finished a fixed pair of test clips in 127s/152s vs. 6/6's
    # 260s/284s and 8/8's 800s+ (severe thread-contention thrashing well before
    # full CPU saturation on this hardware). Do not "helpfully" split evenly
    # again without re-running that sweep - the old assumption doesn't hold.
    python scripts\collect_raw_transcripts.py --parallel 1 --cpu-threads 4 2>$stderrTmp | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    if (Test-Path $stderrTmp) {
        Get-Content $stderrTmp -ErrorAction SilentlyContinue | Add-Content $logFile
        Remove-Item $stderrTmp -ErrorAction SilentlyContinue
    }

    $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-LogAndHost "$timestamp2 - attempt $i finished, exit code $exitCode"

    Start-Sleep -Seconds $pauseSeconds
}