# Health Vault

**A local-first, AI-native "second brain" for athletic performance, physical health, and mental health — built to replace NotebookLM, generic wearable dashboards, and scattered notes-apps with one system that actually reasons over your own data.**

Sources (PDFs, entire YouTube channels, web research, books, lab panels) get converted into structured, cross-linked, contradiction-checked Markdown notes. Those notes are correlated against real Oura biometrics with proper statistical discipline, adversarially critiqued against actual published literature, and organized into a tiered, source-quality-aware knowledge graph of the people and ideas behind them. Everything runs locally, on your own machine, in your own Obsidian vault — no cloud RAG service, no third-party knowledge-base, no data leaving your control unless you choose to push it somewhere.

## Why this exists

Most "AI + your notes" tools stop at retrieval — they answer questions about what you've saved, but they don't second-guess it, connect it across sources, or hold it to any evidentiary standard. Most wearable apps report population-average insights ("most people sleep better with X") instead of *your own* baseline. This project takes a different position on both:

- **Claims get checked, not just stored.** `/concept-audit` runs three adversarial lenses over every ingested concept and verifies critical claims against actual peer-reviewed studies — sample size, methodology, whether the result even generalizes to the claim being made — not just "is there a study that mentions this."
- **Biometric analysis is personal-baseline, not population-average**, and is honest about small-N limits. `/oura-analyze` won't call a group difference "significant" without surviving FDR correction across every comparison tested, won't fit a model below a real data-size floor, and reports a null result as a real finding, not something to hide.
- **Sources are weighted, not flattened.** "The Web" tracks who said what, how they're connected to other sources (who they've interviewed, who taught them), and at what tier of reliability — so a claim from a Tier-1 anchor and a claim from someone three hops away don't carry the same evidentiary weight by accident.
- **Mental health is not an afterthought.** CNS fatigue, overtraining, burnout, and psychological wellbeing are treated as inseparable from physical training, not a separate lesser category bolted on at the end.
- **It's actually thorough.** No recency caps on channel ingestion (every video a channel has ever published gets at least a relevance check), no invented reference ranges on bloodwork, no fabricated citations, anywhere.

## What it does

- **Ingestion** — `/youtube-channel` and `/youtube-queue` process entire YouTube channels (every video, not a recent sample) and curated lists, free and key-less (no Gemini/XAI dependency for the core pipeline), with verbatim-quote guarantees, ad/sponsor filtering, and a relevance gate that discards off-topic content before it's ever processed. `/book-discovery` sources books legitimately only — public-domain/open-access texts get fully distilled, everything else gets citation-and-pointer treatment, never an unauthorized full-text copy.
- **Biometrics** — `/oura-sync` pulls every metric the Oura API exposes (not just the headline four) into daily notes and regenerates a static offline dashboard. `/oura-analyze` runs correlations, personal-baseline rolling trends, anomaly detection, lag-correlation (does yesterday's behavior predict today's outcome), FDR-corrected protocol/tag comparisons, and appropriately-scaled predictive modeling (regularized regression + shallow random forest — not deep learning, which would overfit a dataset this size).
- **The Web** — `/web-expand` builds a tiered graph of people: who influenced/taught an anchor source, and who an anchor has interviewed or cited in their own work (each new discovery capturing *what knowledge domain* connects them, not just a name). Depth-capped at 2 hops by design, so the graph never grows combinatorially forever.
- **Bloodwork** — `/bloodwork-ingest` structures a lab panel using only the reference ranges the source actually gives (never a guessed generic range), cross-referenced against documented family-history risk factors. `/bloodwork-trend` tracks direction between draws once enough panels exist.
- **Personal tailoring** — `/tailor-profile` builds a living profile of goals, constraints, and history that other commands actively check claims against. `/concussion-protocol` cites the real published graduated return-to-sport consensus statement (not an invented one) and maps a concrete current position against it — with physician-confirmation flagged only at the specific clinical transitions where a multi-concussion history actually changes the risk calculus, not as blanket boilerplate.
- **Synthesis & critique** — `/storm-panel` runs a grounded, multi-perspective synthesis over the vault's own sources for a given question. `/concept-audit` adversarially critiques existing concepts and protocols, verifies critical claims via academic research, and checks current online sentiment as directional color.
- **Aggregation** — `Bases/All Content.base` gives one filterable, cross-folder view of everything in the vault; the Extended Graph community plugin visualizes the People/Concepts graph, colorable by tier, confidence, or topic.

