# Health Vault

Local-first Obsidian vault for athletic performance, physical health, **and mental health** research — mental health is a first-class domain here, not an afterthought bolted onto physical protocols. CNS fatigue, overtraining, and burnout sit at the intersection of both and should be treated that way, not siloed. Sources get converted to structured notes, cross-linked, checked for contradictions, and correlated against Oura biometrics. No cloud RAG, no NotebookLM — everything runs locally via the `obsidian-second-brain` skill.

## Repo scope — tooling only, content never leaves this machine

This git repo (private, github.com/rossw811/health-vault) tracks **only the generic tooling**: `.claude/commands/`, `.claude/settings.json`, `.mcp.json`, `scripts/`, `.gitignore`, `.env.example`, `CLAUDE.md`, `_CLAUDE.md`. Every actual content folder/file below is gitignored and stays local-only — never commit or suggest committing them, even accidentally via a broad `git add`. If a new top-level content file/folder is created, add it to `.gitignore` immediately, don't wait for the next cleanup pass.

## Layout

- `Sources/` — raw ingested material (PDFs, transcripts, articles), entirely gitignored. `Sources/Paid/` additionally holds licensed course content (e.g. Ben Winney guides) — never redistribute even if repo scope ever changes. `Sources/Books/` holds legitimately-sourced book notes (see Book discovery below).
- `People/` — one note per person in "the Web" (see below): `tier` (1/2/3, manual) or `derived_tier` (decimal hop notation, automatic)
- `Dashboard/` — generated output of `scripts/generate_dashboard.py`, gitignored (regenerate, don't hand-edit)
- `Concepts/` — atomic concept notes (one idea per note: lipolysis, HRV, CNS fatigue, hypertrophy, anxiety, burnout, etc.)
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
- Auto-link key domain terms on first mention per note: `lipolysis`, `hypertrophy`, `HRV`, `CNS fatigue`, `readiness`, `resting heart rate`, `sleep efficiency`, `training load`, and mental-health terms with equal weight — `burnout`, `overtraining syndrome`, `anxiety`, `sleep quality`, `stress load`, `motivation`, `mental fatigue`. Create the Concept note if it doesn't exist yet.
- Mental health is not a separate, lesser category: when a source discusses training load, recovery, or performance, actively look for and surface the psychological dimension (motivation, burnout risk, anxiety around performance, identity/self-worth tied to results) rather than only extracting the physical claims. When running `/storm-panel` or `/concept-audit`, consider whether a mental-health-informed perspective is missing from the analysis.

## YouTube ingestion

- Primary path: `/youtube-channel [channel url]` (whole channel) or `/youtube-queue` (curated list in `YouTube Queue.md` at vault root) — both custom commands in `.claude/commands/`. Neither depends on any API key: transcript fetching is free (`youtube-transcript-api`), metadata comes from `yt-dlp` (free), and **Claude writes the note directly** rather than delegating to a cloud summarization call.
- **Notable Quotes must be verbatim** — copied character-for-character from the transcript text Claude actually reads, never paraphrased or reconstructed from memory. This holds regardless of whether a Gemini/XAI key is configured; it is a property of how our commands are written, not a fallback behavior.
- The skill's own bundled `/youtube [url]` command is a separate, available fallback for one-off videos, but it hard-requires `GEMINI_API_KEY` or `XAI_API_KEY` (configured globally, see below) since it delegates summarization to Gemini/Grok — prefer `/youtube-queue` with a single line instead, it needs nothing.
- `/youtube-channel`: enumerates **every** video via `yt-dlp --flat-playlist` (no default cap; pass `--limit N` to bound a run), filters ad/sponsor segments out of concept extraction, links concepts across the run and fills gaps via `/research`, and writes/updates a channel rollup note. Resumable — a per-channel state file in `Research/YouTube/.state/` means re-running only processes videos published since the last run.
- **Relevance gate before full processing**: every video (channel or queue path) is checked — title/description first, transcript skim only if ambiguous — for whether it's about health, fitness/performance, or mental health at all. Off-topic videos are discarded before any note is written and marked so they're never re-checked. This is separate from the ad/sponsor filter, which operates on relevant videos to exclude promotional segments specifically.
- **"Channels to Follow"** (`Synthesis/Channels to Follow.md`, updated by `/youtube-channel` only, not per-video queue entries): a standing, single note ranking every processed channel by relevance hit-rate and content signal into `follow closely` / `follow loosely` / `deprioritize`. This is the answer to "is this source worth continuing to check" for channels that aren't outright excluded (see permanent exclusion below).
- "Watching" a channel means transcript+description-based understanding by default, not frame-by-frame visual analysis.
- Run `/vault-update` to update the tool stack and refresh every tracked channel for new videos in one pass.
- **Skill config is global, not per-vault:** `obsidian-second-brain`'s own commands (`/youtube`, `/research`, `/notebooklm`, etc.) read credentials from `~/.config/obsidian-second-brain/.env` (a different file from this vault's own `.env`), keyed by `OBSIDIAN_VAULT_PATH` — required for ANY of the skill's bundled commands to resolve this vault at all. If this machine ever hosts a second Obsidian vault, that global config would need to be swapped or the skill reinstalled scoped differently.

