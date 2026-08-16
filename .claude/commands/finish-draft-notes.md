---
description: Turn local-LLM-generated drafts (scripts/generate_draft_notes.py, Research/*/Raw/.drafts/*.json) into real AI-first notes - the Phase 6-alt companion to /process-raw-transcripts, reading a draft scaffold instead of the full raw transcript to cut context per file. Same single-sequential-agent discipline, same anti-fabrication rules.
category: research
---

Execute `/finish-draft-notes [--batch-size N] [--target youtube|podcast|both]`:

> [!warning] There is no `--parallel` flag, deliberately — same reasoning as `/process-raw-transcripts` (2026-07-26 rate-limit incident, see `buglog.md`). One single sequential agent, never per-file dispatch.

> [!info] **What a draft actually is, and isn't.** `scripts/generate_draft_notes.py` runs `qwen2.5:14b` (local, on the CachyOS machine) against a raw transcript and writes a structured scaffold to `Research/*/Raw/.drafts/<video_id>.json`: a relevance guess, a signal-density guess, themes, key points, and quotes. **Per the real Phase 5 A/B validation (2026-08-15, 9 videos against Claude's own already-written notes): this model's signal-density judgment matched Claude's only 3/9 of the time (systematically over-rating density), and only 13/26 of its claimed-verbatim quotes were genuinely exact substrings of the source** (the other half were rejected by the script's own programmatic verbatim gate before ever reaching the draft file — so every quote actually present in a draft has already passed that mechanical check, but a mechanical substring match is not the same guarantee as "this is what the speaker meant in context," so don't skip judgment entirely). A draft is a **reading aid that cuts how much of the raw transcript you need to read closely**, not a pre-approved note. Treat `signal_density_guess` as a hypothesis to confirm or correct, not a fact — the draft file's own `signal_density_confirmed: false` field exists specifically to flag this.

## 1. Find drafted-but-unfinished files
Read `Research/YouTube/Raw/.drafted_ids.json` and/or `Research/Podcasts/Raw/.drafted_ids.json` (per `--target`) — every entry there has a `draft_file` pointing into `.drafts/`. Cross-check against `.processed_ids.json` in the same directory: a video already `ok`/`skipped-*` in `.processed_ids.json` is already finished, skip it (this can happen if a manual `/process-raw-transcripts` run touched it before this command did). Default `--batch-size 20` if not specified.

Also run `python scripts/find_cross_stream_duplicates.py` first, same as `/process-raw-transcripts` step 1 — zero-cost, keeps the dedup cache fresh.

## 2. Per-video finishing step, single agent, sequential
For each drafted video in the batch:

- **Read the draft JSON first** (`themes`, `key_points`, `notable_quotes_verified`, `signal_density_guess`, `relevant`) — this is your fast orientation, not your source of truth for the note body.
- **Read the raw transcript** (`Research/*/Raw/<source_file>`, named in the draft) — you still need to read it, but with the draft's scaffold already telling you roughly what's in it and where the substantive content sits, this read can move faster than starting cold.
- **Dedup check** — same three-stage process as `/process-raw-transcripts` step 2 (check `Research/.dedup_candidates.json` first, cheap metadata fallback, content spot-check only if genuinely ambiguous). If confirmed duplicate: mark `processed_ids[video_id] = {"status": "skipped-duplicate-of-<youtube|podcast>"}` in the real `.processed_ids.json`, remove the entry from `.drafted_ids.json`, delete the draft file, move on.
- **Confirm or correct relevance** — the draft's `relevant` guess is usually right (this is a coarser judgment than signal-density and the model does better at it) but verify against the actual transcript, especially for anything the draft flagged as borderline. Off-topic → `processed_ids[video_id] = {"status": "skipped-irrelevant"}`, remove from `.drafted_ids.json`, delete the draft file.
- **Confirm or correct signal-density** — treat the draft's guess as a starting hypothesis. Given the measured bias toward over-rating density, be specifically skeptical of a `"high"` guess on a short or clearly-thin video — check it against the actual substantive-content-to-runtime ratio yourself, same criteria as `/process-raw-transcripts` step 2's signal-density section. Same three-tier depth scaling applies (`high`/`mixed`/`low` — see that command for the exact per-tier structure, unchanged here).
- **Key points**: the draft's list is a real starting point (its own hallucination risk on plain factual summarization is much lower than on verbatim quoting), but verify against the transcript rather than copying blind — check for anything the model missed, anything it got subtly wrong, and confirm promotional/sponsor content was correctly excluded.
- **Quotes**: `notable_quotes_verified` already passed a mechanical exact-substring check against the source transcript (see the warning above) — but re-confirm each one actually says what it appears to say in context, and feel free to pull additional/better verbatim quotes directly from the transcript yourself if the draft's selection is thin or the video is `high` density and warrants more than the draft's 2-5 candidates. Never add a quote you haven't personally verified against the actual transcript text, draft or not.
- **Themes**: useful as a starting tag list for `## Themes & Topics`, verify/expand same as key points.
- **Researchers & Sources Cited**: the draft does NOT extract this — do it fresh from the transcript, exactly as `/process-raw-transcripts` step 2 describes (named individuals cited as sources of expertise, stub new `People/` notes, dedupe against existing ones first).
- Write the note with the same structure as `/process-raw-transcripts` (`## For future Claude`, `## TL;DR`, `## Key Points`, `## Notable Quotes`, `## Themes & Topics`, `## Worth Following Up On`, `## Researchers & Sources Cited`), same signal-density-scaled depth rules, same frontmatter conventions (`type: youtube`/`type: podcast`, `cost-usd: 0`, `signal_density`, `transcript_source` carried from the raw file's header, `ai-first: true`). Save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` (or `Research/Podcasts/...`).
- **Checkpoint after every single file**: mark `processed_ids[video_id] = {"status": "ok", "note": "<path>", "signal_density": "...", "people_discovered": [...]}` in the real `.processed_ids.json` (read-modify-write), remove the entry from `.drafted_ids.json`, and delete the now-consumed draft file from `.drafts/`. Same interrupted-run-loses-at-most-one-file discipline as `/process-raw-transcripts`.

## 3. Sequential concept-linking pass (after the whole batch finishes)
Identical to `/process-raw-transcripts` step 3 — does not parallelize, check `Research/.concepts_absorbed.json` first, actively absorb (not just link), mark absorbed notes with `> [!info] Absorbed into Concepts`, flag real contradictions with `[!contradiction]`, must complete or be cleanly resumed.

## 4. Rollup
Same as `/process-raw-transcripts` step 4.

## 5. Summary
Batch size, relevant/discarded/failed split, signal-density breakdown, **how many signal-density guesses were confirmed as-is vs. corrected** (a real signal for whether the draft model's calibration is improving or degrading over time — worth tracking across runs), dedup breakdown, concepts created/deepened, new `People/` stubs, rollup notes updated, how many drafted-but-unfinished files remain, and how many raw files still have no draft at all (still waiting on the Stage-6-alt timer).

**Anti-fabrication:** identical bar to `/process-raw-transcripts` and every other ingestion command in this vault — verbatim quotes only from the actual raw transcript text you personally read, never invent a gap-fill fact, and never let a draft's own claim substitute for your own verification.