## Repo scope — tooling only, content never leaves this machine

**This repo tracks the generic tooling only**: `.claude/commands/`, `.claude/settings.json`, `.mcp.json`, `scripts/`, `.gitignore`, `.env.example`, `CLAUDE.md`, `_CLAUDE.md`, this file, `CONTRIBUTIONS.md`, and `requirements.txt`. **All actual vault content — every note, every source, every piece of personal data — is gitignored and stays local-only.** See `.gitignore` for the full list and the "Repo scope" section of `CLAUDE.md` for the reasoning. If you fork this for your own vault, this boundary is the whole point: clone the tooling, build your own private content on top of it, and nothing personal ever needs to touch a remote.

**Forking this for a different biometric device, transcription engine, or domain entirely?** See `CONTRIBUTIONS.md` — a guide to every swappable subsystem (Oura → Whoop/Apple Watch, whisper.cpp → a different engine, the YouTube ingestion mechanics, the athletic/mental-health domain focus itself) and what contract a replacement needs to satisfy.

## Prerequisites

- [Obsidian](https://obsidian.md/) — the vault viewer/editor itself
- [Claude Code](https://claude.com/claude-code)
- Python 3.11+ with `pip`
- Node.js 18+ with `npm`/`npx`
- [`uv`](https://docs.astral.sh/uv/) (Python package manager, used by the `obsidian-second-brain` skill's isolated environment)
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`jq`](https://jqlang.org/) on PATH
- [GitHub CLI (`gh`)](https://cli.github.com/) if you want to push a fork/clone of this tooling to your own private repo
- An [Oura Ring](https://ouraring.com/) personal access token if you want biometric correlation (optional — everything else works without it)
- `ffmpeg` — optional, only needed if you ever fall back to local audio-based transcription (see Troubleshooting)
- A compiled [`whisper.cpp`](https://github.com/ggml-org/whisper.cpp) binary + a `ggml-small.bin` model — optional, same fallback path as `ffmpeg` above. Not redistributed in this repo (build it yourself, or swap in a different local/cloud transcription engine — see `CONTRIBUTIONS.md`).

## Setup (fresh machine)

1. Clone this repo into your vault folder (or clone into an empty folder and treat it as the vault root — Obsidian just needs a folder to open).
2. Create the vault content folders (these are gitignored, so they don't come with the clone):
   ```
   mkdir Sources Sources/Paid Sources/Books Concepts Protocols Daily Synthesis Synthesis/Channels Synthesis/Critiques Research Research/YouTube Research/Web Logs Bases People Bloodwork Dashboard
   ```
3. `pip install -r requirements.txt`
4. Install the `obsidian-second-brain` Claude Code plugin:
   ```
   /plugin marketplace add eugeniughelbur/obsidian-second-brain
   /plugin install obsidian-second-brain@obsidian-second-brain
   ```
5. Configure the skill's **global** (per-machine, not per-vault) config at `~/.config/obsidian-second-brain/.env`:
   ```
   OBSIDIAN_VAULT_PATH=/absolute/path/to/this/folder
   # Optional: GEMINI_API_KEY, XAI_API_KEY, PERPLEXITY_API_KEY, YOUTUBE_API_KEY
   ```
6. Copy `.env.example` to `.env` in this vault's root and fill in real values (`OURA_TOKEN` at minimum if using biometric correlation). `.env` is gitignored — never commit it.
7. Open the folder in Obsidian as a vault. Install the **Extended Graph** community plugin manually (Settings → Community Plugins) if you want to visualize the People/Concepts graph — do this while Obsidian is closed or freshly opened, not mid-session, to avoid a live-config conflict.
8. In Claude Code, run `/vault-update` once to confirm the tool stack resolves correctly.
9. Run `/tailor-profile` when you're ready to shift from broad data-gathering into tailored, profile-aware research — this is what lets `/storm-panel` and `/concept-audit` check claims against your actual documented context instead of accumulating generically.

## Custom commands

All defined in `.claude/commands/`. Full behavior documented in `CLAUDE.md`.

| Command | Purpose |
|---|---|
| `/youtube-channel [url]` | Ingest every video from a channel — resumable, permanently excludes sparse (<5 video) channels, filters ad/sponsor content, no API key required |
| `/youtube-queue` | Process a curated list of video/channel links from `YouTube Queue.md` |
| `/podcast-queue` | Discover/verify podcast RSS feeds (Apple Search API, no key needed) and process a curated list from `Podcast Queue.md` — same free, no-API-key discipline as YouTube |
| `/blog-sweep` | Discover and distill Substack/blog RSS feeds — free/open content gets full distillation, paywalled gets citation-and-pointer treatment |
| `/process-raw-transcripts` | Turn raw transcripts collected by the zero-cost background collectors (`scripts/collect_raw_transcripts.py`, `scripts/podcast_collector.py`) into real AI-first notes — the Claude-costing half of the two-stage pipeline. **Run as one Agent call per batch with its own internal per-file loop — never as a per-file fan-out (Workflow/many Agent calls); that pattern hit a session rate limit and failed almost entirely, see `buglog.md` 2026-07-26.** |
| `/web-expand [person \| url] [--depth N] [--influenced-by]` | Grow the tiered People graph — forward (who this source cites/interviews) or backward (`--influenced-by`, who taught/influenced them) |
| `/institution-sweep [person]` | Extension of the Web — find a tracked person's institutional affiliation and sweep that institution's own publication output |
| `/book-discovery [topic \| author]` | Source books legitimately — full distillation for public-domain/open-access texts, citation-only otherwise |
| `/journal-sweep [journal \| topic]` | Sweep a journal/topic for legitimately-accessible studies (PubMed/OpenAlex abstracts or open-access full text) and critique methodology; newer studies weighted over older conflicting ones |
| `/tailor-profile` | Build/update the living personal profile that other commands check claims against |
| `/concussion-protocol` | Cite the real published graduated return-to-sport consensus statement and map a concrete current position against it |
| `/oura-sync` | Pull every Oura metric into today's daily note and regenerate the dashboard |
| `/oura-analyze` | Full statistical pass over Oura history — correlations, trends, anomalies, lag effects, FDR-corrected protocol/tag comparisons, predictive modeling |
| `/bloodwork-ingest [file \| "manual"]` | Structure a lab panel, cross-referenced against documented family-history risk factors, ranges from the source only |
| `/bloodwork-trend [marker]` | Track a marker's direction across draws once 2+ panels exist |
| `/bloodwork-second-opinion [panel note]` | Second-opinion-style read on an ingested panel, grounded in the People/Concepts graph's own collected expertise — organizes/cross-references only, never diagnoses |
| `/genetics-ingest [file \| "manual"]` | Structure a raw DNA/genetic test into a note — each marker with only the interpretation the source itself provides, cross-referenced against family history |
| `/storm-panel [question]` | Multi-perspective grounded synthesis panel over the vault's own sources |
| `/concept-audit [concept \| "all"]` | Adversarially critique concepts — weak claims, verified against actual studies via `/research --academic`, plus online sentiment |
| `/concept-connect [concept \| topic]` | Map how a concept connects to everything else in the vault; surface branch-out (adjacent uncovered topics) and deep-dive (thin/single-source concepts) directions |
| `/person-views [person \| "all"]` | Backfill a person's "Views & Claims" — what they stated as fact vs. opinion vs. reasoning, per subject, sourced from citing video/podcast notes |
| `/optimize-target [target]` | Build/refresh a per-marker or per-body-system optimization plan — evidence-tiered levers, measurement plan, and interactions with other targets |
| `/vault-update` | Update the local tool stack and refresh all tracked YouTube channels for new videos |

## Automation

All local Windows Scheduled Tasks (unattended, set up via `Register-ScheduledTask`, not the cloud "schedule" skill — that runs in an isolated sandbox without this machine's local tools/skill installs). Two tiers: **zero-Claude-cost** (pure Python, safe to run continuously) and **Claude-costing** (deliberately left manual, not scheduled):

| Task | Cadence | What it does | Cost | Log |
|---|---|---|---|---|
| `HealthVault-OuraSync` | Daily | `/oura-sync` — biometrics into today's daily note + dashboard regen | Claude | `Logs/oura-sync-task.log` |
| `HealthVault-VaultUpdate` | Weekly | `/vault-update` — tool-stack refresh + channel discovery | Claude | `Logs/vault-update-task.log` |
| `HealthVault-YouTubeQueue-Loop` | Continuous | `scripts/collect_raw_transcripts.py` — raw transcript collection (official captions, local Whisper fallback), checkpointed/retried, singleton-locked | Zero | `Logs/` (per-collector) |
| `HealthVault-PodcastQueue-Loop` | Continuous | `scripts/podcast_collector.py` — RSS-based episode collection, same checkpoint/retry/lock discipline, deduped against YouTube coverage | Zero | `Logs/` (per-collector) |
| `HealthVault-ReapOrphans` | Hourly | `scripts/reap_orphans.ps1` — kills only confirmed-orphaned worker processes (dead parent), never touches healthy workers; self-corrects invalid channel exclusions | Zero | `Logs/reap-orphans.log` |
| `HealthVault-BacklogHealthCheck` | Daily 4am | `scripts/backlog_health_check.py` — audits every checked-off channel's real video count vs. collected count, auto-reopens on a significant gap | Zero | `Logs/backlog-health-check.log` |

Manage/inspect via Task Scheduler (`taskschd.msc`). **`/process-raw-transcripts` (turning collected raw transcripts into real notes), `/oura-analyze`, and `/concept-audit` are deliberately NOT scheduled** — they cost real Claude budget per run, so they're invoked deliberately in batches rather than fired blindly on a timer. See `development.md`'s Current State section for the safe way to run `/process-raw-transcripts` (one Agent call per batch, not a per-file fan-out).

**Windows Task Scheduler caveat, learned the hard way**: `Stop-ScheduledTask` does not reliably kill an entire child process tree, and force-killing a parent process does not trigger normal cleanup for a `ProcessPoolExecutor`'s worker processes — they can orphan and keep holding loaded models in memory indefinitely. Both collector scripts use a PID-based singleton lock to prevent duplicate instances regardless of this; use `scripts/stop-collectors.ps1` to stop them cleanly (it separately hunts down and kills any orphans by process signature), never a raw `Stop-Process` on just the parent. Also: a scheduled task's `Execute` field needs the interpreter's **full path** (e.g. `C:\Users\<you>\anaconda3\python.exe`), not a bare `python.exe`/`powershell.exe` — PATH does not reliably resolve in the actual unattended execution context on this platform.

## Architecture & design principles

- **No cloud RAG.** The `obsidian-second-brain` skill's built-in keyword + optional local-Ollama semantic search covers this; no separate `mcp-local-rag`/`Agent-Reach` server is used.
- **No API key required for YouTube ingestion.** Transcript fetching (`youtube-transcript-api`) and metadata (`yt-dlp`) are both free; Claude writes the summary/quotes directly rather than delegating to a cloud model — this also guarantees verbatim quotes, since Claude reads the actual transcript rather than trusting another model's claimed quote.
- **MCP servers**: `oura` (biometrics, via `scripts/run-oura-mcp.mjs`) and `excel` (`@negokaz/excel-mcp-server`), both registered in `.mcp.json`.
- **Protective hooks**: `.claude/settings.json` denies edits to `.env` and blocks destructive/move Bash commands touching `.env` or `Sources/Paid/`.
- **Statistical honesty over statistical impressiveness.** `scripts/oura_analyze.py` refuses to model below a minimum row count, refuses a tag comparison below a minimum per-group size, and FDR-corrects every multiple-comparison test before anything gets called "significant." A near-zero or negative cross-validated R² is reported as a real finding ("no signal found"), not hidden. Circularity is flagged explicitly (e.g. predicting a score from its own published sub-components looks artificially good and isn't a discovery).
- **Anti-fabrication is load-bearing, not a disclaimer.** Never invent a reference range, a citation, a person's identity/credentials, a family-history mapping, or a study's methodology. An ambiguous or single-weak-source name gets left as an unresolved reference, not a stub — this has caught real near-misses (name confusions, garbled aggregation artifacts) in practice, not just in theory.
- **Legitimate sourcing only.** Book discovery never fetches unauthorized full text of in-copyright works — Internet Archive's controlled-digital-lending is deliberately excluded as a source, not merely deprioritized, since its legal status is genuinely contested.
- **The Web's grouping is a view concern, not a data concern.** Every `People`/`Concepts` note carries enough metadata (tier, derived_tier, confidence, topics) to regroup the graph by any property at any time via Extended Graph or a Base view — trying a new "webbing scheme" means changing what property you group by, never reprocessing data.

## Troubleshooting

**YouTube transcript fetching returns `IpBlocked`/`RequestBlocked` or `429 Too Many Requests` on subtitle downloads.** This is a genuine IP-level restriction from YouTube, not a bug in this tooling — confirmed to persist for a full day or more once triggered, and confirmed to be specific to the caption-serving endpoint (general video/audio download is unaffected). It's very likely triggered by running many channel-ingestion agents concurrently against fresh channels from the same IP — always process channels sequentially, not in parallel, to avoid it. If it happens:
1. **A genuinely different IP** (e.g. a mobile hotspot) works immediately and for free, if available — this is the fastest fix. Verify the machine is actually routing through it (`curl https://api.ipify.org`) before retrying — a hotspot that silently drops back to the original network looks identical to a fresh ban otherwise.
2. **A rotating residential proxy** (Webshare is built directly into `youtube-transcript-api` via `WebshareProxyConfig`) is the documented, reliable paid fix if a different IP isn't practical.
3. Cookie-based authentication is **not** a working fix — it's currently broken upstream in `youtube-transcript-api` itself.
4. **Third-party "free transcript" sites are not a safe alternative** — at least one (a site that Whisper-transcribed Huberman Lab episodes) has already been taken down following a legal notice. Real, demonstrated legal risk, not a theoretical one — treated the same way this vault excludes Internet Archive's contested lending library from `/book-discovery`.
5. **Local transcription is built and wired in as an automatic fallback** (`scripts/whisper_transcribe.py` + `ffmpeg` on PATH): downloads only the audio track (unaffected by the caption-endpoint block) and transcribes it locally. `youtube-channel.md`/`youtube-queue.md` fall back to it automatically on `IpBlocked`/`RequestBlocked`/`429` specifically — notes made this way get `transcript_source: whisper-local` in frontmatter, since it's the platform's audio transcribed by us rather than its own official captions. **Engine: [`whisper.cpp`](https://github.com/ggml-org/whisper.cpp)**, built from source (not redistributed here — see Prerequisites and `CONTRIBUTIONS.md` for swapping this out for a different engine, e.g. if you're not on Windows ARM64).

**`yt-dlp` audio download fails with `403 Forbidden` or "Requested format is not available."** Usually not an anti-bot/authentication issue despite how it looks — it's yt-dlp needing an updated JS-challenge-solver component it doesn't bundle by default. Fix: add `--remote-components ejs:github` to the yt-dlp invocation (already present in `scripts/whisper_transcribe.py`'s `download_audio()` as of 2026-07-27). Cookie-based authentication was investigated as an alternative fix and found to be a dead end on Windows specifically — modern Chrome/Edge's Application-Bound Encryption blocks any external tool (including yt-dlp) from decrypting their cookie store, and yt-dlp's own OAuth2 login was removed in current releases — the `--remote-components` flag above is the actual fix, not cookies.

## History rewrites

If you ever need to scrub content from git history (e.g. something got committed that shouldn't have been), use [`git-filter-repo`](https://github.com/newren/git-filter-repo) (`pip install git-filter-repo`), not `filter-branch`. This is a destructive, force-push operation — back up first and confirm with anyone else who has a clone before doing it.