## Biometric correlation (Oura)

- The `oura` MCP server (see `.mcp.json`) exposes sleep/readiness/activity/HRV tools. Token lives in `.env` (gitignored) as `OURA_TOKEN` — never hardcode it anywhere else.
- `/oura-sync` (custom command) is the primary path: pulls **every** metric the `oura` MCP server exposes (daily summary, readiness + its components, sleep + its components, heart rate, activity/steps, workouts, stress, SpO2, sessions, trends — not just the headline four) into `Daily/YYYY-MM-DD.md` frontmatter, and regenerates `Dashboard/index.html`. Full field list lives in `.claude/commands/oura-sync.md` — don't duplicate it here, it'll drift; that file is the source of truth for the schema. `--backfill` pulls the account's entire history once (skipping dates already populated, safe to re-run); the default daily run only touches today. Runs daily via a local Windows Scheduled Task (`HealthVault-OuraSync`, unattended, `scripts/run-oura-sync.cmd`). `/obsidian-daily` remains available for manual/interactive daily-note creation, but `/oura-sync` is what keeps biometrics current automatically.
- **MCP approval is per-session**: `oura`/`excel` were added to `.mcp.json` mid-session and show "Pending approval" until a session either gets the interactive trust prompt (`/mcp`) or is restarted after the fact. If Oura tools seem unavailable, check `claude mcp list` first before assuming something's broken.

- When asked to evaluate protocol efficacy, cross-reference `Daily/` frontmatter against `active_protocols` over the requested window before concluding anything.
- **Dashboard**: `scripts/generate_dashboard.py` reads `Daily/` frontmatter and writes a static, offline `Dashboard/index.html` (hand-rolled SVG charts, no server, no CDN) — open directly in a browser. Regenerated automatically by `/oura-sync`; run manually anytime with `python scripts/generate_dashboard.py`.

## Spreadsheets

- The `excel` MCP server (see `.mcp.json`) reads/writes `.xlsx` files directly — use it for `Protocols/Poliquin_Tracker_v2_1.xlsx` and any future tracker spreadsheets rather than round-tripping through manual conversion.

## Multi-perspective synthesis

- Use `/storm-panel [question]` (custom command) for comparative analysis across sources — simulates a 4-expert panel (neurological/performance, systemic volume, clinical/longevity, biochemical optimization), queries the vault first, cross-examines disagreements, and writes a synthesized note to `Synthesis/`. This is a local prompt-driven simulation, not the academic Stanford STORM pipeline (which needs paid search APIs) — same output shape, no extra infra.

## Bulletproofing concepts

- Use `/concept-audit [concept | "all"]` (custom command) to adversarially critique existing Concept/Protocol notes — three independent lenses (mechanism-demanding, evidence-auditing, contrarian), finds weak/single-source claims, oversights, and unresolved contradictions. This is distinct from the skill's own `/obsidian-challenge`, which red-teams a *proposed idea* against your own past decisions — `/concept-audit` systematically critiques the ingested concepts themselves.
- **Claim verification**: every critical finding gets checked against actual studies via `/research --academic` (scholarly sources only) — not just "is this backed," but the study's own sample size, methodology shortcomings, and whether its result actually generalizes to the vault's claim. Tagged Verified/Contradicted/Inconclusive.
- **Online sentiment**: the `last30days` skill checks current Reddit/HN/X/YouTube discourse on the concept — directional color on whether it's broadly accepted, actively debated, or quietly debunked since ingestion. Never overrides the study-level verification.
- Output: full report to `Synthesis/Critiques/`, critical findings flagged inline on the audited note via a `[!warning]` callout.

## Source quality — permanent exclusion for inactive/sparse channels

