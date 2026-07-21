# Health Vault

Local-first Obsidian vault for athletic performance / health research. Sources get converted to structured notes, cross-linked, checked for contradictions, and correlated against Oura biometrics. No cloud RAG, no NotebookLM — everything runs locally via the `obsidian-second-brain` skill.

## Layout

- `Sources/` — raw ingested material (PDFs, transcripts, articles). `Sources/Paid/` holds licensed course content (e.g. Ben Winney guides) — **gitignored, never redistribute even privately.**
- `Concepts/` — atomic concept notes (one idea per note: lipolysis, HRV, CNS fatigue, hypertrophy, etc.)
- `Protocols/` — active/experimental protocol notes, each linking the Concepts and Sources backing it
- `Daily/` — daily logs with Oura frontmatter + protocol execution checklist
- `Synthesis/` — STORM-style multi-perspective panel outputs, master protocol docs. `Synthesis/Channels/` holds YouTube channel rollup notes.
- `Research/` — skill-default research output (`Research/YouTube/` single-video notes + `.state/` channel-refresh tracking, `Research/Web/` free/paid research dossiers)
- `scripts/` — small local automation (Oura MCP wrapper, etc.) — keep these generic (env vars, relative paths), no hardcoded secrets or machine-specific paths
- `development.md` — dev log + living "Current State" handoff summary. Update the log on any setup/tooling change; keep "Current State" current, don't let it drift.
- `buglog.md` — append-only issue log for tooling problems encountered (not vault content issues — those are `[!contradiction]` callouts instead)

## Ingestion rules

- Use `/obsidian-ingest` for new sources (PDF, article, transcript). It rewrites/extends existing Concept notes rather than duplicating them.
- New information that conflicts with an existing note gets a `[!contradiction]` callout grouping the opposing claims and their sources — never silently overwrite a prior claim.
- Auto-link key domain terms on first mention per note: `lipolysis`, `hypertrophy`, `HRV`, `CNS fatigue`, `readiness`, `resting heart rate`, `sleep efficiency`, `training load`. Create the Concept note if it doesn't exist yet.

## YouTube ingestion

- Primary path: `/youtube-channel [channel url]` (whole channel) or `/youtube-queue` (curated list in `YouTube Queue.md` at vault root) — both custom commands in `.claude/commands/`. Neither depends on any API key: transcript fetching is free (`youtube-transcript-api`), metadata comes from `yt-dlp` (free), and **Claude writes the note directly** rather than delegating to a cloud summarization call.
- **Notable Quotes must be verbatim** — copied character-for-character from the transcript text Claude actually reads, never paraphrased or reconstructed from memory. This holds regardless of whether a Gemini/XAI key is configured; it is a property of how our commands are written, not a fallback behavior.
- The skill's own bundled `/youtube [url]` command is a separate, available fallback for one-off videos, but it hard-requires `GEMINI_API_KEY` or `XAI_API_KEY` (configured globally, see below) since it delegates summarization to Gemini/Grok — prefer `/youtube-queue` with a single line instead, it needs nothing.
- `/youtube-channel`: enumerates **every** video via `yt-dlp --flat-playlist` (no default cap; pass `--limit N` to bound a run), filters ad/sponsor segments out of concept extraction, links concepts across the run and fills gaps via `/research`, and writes/updates a channel rollup note. Resumable — a per-channel state file in `Research/YouTube/.state/` means re-running only processes videos published since the last run.
- "Watching" a channel means transcript+description-based understanding by default, not frame-by-frame visual analysis.
- Run `/vault-update` to update the tool stack and refresh every tracked channel for new videos in one pass.
- **Skill config is global, not per-vault:** `obsidian-second-brain`'s own commands (`/youtube`, `/research`, `/notebooklm`, etc.) read credentials from `~/.config/obsidian-second-brain/.env` (a different file from this vault's own `.env`), keyed by `OBSIDIAN_VAULT_PATH` — required for ANY of the skill's bundled commands to resolve this vault at all. If this machine ever hosts a second Obsidian vault, that global config would need to be swapped or the skill reinstalled scoped differently.

## Biometric correlation (Oura)

- The `oura` MCP server (see `.mcp.json`) exposes sleep/readiness/activity/HRV tools. Token lives in `.env` (gitignored) as `OURA_TOKEN` — never hardcode it anywhere else.
- `/obsidian-daily` should populate the daily note frontmatter from live Oura data:

```yaml
---
date: <YYYY-MM-DD>
type: daily-log
readiness_score:
sleep_score:
average_hrv:
resting_hr:
active_protocols: []
training_load_hrs: 0
tags: [biometrics, health-tracking]
---
```

- When asked to evaluate protocol efficacy, cross-reference `Daily/` frontmatter against `active_protocols` over the requested window before concluding anything.

## Spreadsheets

- The `excel` MCP server (see `.mcp.json`) reads/writes `.xlsx` files directly — use it for `Protocols/Poliquin_Tracker_v2_1.xlsx` and any future tracker spreadsheets rather than round-tripping through manual conversion.

## Multi-perspective synthesis

- Use `/storm-panel [question]` (custom command) for comparative analysis across sources — simulates a 4-expert panel (neurological/performance, systemic volume, clinical/longevity, biochemical optimization), queries the vault first, cross-examines disagreements, and writes a synthesized note to `Synthesis/`. This is a local prompt-driven simulation, not the academic Stanford STORM pipeline (which needs paid search APIs) — same output shape, no extra infra.
