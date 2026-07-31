# Stops both collector scheduled tasks AND cleans up their process trees
# properly - real incident 2026-07-25: force-killing just the main collector
# process (via Stop-Process on the python.exe running collect_raw_transcripts.py
# or podcast_collector.py) does NOT clean up its ProcessPoolExecutor worker
# children. Each worker still holds a loaded Whisper model in memory
# (hundreds of MB to ~1GB+), so repeated restarts using only a parent-process
# kill silently leaked memory across the session - traced to a machine with
# only 15.6GB RAM going from healthy to 0.5GB free (99.9% of collection
# attempts then failing with "process pool terminated abruptly", i.e. Windows
# killing workers under memory pressure) after about 5 restart cycles in one
# session. ALWAYS use this script to stop the collectors, not an ad-hoc
# Stop-Process on just the main process.

Stop-ScheduledTask -TaskName 'HealthVault-YouTubeQueue-Loop' -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName 'HealthVault-PodcastQueue-Loop' -ErrorAction SilentlyContinue

$mainPattern = 'run-youtube-queue-loop|run-podcast-queue-loop|collect_raw_transcripts|podcast_collector|fetch_transcript_auto|whisper_transcribe'
$mainProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $mainPattern -and $_.Name -match 'powershell|python|yt-dlp' }
foreach ($p in $mainProcs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }

# The critical step this script exists for: orphaned ProcessPoolExecutor
# workers don't have the script name in their command line anymore (they're
# relaunched via multiprocessing's own spawn bootstrap) - match on that
# bootstrap signature instead.
$orphans = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spawn_main*' }
foreach ($p in $orphans) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }

# whisper-cli.exe (added 2026-07-27 when whisper.cpp replaced faster-whisper -
# see buglog.md) is a plain subprocess.run() child, not a multiprocessing
# worker, so it has neither the main-process command-line patterns above nor
# the spawn_main signature - killing its python.exe parent does NOT kill it.
# Found this the hard way: this script reported "stopped" while two
# whisper-cli.exe processes from well before the stop kept running for over
# 40 minutes afterward, silently invalidating a controlled thread-count test.
# Always kill these explicitly by name whenever collectors are stopped.
$whisperProcs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'whisper-cli.exe' }
foreach ($p in $whisperProcs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2

Remove-Item 'C:\Users\RossW\Projects\Health\Research\YouTube\Raw\.collector.lock' -ErrorAction SilentlyContinue
Remove-Item 'C:\Users\RossW\Projects\Health\Research\Podcasts\Raw\.collector.lock' -ErrorAction SilentlyContinue

Write-Host "Stopped $($mainProcs.Count) main process(es), $($orphans.Count) orphaned worker(s), and $($whisperProcs.Count) whisper-cli.exe process(es)."
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='FreeGB';e={[math]::Round($_.FreePhysicalMemory/1MB,1)}}
