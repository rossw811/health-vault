# Customizing this project

This is a guide to the *swappable parts* of this vault's tooling — where each subsystem's boundary is, what contract a replacement needs to satisfy, and concretely how you'd swap one thing for another (Oura → Whoop, whisper.cpp → a cloud API, the current athletic/mental-health domain focus → something else entirely). It assumes you've already read `README.md` (what the project does) and `CLAUDE.md` (the operating rules an AI session follows). This file is about *changing* those things, not using them as-is.

**General principle**: almost everything here is deliberately loosely coupled — a Python script that shells out to a CLI tool, writes/reads flat Markdown files with YAML frontmatter, or calls a REST API directly. There's no framework to fight. Swapping a component almost always means replacing one script (or one function's internals) while leaving everything downstream of it untouched, because downstream consumers only care about the *shape* of what they receive (a frontmatter schema, a function signature, a file format), not how it was produced.

---

## 1. Biometric source: Oura → Whoop, Apple Watch, Garmin, etc.

**What's currently there**: `scripts/oura_full_sync.py` calls Oura's REST API v2 directly (bearer-token auth, `OURA_TOKEN` in `.env`), pulls every endpoint (daily summary, readiness + contributors, sleep + contributors + time-series, activity, heart rate, workouts, stress, SpO2, sessions, resilience, cardiovascular age, VO2max, tags), and does two things with the result:
1. Writes the full raw JSON payload per day to `Daily/.oura-raw/<date>.json` (an unopinionated archive — never discarded, even if the frontmatter schema changes later).
2. Calls `build_frontmatter_updates()` to flatten the data it cares about into a dict, then `upsert_daily_note()` to merge that dict into `Daily/YYYY-MM-DD.md`'s YAML frontmatter (creating the note if it doesn't exist, preserving any existing prose/checklist content below the frontmatter block).

`scripts/schemas.py` defines a Pandera schema that `scripts/oura_analyze.py` uses to validate the resulting `Daily/*.md` frontmatter before running any statistics on it — this is what actually determines "what fields does this vault expect to exist," not `oura_full_sync.py` itself.

**The actual contract, if you're swapping the data source**:
- Your replacement script needs to write **some set of numeric/categorical fields into `Daily/YYYY-MM-DD.md`'s frontmatter**, one note per day, without destroying whatever else is already in that note (protocol checklists, journal prose, etc. — see `upsert_daily_note()`'s merge-not-overwrite pattern for how the current one does this safely).
- The **field names are yours to choose** — `schemas.py` is not a fixed API, it's *this vault's own* schema, built to match what Oura happens to expose. If you're pulling from Whoop (recovery score, strain, HRV, respiratory rate) or Apple Health (via HealthKit export or the Health Auto Export app's REST/webhook), rename `schemas.py`'s columns to match your actual source's vocabulary, and update `scripts/generate_dashboard.py`'s chart-building code to reference the new field names (it's a hand-rolled SVG generator reading directly from frontmatter — no magic, just look for where it currently references `readiness_score`/`sleep_score`/etc. and repoint them).
- `/oura-analyze`'s statistical rigor (FDR correction, minimum-N gating, cross-validated modeling) is **generic** — it operates on whatever numeric columns exist in `Daily/*.md`, not specifically Oura fields. You get to keep all of that by just pointing `schemas.py` at your new field names; the actual `scripts/oura_analyze.py` logic needs no changes.
- If your new source has a real public API (Whoop's v2 API uses OAuth2, not a static token — different auth flow than Oura's bearer token, budget real time for that), write a new `scripts/<source>_full_sync.py` following `oura_full_sync.py`'s three-part shape (fetch → raw archive → frontmatter merge). If your source is Apple Health specifically, there's no direct API — you're realistically looking at a periodic CSV/JSON export (via Health Auto Export or similar) that a script parses and reshapes into the same `Daily/*.md` frontmatter merge, rather than a live API pull.
- Rename `/oura-sync` → whatever fits (`/whoop-sync`, `/biometric-sync`) in `.claude/commands/`, and update the Scheduled Task (`HealthVault-OuraSync`) to call the new script.
- The `oura` MCP server registration in `.mcp.json` is optional context for a live Claude Code session (ad-hoc "what's my sleep score" questions) — separate from the sync pipeline above, and not required for anything else to work. Swap or drop it independently.

---

## 2. YouTube/podcast ingestion queue mechanics

**What's currently there**: `YouTube Queue.md` and `Podcast Queue.md` are plain Markdown checklists (`- [ ] <url>`) under `##` headings. `scripts/collect_raw_transcripts.py`'s `extract_urls_from_queue()` reads the file, and — this is the one non-obvious rule worth knowing if you're editing queue structure — **any heading whose text contains the literal substring "PRIORITY" (case-insensitive) makes every URL under it high-priority**, processed (both newly-discovered and previously-failed/retry-eligible) strictly ahead of everything under a non-"PRIORITY" heading, in file order within each tier. This is a plain string match, not a special YAML field — you customize prioritization entirely by renaming/reordering headings in the queue file itself, no code changes needed for the common case.

**If you want a different prioritization scheme entirely** (e.g., weighted scoring instead of binary priority, per-channel refresh cadence, a max-videos-per-run cap per channel): the relevant logic is `_build_worklist()` in `collect_raw_transcripts.py` (YouTube) and `podcast_collector.py` (podcasts) — both take a `collected` dict (what's already been attempted) and return an ordered list of work items. Replace the ordering logic inside that one function; nothing else in either script needs to know how the ordering decision was made. (Fair warning if you do this: getting this exactly right took three iterations this session, documented in `buglog.md`'s 2026-07-27 entries — the subtle failure mode is "new work from a low-priority source can perpetually preempt a high-priority source's backlog" if new-vs-retry status is sorted separately from source rank. Worth reading before redesigning this.)

