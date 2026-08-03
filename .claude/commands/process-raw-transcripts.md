---
description: Turn raw transcripts collected by scripts/collect_raw_transcripts.py (Research/YouTube/Raw/*_full.txt) into real AI-first video notes - the step that needs Claude, done in controlled-concurrency batches now that budget allows, separated from the note-writing-independent raw collection itself.
category: research
---

Execute `/process-raw-transcripts [--batch-size N] [--parallel N]`:

## 1. Find unprocessed raw files
Read `Research/YouTube/Raw/.processed_ids.json` (create empty if absent: `{}`). Every `*_full.txt` file in `Research/YouTube/Raw/` whose `video_id` (from its own header) isn't yet a key in that file is unprocessed. Default `--batch-size 20` per run if not specified.

## 2. Per-video note-writing step, single agent, sequential
**Do NOT dispatch parallel subagents for this step, one per chunk or otherwise** — a real 2026-07-26 incident (see `buglog.md`) hit the account's session rate limit almost immediately from per-file/per-chunk parallel dispatch (81 files fanned out, 1 of 84 agent calls succeeded, the rest failed identically) for zero real output. The proven-safe pattern, used successfully multiple times since, is exactly the opposite: **one single `Agent` call whose own internal tool-call loop works through the whole batch sequentially** (read → judge relevance → write note → checkpoint state → next file), all within that one agent's own conversation. If grouping by channel is useful for concept-linking coherence, do it as an ordering choice within the single sequential loop, not as a basis for parallel dispatch. This overrides any general "parallel subagents are appropriate" instinct — it is not appropriate here, specifically because of the documented incident above.
- Read the raw file's header (metadata) and body (the transcript itself).
- **Relevance check** (same as `/youtube-channel` step 7.4): title/description first, transcript skim if ambiguous. Discard off-topic videos - mark `processed_ids[video_id] = {"status": "skipped-irrelevant"}`, no note written.
- If relevant: same body structure as `/youtube-channel` step 6 (`## For future Claude`, `## TL;DR`, `## Key Points`, `## Notable Quotes` - verbatim from the raw transcript text, never paraphrased - `## Themes & Topics`, `## Worth Following Up On`). Exclude promotional material from concept extraction per the same rules. Frontmatter carries over `transcript_source` from the raw file's header if it says `local whisper`, plus `type: youtube`, `cost-usd: 0`, etc.
- **Research & connections extraction (feeds the Web)**: while reading the transcript, separately watch for any real, identifiable named individual referenced as a source of expertise - an interviewee, a cited researcher, a study author, someone credited for a claim (not passing mentions, not "some studies show"). Add a `## Researchers & Sources Cited` section listing each one plus what claim/study they were cited for. For each name not already a `People/` note (dedup by name + any known handle, same rule as `/web-expand`), create a stub `People/` note (`discovered_via: "[[<this note>]]"`, `derived_tier` one hop out from whichever anchor/channel this video belongs to, `connection_type: "interview"` or `"influence"` per how they were referenced) and add it to a running "new people to research" list for this batch. This is exactly `/web-expand`'s discovery step, applied inline per-video instead of requiring a separate pass - the point is that no researcher/source mentioned in ingested content goes untracked as a potential Web connection.
- Save `Research/YouTube/YYYY-MM-DD - <title-slug>.md`, mark `processed_ids[video_id] = {"status": "ok", "note": "<path>", "people_discovered": ["<name>", ...]}` in the shared state file.

**Concurrency-safe state writes**: since multiple chunks run in parallel and all write to the same `.processed_ids.json`, each chunk must read-modify-write it defensively (read fresh immediately before writing its own entries, merge rather than overwrite) - or simpler, have each parallel chunk write to its own `.processed_ids.<chunk-n>.json` and merge all chunk files into the main one in a single sequential step after all chunks complete. Prefer the latter - it avoids any real race condition instead of hoping read-modify-write timing works out.

## 3. Sequential concept-linking pass (after all parallel chunks finish)
This step does NOT parallelize - it needs a holistic view across everything the whole batch touched, same as `/youtube-channel` step 9: aggregate concepts touched, actively absorb substantive content into `Concepts/` notes (rewrite/deepen, don't just link), mark absorbed video notes with the `> [!info]` pointer, cross-link related concepts, identify and fill real gaps via `/research`, flag contradictions with the normal `[!contradiction]` callout.

Also merge every chunk's `people_discovered` list into one batch-wide list, dedupe against existing `People/` notes exactly as `/web-expand` does (best tier/hop path wins), and finalize each new stub note's frontmatter. Do not run full literature/channel research on newly-discovered people in this same pass - that's `/web-expand`'s job on a follow-up run; this step only ensures they exist as tracked stubs so nothing is dropped.

## 4. Rollup
Same as `/youtube-channel` step 10 - update the relevant `Synthesis/Channels/<channel> - Channel Rollup.md` for each channel touched this batch, and `Synthesis/Channels to Follow.md`.

## 5. Summary
Batch size, parallel chunk count, relevant/discarded/failed split, concepts created/deepened, gaps filled, new `People/` stubs discovered this batch (names + who to `/web-expand` next), rollup notes updated, and how many unprocessed raw files remain in `Research/YouTube/Raw/` for a future run.

**Anti-fabrication:** same rules as every other ingestion command in this vault - verbatim quotes only from the actual raw transcript text, never invent a gap-fill fact.
