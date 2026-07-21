# Health Vault — tooling

This repo holds the **tooling** for a local-first Obsidian "second brain" covering athletic performance, physical health, and mental health research. It replaces NotebookLM: sources (PDFs, YouTube channels, web research) get converted into structured, cross-linked, contradiction-checked notes, correlated against Oura biometrics, and adversarially critiqued for weak claims.

**This repo does not contain the vault's actual content.** Concepts, Sources, Protocols, Daily notes, Synthesis, Research output, and all logs are gitignored and stay local-only — see `.gitignore` and the "Repo scope" section of `CLAUDE.md`. What's here is the generic, reusable machinery: custom commands, MCP server wiring, and configuration. Full behavior/architecture docs live in `CLAUDE.md` and `_CLAUDE.md`.

## Prerequisites

- [Obsidian](https://obsidian.md/) — the vault viewer/editor itself
- [Claude Code](https://claude.com/claude-code)
- Python 3.11+ with `pip`
- Node.js 18+ with `npm`/`npx`
- [`uv`](https://docs.astral.sh/uv/) (Python package manager, used by the `obsidian-second-brain` skill's isolated environment)
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`jq`](https://jqlang.org/) on PATH
- [GitHub CLI (`gh`)](https://cli.github.com/) if you want to push a fork/clone of this tooling to your own private repo
- An [Oura Ring](https://ouraring.com/) personal access token if you want biometric correlation (optional — everything else works without it)

## Setup (fresh machine)

1. Clone this repo into your vault folder (or clone into an empty folder and treat it as the vault root — Obsidian just needs a folder to open).
2. Create the vault content folders (these are gitignored, so they don't come with the clone):
   ```
   mkdir Sources Sources/Paid Concepts Protocols Daily Synthesis Synthesis/Channels Synthesis/Critiques Research Research/YouTube Research/Web Logs Bases
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
7. Open the folder in Obsidian as a vault.
8. In Claude Code, run `/vault-update` once to confirm the tool stack resolves correctly.

## Custom commands

All defined in `.claude/commands/`. Full behavior documented in `CLAUDE.md`.

| Command | Purpose |
|---|---|
| `/youtube-channel [url]` | Ingest every video from a channel — resumable, permanently excludes inactive/sparse channels, filters ad/sponsor content, no API key required |
| `/youtube-queue` | Process a curated list of video/channel links from `YouTube Queue.md` |
| `/storm-panel [question]` | 4-perspective grounded synthesis panel over the vault's own sources |
| `/concept-audit [concept \| "all"]` | Adversarially critique concepts — weak claims, verified against actual studies via `/research --academic`, plus online sentiment |
| `/vault-update` | Update the local tool stack and refresh all tracked YouTube channels for new videos — runs weekly via a local Windows Scheduled Task |

## Architecture notes

- **No cloud RAG.** The `obsidian-second-brain` skill's built-in keyword + optional local-Ollama semantic search covers this; no separate `mcp-local-rag`/`Agent-Reach` server is used.
- **No API key required for YouTube ingestion.** Transcript fetching (`youtube-transcript-api`) and metadata (`yt-dlp`) are both free; Claude writes the summary/quotes directly rather than delegating to a cloud model — this also guarantees verbatim quotes.
- **MCP servers**: `oura` (biometrics, via `scripts/run-oura-mcp.mjs`) and `excel` (`@negokaz/excel-mcp-server`), both registered in `.mcp.json`.
- **Protective hooks**: `.claude/settings.json` denies edits to `.env` and blocks destructive/move Bash commands touching `.env` or `Sources/Paid/`.

## History rewrites

If you ever need to scrub content from git history (e.g. something got committed that shouldn't have been), use [`git-filter-repo`](https://github.com/newren/git-filter-repo) (`pip install git-filter-repo`), not `filter-branch`. This is a destructive, force-push operation — back up first and confirm with anyone else who has a clone before doing it.