**If you want a different video/audio source entirely** (not YouTube) — the collector's actual external dependency is `yt-dlp` for enumeration/download and either `youtube-transcript-api` or local transcription for the text itself. Swapping to, say, a different platform means replacing `list_channel_video_ids()` and `download_audio()`'s underlying calls; the checkpoint/retry/priority machinery around them is platform-agnostic (it just tracks opaque IDs and statuses in `Research/YouTube/Raw/.collected_ids.json`).

---

## 3. Transcription engine

**What's currently there**: `scripts/whisper_transcribe.py` is the *only* file either collector talks to for local transcription — both `collect_raw_transcripts.py` and `podcast_collector.py` call exactly three functions: `load_model(model_size, cpu_threads)` (called once per worker process, returns an opaque config object), `transcribe(audio_path, model_size, batched_model, cpu_threads)` (returns a plain string), and `transcribe_video(...)` (the download+transcribe combo, used by the CLI/standalone path).

**This is the cleanest swap point in the whole project** — as of 2026-07-27 this vault runs a self-compiled `whisper.cpp` binary (native ARM64, see `CLAUDE.md`'s YouTube ingestion section and `buglog.md` for why), but the interface was deliberately kept identical to the *previous* engine (`faster-whisper`/CTranslate2) specifically so this swap wouldn't require touching either collector. To swap to something else — a different local engine, or a cloud STT API (Whisper API, Deepgram, AssemblyAI, etc.) — **rewrite only the bodies of `load_model()` and `transcribe()`** in `whisper_transcribe.py`, keep the same function names/signatures/return types, and both collectors keep working with zero changes.

**Before you swap it, know the standing rule this vault operates under** (see `CLAUDE.md`'s "Always test whatever is built" section, and the extensive A/B-testing methodology in `buglog.md`'s 2026-07-27 entries): any transcription-engine change gets validated with a real, systematic word-level diff (`difflib.SequenceMatcher`, not eyeballing) against a known-good baseline on real audio before it's trusted in production — not because the tooling demands it, but because this session found real, measurable accuracy regressions (dropped clauses, repetition-loop hallucinations) in two different alternative engines that looked fine on casual inspection. If you swap engines, budget time for the same rigor, or you may ship something quieter-but-worse.

---

## 4. Domain focus (currently: athletic performance + physical health + mental health)

**What's currently there**: the domain focus isn't hardcoded into any script — it lives entirely in `CLAUDE.md` (the auto-linked-term list, the ingestion rules, the "mental health is first-class" mandate) and in the actual content of `Concepts/`/`Protocols/` notes. The commands themselves (`/youtube-channel`, `/concept-audit`, `/storm-panel`, etc.) are domain-agnostic — they operate on "whatever this vault's `CLAUDE.md` says to care about," not on health specifically by any code-level assumption.

**To retarget this vault at a different domain** (finance research, a different academic field, general personal knowledge management): the real work is rewriting `CLAUDE.md`'s domain-specific sections (auto-link term list, ingestion rules, the tiered "Web" of people's scope) — the commands, the two-stage collector pipeline, the People-graph tiering system, and the statistical-rigor conventions all carry over structurally unchanged, since none of them are actually about health specifically. The one place with real health-specific logic is `scripts/schemas.py`/`oura_analyze.py` (biometric-specific) and `bloodwork-ingest.md`/`genetics-ingest.md` (medical-lab-specific) — those three are the ones to drop or heavily rewrite for a non-health domain; everything else generalizes.

---

## 5. The People graph (tiering, hop distance, "the Web")

**What's currently there**: `People/<name>.md` notes carry a `tier` (1/2/3, assigned manually — see `CLAUDE.md`'s explicit note that this vault never assigns Tier 1 unilaterally) or a `derived_tier` (decimal hop notation like `"1.1"`, assigned automatically by `/web-expand` based on citation/interview distance from a Tier-1 anchor). This is a pure frontmatter-metadata convention, not a database — Obsidian's Extended Graph plugin (or a `Bases` view) reads these properties directly to color/group the graph.

**To change the tiering scheme** (e.g., a numeric trust score instead of discrete tiers, a different hop-decay function, additional dimensions like "recency of citation"): this is entirely a frontmatter-schema decision plus `/web-expand`'s own hop-assignment logic (in its command definition, `.claude/commands/web-expand.md`) — there's no separate graph-database layer to migrate. Per `CLAUDE.md`'s own stated design intent, "grouping/visualization is a view concern, not a data concern" — you're free to add new properties and view the same underlying notes multiple ways without reprocessing anything.

---

## 6. What's core philosophy, not implementation detail (think twice before changing)

A few things in this project are load-bearing design decisions the rest of the system leans on, not incidental choices:
- **Anti-fabrication discipline** (never invent a citation, a reference range, a person's identity, a study's methodology) — every ingestion/audit command assumes this holds. Loosening it would silently corrupt the vault's own evidentiary claims over time, not just produce occasional bad output.
- **Small-N statistical honesty** (`oura_analyze.py` refusing to model below a row-count floor, FDR-correcting multiple comparisons) — this is what makes the biometric analysis trustworthy on a single person's dataset instead of quietly overfitting. Don't relax this to get more "findings" out of thin data.
- **The two-stage pipeline split** (zero-cost background collection vs. deliberate, batched Claude-costing note-writing) — collapsing this back into one step was tried implicitly early in this project's life and is exactly what the "Two-stage transcript pipeline" section of `CLAUDE.md` warns against re-doing; it's cost-control architecture, not a stylistic preference.

Everything else in this file — the specific biometric source, the specific transcription engine, the specific ingestion queue format, the specific domain — is genuinely just implementation, swap freely.
