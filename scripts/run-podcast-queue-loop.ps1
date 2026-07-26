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
$ffmpegDir    = "C:\Users\RossW\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"

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
    python scripts\podcast_collector.py 2>$stderrTmp | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    if (Test-Path $stderrTmp) {
        Get-Content $stderrTmp -ErrorAction SilentlyContinue | Add-Content $logFile
        Remove-Item $stderrTmp -ErrorAction SilentlyContinue
    }

    $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-LogAndHost "$timestamp2 - attempt $i finished, exit code $exitCode"

    Start-Sleep -Seconds $pauseSeconds
}