- Before processing any channel, `/youtube-channel` checks `Research/YouTube/.state/_excluded-channels.json` first and stops immediately if already listed — excluded channels are **never automatically re-fetched or re-evaluated**, only a manual edit to that file removes an exclusion.
- New channels are triaged automatically: **inactive** (no upload in 18+ months) or **sparse** (fewer than 5 total videos) get added to the exclusion list and skipped, with the specific reason/detail recorded. A single relevant video from an excluded channel can still be processed individually via `/youtube-queue` — the exclusion is channel-level, not video-level.

## Aggregation

- `Bases/All Content.base` (Obsidian Bases) gives one browsable, filterable view across every content folder — Concepts, Protocols, Synthesis (incl. Channel Rollups, Critiques), Research/YouTube, Research/Web — grouped by area, with tags/status/date columns. This is the "see everything at a glance" answer rather than folder-by-folder browsing. Requires Obsidian itself with Bases (core feature in current versions) to view.

## The Web — tiered source-quality graph of people

- `People/` holds one note per person, with `tier` (1/2/3, assigned manually — a judgment call this vault never makes unilaterally) or `derived_tier` (decimal hop notation, e.g. `"1.1"` for someone a Tier-1 source directly references, `"1.2"` for that person's own references, assigned automatically).
- `/web-expand [person | channel url] [--depth N] [--influenced-by]` grows the Web: processes a source's content (reusing `/youtube-channel`'s full pipeline), additionally extracts every real named individual referenced/interviewed, dedupes against existing `People/` notes (keeping the best tier/hop path when a person is discovered via multiple routes), and recurses **2 hops deep by default** — a hard cap, not a suggestion, since this graph can otherwise grow combinatorially forever.
- `--influenced-by` runs the same discovery in reverse: who influenced/taught/mentored an already-known person (via `/research` rather than their own channel) — this is how influence genealogy (e.g. what Poliquin himself studied) gets built, using the same tiering machinery.
- **Grouping/visualization is a view concern, not a data concern**: every `People`/`Concepts` note already carries enough metadata (tier, `derived_tier`, `confidence` from `/concept-audit`, category tags) to regroup the graph any number of ways. Trying a new "webbing scheme" (by tier, by information quality, by topic category) means changing what property Extended Graph or a Base groups by — never reprocessing data. This vault is explicitly meant to experiment with multiple schemes over time, not settle on one.
- Visualize via the **Extended Graph** community plugin (manual install via Settings → Community Plugins — never hot-edit plugin config while Obsidian is running) — node coloring/grouping by frontmatter property, multiple saved configs (one per webbing experiment).

## Book discovery — legitimate sources only

- `/book-discovery [topic | author]` — Google Books previews, Project Gutenberg (public domain), NCBI Bookshelf + DOAB (open-access academic). Full-text distillation only for genuinely public-domain/open-access results; everything else gets citation + legitimate-access-pointer treatment.
- **Internet Archive's lending library is deliberately excluded** — its legal status is contested (lost the Hachette appeal in 2024), not merely deprioritized. Never use it as a source even if convenient.

## Personal tailoring phase — ACTIVE as of 2026-07-21

- `Protocols/My Profile.md` exists. **The vault is now in tailored-research mode, not broad data-gathering mode.** `/storm-panel` and `/concept-audit` must read it and actively check whether a claim/protocol applies to the documented profile (concussion history, current training status, stated goals, family history flags) before treating a general finding as automatically relevant. Re-run `/tailor-profile` to update sections as things change (training resumes, bloodwork comes back, etc.) rather than letting this note go stale.
- **Concussion history is documented, not diagnosed by this vault.** `/concussion-protocol` researches and cites the actual published graduated return-to-play consensus statement (Berlin/Amsterdam, CDC HEADS UP — never invented from scratch), maps the user's documented history to a concrete current stage, and flags physician/neurologist confirmation specifically at stage-advancement points where symptoms could plausibly recur — not as blanket boilerplate. A documented history of multiple concussions is treated as materially different from the single-incident population the standard protocol validates against.

## Automated maintenance

- `/vault-update` runs weekly via a local Windows Scheduled Task (`HealthVault-VaultUpdate`, unattended, `scripts/run-vault-update.cmd`) — updates the local tool stack and refreshes every tracked YouTube channel for new videos. Logs to `Logs/vault-update-task.log` and `development.md`. Manage/inspect via Task Scheduler (`taskschd.msc`).
