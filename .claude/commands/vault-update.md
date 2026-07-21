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

## 3. Log
Append one dated entry to `development.md`'s `## Log` section (today's date, new sub-bullet if today already has an entry) summarizing: which tools updated successfully/failed and to what version, which channels were refreshed and how many new videos each picked up. Update the "Current State" section at the top of `development.md` only if something materially changed (a tool version pin, a new blocker, a resolved TODO) — don't touch it for routine no-op updates.

## 4. Summary to user
Plain-text: tool update results, per-channel new-video counts, any failures that need attention (route anything that looks like a recurring problem into `buglog.md`).
