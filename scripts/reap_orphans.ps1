# Safe, non-disruptive orphan cleanup - designed to run frequently/automatically
# (unlike scripts/stop-collectors.ps1, which stops EVERYTHING including healthy
# running collectors). This only kills spawn_main worker processes whose
# parent_pid is no longer alive - a legitimate running collector's own workers
# are never touched. Built 2026-07-26 as part of the zero-Claude-cost
# automation tier, directly motivated by the same-day incident where ~17
# orphaned ProcessPoolExecutor workers accumulated silently across several
# manual restarts and exhausted the machine's 15.6GB RAM before being caught.

$orphans = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*spawn_main*' }
$killedCount = 0
$checkedCount = 0

foreach ($p in $orphans) {
    $checkedCount++
    if ($p.CommandLine -match 'parent_pid=(\d+)') {
        $parentId = [int]$matches[1]
        $parentAlive = $null -ne (Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue)
        if (-not $parentAlive) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            $killedCount++
        }
    }
}

# Exclusion-list guard: age/inactivity must never be a valid exclusion reason
# (stated explicitly by the user, twice - see CLAUDE.md's Source quality section
# and feedback_no_age_based_exclusions.md). Self-correcting: if this is ever
# found, remove it automatically rather than waiting for manual discovery.
$exclusionFile = "C:\Users\RossW\Projects\Health\Research\YouTube\.state\_excluded-channels.json"
$exclusionFixed = 0
if (Test-Path $exclusionFile) {
    $raw = Get-Content $exclusionFile -Raw
    $data = $null
    try { $data = $raw | ConvertFrom-Json -ErrorAction Stop } catch { $data = $null }
    if ($data) {
        # PSCustomObject, not a hashtable (ConvertFrom-Json -AsHashtable isn't
        # available in this PowerShell 5.1 environment) - rebuild a clean object
        # from only the properties that should survive.
        $cleaned = New-Object PSObject
        foreach ($prop in $data.PSObject.Properties) {
            if ($prop.Value.reason -eq "inactive") {
                $exclusionFixed++
            } else {
                $cleaned | Add-Member -MemberType NoteProperty -Name $prop.Name -Value $prop.Value
            }
        }
        if ($exclusionFixed -gt 0) {
            $cleaned | ConvertTo-Json -Depth 10 | Set-Content $exclusionFile -Encoding utf8
        }
    }
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logLine = "$timestamp - checked $checkedCount worker process(es), killed $killedCount orphan(s), removed $exclusionFixed invalid exclusion(s)"
Add-Content "C:\Users\RossW\Projects\Health\Logs\reap-orphans.log" $logLine
Write-Host $logLine
