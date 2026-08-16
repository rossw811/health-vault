# New-machine setup — read this first if you're Claude Code running on the CachyOS PC

## For future Claude (on the new machine)

You're a fresh Claude Code session with zero memory of the conversation that produced this document. Here's what you need to know to pick this up correctly.

**What this vault is**: a local-first Obsidian vault for athletic performance, physical health, and mental health research (`CLAUDE.md`, checked into this repo, has the full standing rules — read it before doing anything else, it overrides defaults). This repo (`github.com/rossw811/health-vault`, public, tooling-only) tracks scripts/commands/config; the actual vault content (`Concepts/`, `Research/`, `Optimization/`, etc.) is gitignored and arrives separately via Syncthing, not git.

**Why this document exists**: Ross is migrating to this machine (i7-10700K, 48GB DDR4-3600, RTX 4080 16GB VRAM, CachyOS/Arch) from a Windows machine that's been running this vault's full pipeline for weeks. The goal is threefold, in priority order: (1) get everything working here, (2) keep both machines in sync via Syncthing so both stay usable, (3) move the GPU-bound work here — Whisper transcription first, and *if it validates well enough* (see the gate below — don't skip it), local-LLM note-writing too.

**Do not skip the validation gate described below just because it would be faster to build the full pipeline directly.** Ross was explicit about this when the plan was made: test the local model against Claude's actual existing output *before* investing in pipeline automation, and if it's not good enough, build the lighter "assisted-draft" version instead of forcing the full replacement. This matches the vault's own standing rule, documented in `buglog.md`'s 2026-07-27 QNN-Whisper entry: *"doesn't pass the standing 'compare to original, bug-test, only execute if it passes' bar, so per that rule it stays out of production."* Apply that same bar here.

---

## What's already done (on the Windows machine, before this migration)

- Full vault backup archived (Phase 0) — ask Ross where he put it if you ever need to verify against a known-good snapshot.
- Nothing else — the physical transfer, Syncthing setup, and everything past it is genuinely your job, starting fresh.

## The phases (do them in order — each depends on the last actually working, not just being attempted)

### Phase 1 — Confirm the file transfer landed clean
- The vault should already be copied to this machine (external drive or direct transfer — not Syncthing yet, that's Phase 2). Confirm the path (likely `~/Health` or wherever Ross put it) has the expected top-level folders: `Concepts/`, `Research/`, `Optimization/`, `Protocols/`, `People/`, `scripts/`, `.claude/`, `Daily/`, plus this file and `CLAUDE.md`.
- Install the toolchain via `pacman`/`yay` (CachyOS, Arch-based — **not** `winget`, that's a Windows-only assumption baked into some of the existing `.ps1` scripts you'll be replacing): Python (check `pyproject.toml`/`requirements.txt` for the version this vault expects), `uv`, Node.js (needed — see the yt-dlp JS-challenge-solver note below), ffmpeg, Git, the Claude Code CLI, and the `obsidian-second-brain` plugin.
- **`~/.config/obsidian-second-brain/.env` needs recreating on this machine** — it's global-per-machine config (API keys, `OBSIDIAN_VAULT_PATH`), not part of the vault itself, and won't have transferred. Ask Ross for the values, or check if he already set it up here.
- `git remote -v` and `git log` to confirm this clone can still push/pull to `github.com/rossw811/health-vault`.
- **Verify before proceeding**: open a few real files and confirm they're intact and readable (`Protocols/My Profile.md`, a recent `Daily/` note, `buglog.md`). Don't assume a clean transfer — check it.

### Phase 2 — Syncthing
- Install Syncthing on both this machine and the Windows one, pair them, share the vault folder.
- Set up `.stignore` (Syncthing's own ignore file — separate from `.gitignore`): exclude `.git/`, `.venv/`, `.ruff_cache/`, `__pycache__/`. Everything else — including all the gitignored real content — **should** sync; that's the entire point of Syncthing here.
- Let the first sync complete, then diff file counts on both machines before trusting it.
- **Decide with Ross which machine runs Stage-1 collection** (the YouTube/podcast raw-transcript collectors) — running both simultaneously risks two machines racing on the same lock files with no distributed locking to protect against it (`.collector.lock`, `.collected_ids.json`, `.processed_ids.json`). The plan's recommendation was this machine (better hardware for the GPU-Whisper work in Phase 3) with the Windows machine's equivalent scheduled tasks disabled once this machine is confirmed stable.

### Phase 3 — GPU-accelerated Whisper transcription
- Build `whisper.cpp` here with CUDA support. This is a **fresh Linux build, not a port** of the existing Windows `whisper-cli.exe` binary — Linux CUDA builds are generally more straightforward than the Windows path this vault went through (see `buglog.md`'s 2026-07-27 entries for the full QNN/ARM64 saga that was eventually abandoned in favor of whisper.cpp CPU — don't repeat that detour, CUDA-on-Linux is a cleaner path).
- `scripts/whisper_transcribe.py` needs real porting, not a path swap: it currently shells out to a Windows binary and assumes a winget-style ffmpeg install (see `run-youtube-queue-loop.ps1`'s dynamic `ffmpeg-*` folder lookup). Keep the same external function signatures (`load_model()`, `transcribe()`, `transcribe_video()`) so the collectors don't need to change, but expect the internals to actually differ here.
- Validate speed AND quality against the existing CPU baseline (127s/152s on the documented reference clips, if Ross still has them) before trusting it — faster but lower-quality would be a real regression, not a win.
- **No Windows Task Scheduler here.** Recreate `HealthVault-YouTubeQueue-Loop`, `HealthVault-PodcastQueue-Loop`, `HealthVault-ReapOrphans`, `HealthVault-BacklogHealthCheck` as systemd user timers (better fit for the "keep running, restart on failure" shape than cron). The actual loop logic in the `.ps1` wrappers is thin — worth porting to a small cross-platform Python wrapper rather than a separate bash reimplementation that'll drift from the Windows version.
- `reap_orphans.ps1` and `stop-collectors.ps1` are PowerShell-specific and need real Linux rewrites (`psutil`-based Python is probably cleanest) — keep the same safety properties: never a bare process kill, confirm real parent-process-death before reaping an orphan, explicit handling for `whisper-cli` since it's a plain subprocess child with no multiprocessing `spawn_main` signature to match on.

### Phase 4 — Local LLM
- Install Ollama.
- **Don't trust any model recommendation baked into an old plan document — check `ollama.com/library` directly, today, when you actually do this.** Model rankings move fast; treat any specific model name suggested to you the same way this vault treats an uncited claim: a lead to verify, not a fact to act on. As of when this plan was drafted (Aug 2026), the ~14B tier was the practical ceiling for 16GB VRAM with usable context headroom (Qwen3-14B and similarly-sized Llama-family models were the leading candidates) — verify that's still accurate before committing to a model.
- Context length matters more than parameter count for this use case — multi-hour Huberman/Attia episodes run 30-40K+ tokens. Prioritize genuine long-context support.

### Phase 5 — THE VALIDATION GATE (do not skip, do not build Phase 6 first)
- Pick 5-10 videos Claude has already fully processed (real notes exist — ground truth to compare against).
- Feed the same raw transcripts to the local model, no pipeline scaffolding, just direct prompt-and-compare: ask it to do the whole job (relevance call, signal-density call, Key Points, verbatim Notable Quotes, Themes & Topics).
- **Score it honestly, by hand**: do the relevance/density judgments match Claude's actual calls? Are the "verbatim" quotes actually verbatim — string-search each one against the source transcript yourself, don't trust the model's claim that it's quoting accurately? Does Key Points coverage match, or does it miss things / invent things?
- **This score decides which pipeline you build**, not a preference:
  - Genuinely close to Claude's judgment, quotes check out as real substrings, no fabrication → build Phase 6 (full local pipeline).
  - Quotes drift, judgment disagrees often, or you catch real fabrication → build Phase 6-alt (assisted-draft mode) instead.

### Phase 6 — Full local pipeline (only if Phase 5 passed)
New script (e.g. `scripts/process_raw_transcripts_local.py`), plain Python calling Ollama's API:
1. Dedup — reuse `scripts/find_cross_stream_duplicates.py`'s `.dedup_candidates.json` output directly, no LLM call needed, already built.
2. Relevance — one LLM call, structured `{relevant: bool, reason: str}`.
3. Signal-density — one LLM call, `{density: "high"|"mixed"|"low", reason: str}`.
4. Note generation — the six sections `.claude/commands/process-raw-transcripts.md` already documents in full. **Add a hard, non-LLM verification gate on Notable Quotes regardless of how well Phase 5 scored**: programmatically check every claimed quote is an exact (whitespace-normalized) substring of the actual transcript; reject/regenerate anything that doesn't verify. A model that passed spot-checking can still drift at scale — this costs nothing and catches it every time.
5. Researchers & Sources Cited — LLM extraction, then a fuzzy-match Python step (not LLM) against existing `People/` notes before creating a new stub.
6. Checkpoint `.processed_ids.json` after every single file (read-modify-write, not overwrite) — same pattern the existing pipeline already uses safely.
7. **Do not have the local model do concept-linking.** New video notes accumulate; a periodic Claude Code batch (the proven "one single sequential agent" pattern — see `.claude/commands/process-raw-transcripts.md` step 3 and `buglog.md`'s 2026-07-26 rate-limit incident for why it must stay sequential, never per-file parallel dispatch) does the actual `Concepts/`-folding work on whatever cadence Ross wants.

### Phase 6-alt — Assisted-draft mode (if Phase 5 didn't pass)
Same script shape, lower-trust output: the local model produces a structured rough draft per video (candidate Key Points, candidate quotes — still run through the same verbatim-verification gate, failing candidates just get dropped — a topic list, and an unconfirmed-flagged relevance/density guess) saved alongside the raw transcript instead of a finished note. A Claude Code batch reads the *draft*, not the full raw transcript, to finish the note — shorter context per file, real efficiency gain, without pretending the local model's judgment is trustworthy unsupervised.

### Phase 7 — Ongoing operation
Whichever path Phase 5 sent you down, periodically re-run a small Phase-5-style spot-check by hand. Model quality and Ollama's library both keep moving — don't treat the original Phase 5 decision as permanent.

---

## Standing rules that apply to you exactly as much as they apply on the Windows machine

- **Anti-fabrication is non-negotiable.** Verbatim quotes only from what you actually read. Never invent a gap-fill fact. This applies to your own work building this pipeline too — if you don't know whether something transferred correctly, verify it, don't assume.
- **Never dispatch per-file parallel agents for note-writing.** One sequential agent, internal loop. See `buglog.md`'s 2026-07-26 entry for exactly why (a real rate-limit incident, 1 of 84 dispatched calls succeeded).
- **Never use destructive commands without checking state first.** `git status` before anything that could discard work. This vault has real personal health data in it — treat file operations with real care, not just code-review care.
- **When something doesn't match what this document says, trust the live system over this document.** This was written from the Windows-machine side of the migration; if reality has diverged (a script got renamed, a path changed), say so and adapt rather than forcing the document's assumptions.

Read `CLAUDE.md` in full before starting Phase 1 if you haven't already — this document assumes it, doesn't restate it.
