---
description: Update the whole local tool stack (yt-dlp, markitdown, oura-mcp, gh, the obsidian-second-brain plugin) and refresh every tracked YouTube channel with new videos since its last run. Logs everything to development.md.
category: meta
---

Execute `/vault-update`:

## 1. Update tools
Run each, capture output, don't abort the whole run if one fails — report and continue:
```bash
pip install --upgrade yt-dlp markitdown
npm update -g @daveremy/oura-mcp
claude plugin update obsidian-second-brain@obsidian-second-brain
```
Also check for a `gh` CLI update if the platform package manager is available (e.g. `winget upgrade --id GitHub.cli` on Windows); skip silently if not applicable. Note in the summary that `excel-mcp-server` and `mcp-local-rag`-equivalents run via `npx -y` so they always pull latest on next launch — no explicit update step needed for those.

## 2. Refresh tracked channels
List every `Research/YouTube/.state/*.json` file. For each one, read `channel_url` and re-run the full `/youtube-channel [channel_url]` flow (see `.claude/commands/youtube-channel.md`) — its own state-diffing means this naturally only processes videos published since the last run; already-processed video IDs are skipped automatically. If there are no state files yet, say so and skip this section (nothing to refresh until at least one channel has been ingested once).

## 3. Check the raw-transcript collector's health
Check `Get-ScheduledTask -TaskName "HealthVault-YouTubeQueue-Loop"` (PowerShell). If its `State` isn't `Running`, restart it (`Start-ScheduledTask`) — this task has no permission-granted auto-restart trigger (a known, standing limitation — see `buglog.md` 2026-07-25), so it silently stays down after any interruption (sleep, reboot, manual stop) until something notices and restarts it. Report its state either way in the summary; don't silently skip this check.

## 4. Process the raw-transcript backlog
Run `/process-raw-transcripts` (see `.claude/commands/process-raw-transcripts.md`) once, with its default batch size — this is the Claude-dependent step (note-writing, relevance judgment, concept-linking) that the raw collector itself deliberately doesn't do. Report how many were processed vs. how many remain in `Research/YouTube/Raw/` for a future run - don't try to clear the entire backlog in one `/vault-update` pass if it's large, that defeats the point of batching.

## 5. Log
Append one dated entry to `development.md`'s `## Log` section (today's date, new sub-bullet if today already has an entry) summarizing: which tools updated successfully/failed and to what version, which channels were refreshed and how many new videos each picked up, the raw-transcript collector's task state (and whether it needed restarting), and the raw-transcript backlog processed/remaining counts. Update the "Current State" section at the top of `development.md` only if something materially changed (a tool version pin, a new blocker, a resolved TODO) — don't touch it for routine no-op updates.

## 6. Summary to user
Plain-text: tool update results, per-channel new-video counts, transcript-collector task health, backlog processing results, any failures that need attention (route anything that looks like a recurring problem into `buglog.md`).
