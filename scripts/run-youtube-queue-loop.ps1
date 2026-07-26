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
$ffmpegDir    = "C:\Users\RossW\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"

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
    python scripts\collect_raw_transcripts.py 2>$stderrTmp | Tee-Object -FilePath $logFile -Append
    $exitCode = $LASTEXITCODE
    if (Test-Path $stderrTmp) {
        Get-Content $stderrTmp -ErrorAction SilentlyContinue | Add-Content $logFile
        Remove-Item $stderrTmp -ErrorAction SilentlyContinue
    }

    $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-LogAndHost "$timestamp2 - attempt $i finished, exit code $exitCode"

    Start-Sleep -Seconds $pauseSeconds
}