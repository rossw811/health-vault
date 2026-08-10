# Repeatedly invokes the podcast collector (pure Python, zero Claude
# dependency - mirrors scripts/run-youtube-queue-loop.ps1's pattern exactly)
# until the podcast queue has no unchecked feeds left. Each "attempt" is a
# full pass through every remaining feed line (podcast_collector.py's own
# main() already walks the whole queue), so this wrapper exists mainly for
# resilience against a crash/transient network error.

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\RossW\Projects\Health"

$logFile      = "C:\Users\RossW\Projects\Health\Logs\podcast-queue-loop.log"
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
    $content = Get-Content "Podcast Queue.md" -Raw
    return ([regex]::Matches($content, '(?m)^- \[ \]')).Count
}

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

    Write-LogAndHost "$timestamp - attempt $i starting (podcast collector, no Claude), $remaining unchecked feed line(s) remaining"

    # Same PowerShell 5.1 stderr-wrapping gotcha as the YouTube loop - never
    # use `2>&1` on a native executable, redirect stderr to its own file instead.
    $stderrTmp = "$logFile.stderr.tmp"
    # --parallel 1, 2026-07-26: same memory-pressure fix as run-youtube-queue-loop.ps1 -
    # this machine hit 0GB free with both collectors running 2 workers each (4 Whisper
    # models loaded concurrently), which was directly causing worker OOM-crashes.
    # --cpu-threads 4, 2026-07-27: see the matching comment in
    # run-youtube-queue-loop.ps1 - the whisper.cpp engine swap made the old
    # "split 12 cores 6/6" assumption stale and actually wrong; a controlled
    # 2-concurrent-process sweep found 4 threads/process as the true optimum
    # (127s/152s vs. 6/6's 260s/284s on identical test clips), not 6.
    python scripts\podcast_collector.py --parallel 1 --cpu-threads 4 2>$stderrTmp | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    if (Test-Path $stderrTmp) {
        Get-Content $stderrTmp -ErrorAction SilentlyContinue | Add-Content $logFile
        Remove-Item $stderrTmp -ErrorAction SilentlyContinue
    }

    $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-LogAndHost "$timestamp2 - attempt $i finished, exit code $exitCode"

    Start-Sleep -Seconds $pauseSeconds
}
