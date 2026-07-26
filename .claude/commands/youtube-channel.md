---
description: Ingest a YouTube channel into the vault - every video the channel ever published gets at least a relevance check by default (resumable, checkpointed per-video so an interrupted run loses nothing, permanently excludes inactive/sparse channels, discards off-topic videos before full processing, skips ads/sponsor segments), then link concepts across the run, fill gaps via /research, and update a standing "Channels to Follow" recommendation note. Pass --limit N to bound a single run if you want a quick partial pass instead. --visual for frame reading.
category: research
---

Use this together with the obsidian-second-brain skill's `/research` machinery. Execute `/youtube-channel [channel url] [--limit N] [--visual]`:

**No open-ended scoping questions, ever.** This command runs both interactively and unattended (scheduled tasks, `/youtube-queue` batches) — a question that blocks waiting for an answer is fatal in the unattended case, since there's no one there to answer it and the run just exits having done nothing. Apply the default below automatically and report it loudly in the summary instead of asking.

**There is no background for this process. Ever. Do not say there is.** When invoked unattended (`claude -p`, a scheduled task, or as a `/youtube-queue` hand-off), this is a single synchronous invocation — once it produces its final response and exits, the process is gone. Never write "I'll keep triaging/processing in the background and report back once it's done" — that sentence is false in this execution mode and produces a run that does nothing further after printing it. If there's more work (more videos in this channel, more triage to do), keep doing it synchronously in this same invocation no matter how long it takes — hours is fine, a fake async promise is not. Work only legitimately carries over via this channel's own state file and `processed_video_ids`, picked up correctly by the *next actual invocation*, not by this process pretending to continue after exiting.

## 1. Resolve inputs
Accept a channel handle URL (`https://www.youtube.com/@handle`), a `/channel/UC...` URL, or a bare `@handle`. If none given, ask "Which YouTube channel?". Compute `channel-slug` (lowercased, hyphenated handle/name) for state and rollup filenames.

## 2. Check the permanent exclusion list FIRST
Read `Research/YouTube/.state/_excluded-channels.json` if it exists (`{"<channel-slug>": {reason, detail, excluded_date}}`). If this channel is already in it, **stop immediately** — report the exclusion reason/detail to the user and do not re-check activity or re-fetch anything. This list only changes if the user manually edits the file to remove an entry; never silently re-add or re-evaluate an excluded channel on your own.

## 3. Source triage — permanently exclude inactive or sparse channels
Only for channels not already excluded. Check:
```bash
yt-dlp --flat-playlist --print "%(upload_date)s" --playlist-end 1 "<channel-url>/videos"
yt-dlp --flat-playlist --print "%(id)s" "<channel-url>/videos" | wc -l
```
- **Inactive**: most recent upload is more than 18 months old (fixed default — don't ask, just apply it; report the threshold used in the summary).
- **Sparse**: fewer than 5 total videos (not enough content to be worth channel-level treatment — a single relevant video can still go through `/youtube-queue` instead).

If either triggers, write an entry to `Research/YouTube/.state/_excluded-channels.json` (`reason: "inactive"` or `"sparse"`, `detail` with the actual last-upload date or video count, `excluded_date: today`), report it to the user, and stop — do not enumerate or process any videos from this channel. This exclusion is permanent per step 2.

## 4. Load state (resumability)
Read `Research/YouTube/.state/<channel-slug>.json` if it exists: `{channel_url, channel_name, processed_video_ids[], last_run}`. If absent, this is a first run (empty processed list). Each entry in `processed_video_ids` is either a bare ID (legacy/successful) or `{id, status}` where `status` is `ok`, `failed`, or `skipped-irrelevant` — always treat any of the three as "already handled, do not reprocess."

## 5. Enumerate videos
```bash
yt-dlp --flat-playlist --print "%(id)s" "<channel-url>/videos"
```
(If the URL already points at a specific playlist/tab, use it as-is.) This is the full list — every video the channel has ever published, going back to its very first upload, not a recent window. Diff against `processed_video_ids` from state to find which are "new" (= not yet processed): **on a first-ever run for a channel, that's ALL of them** — for a prolific channel like Huberman Lab (hundreds of videos), that means hundreds of videos get queued for consideration in that first run. This is the intended behavior, not something to work around or sample down from.

**Default scope: literally every video, no cap, ever.** Every video a channel has ever published gets at least the relevance check in step 7.4 — that check is the actual filter (health/fitness/mental-health relevance), never a recency cutoff or a "most recent N" sample. Only apply `--limit N` if it was explicitly passed for this specific run; when it is, report the cap plainly and say explicitly "N more videos exist, re-run with a higher --limit or no --limit to continue" so any truncation is loud, never silent. A full back-catalog run on a prolific channel can take a long time (hours) — that's expected and correct given the ask, not a problem to solve by capping. Per-video checkpointing (step 8) means an interrupted run loses nothing and simply resumes exactly where it left off.

## 6. Resolve SKILL_ROOT
```bash
find ~/.claude/plugins/cache/obsidian-second-brain -maxdepth 3 -type d -name commands | sed 's#/commands$##'
```

## 7. Per-video ingestion — Claude writes the note directly (no external LLM call, no key needed)
The skill's own `/youtube` command delegates summarization to a cloud call (Gemini/Grok) that hard-requires an API key. We don't use that path: transcript fetching is free and key-less, and Claude (already in this session) writes the note directly — this also guarantees verbatim quotes are pulled from the real transcript, not a second model's paraphrase.

For each new video ID, in order:

1. Fetch free metadata via yt-dlp, including description (no key needed):
```bash
yt-dlp --skip-download --print title --print description --print channel --print upload_date --print duration_string --print view_count --print like_count "https://www.youtube.com/watch?v=<video-id>"
```
2. Fetch the transcript via the single unified entry point — **do not call the official-captions path and the Whisper fallback separately, and never decide yourself which one to use.** `scripts/fetch_transcript_auto.py` already tries official captions first and automatically falls back to local Whisper transcription (audio download + `faster-whisper`) if that fails with `IpBlocked`/`RequestBlocked`/`429` — this is fully automatic, no judgment call needed on your part:
```bash
python scripts/fetch_transcript_auto.py "<video-id>" > "<tmp-file>" 2> "<diag-file>"
```
Check `<diag-file>` (stderr) for which method actually produced the transcript — it prints `method: official captions` or `method: local whisper`. If it's `local whisper`, set `transcript_source: whisper-local` in the video's frontmatter in step 6 (omit the field entirely for the normal official-caption path — same "verbatim from what was actually read" guarantee either way, just worth being honest about the origin). Needs `ffmpeg` on PATH and `faster-whisper` installed for the fallback to work — if both methods fail (exit code 1), the diagnostic file explains why (genuine caption absence vs. a missing local dependency vs. both methods blocked). Never use a third-party "free transcript" site as a substitute — at least one has already been taken down over this exact use case, real demonstrated legal risk, not a theoretical one.
3. If the transcript is still empty after this (script exited 1), log it as failed and move on — do not fabricate content.
4. **Relevance check.** Before doing any real extraction, judge whether this video is about health, fitness/athletic performance, or mental health in any way. Decide from title + description first; if genuinely ambiguous, read the first ~2000 characters of the fetched transcript before deciding — don't skip straight to a transcript read for every video, only when title/description doesn't settle it. If it's not related in the slightest (e.g. a fitness channel's off-topic vlog, unboxing, unrelated Q&A), **discard**: do not write a `Research/YouTube/` note, add its ID to `processed_video_ids` tagged `skipped-irrelevant` in state so it's never re-checked, and record it in the rollup's skipped list with a one-line reason. Move to the next video.
5. Read the transcript file yourself (Read tool) and write the note. Before treating anything as a "concept," identify and exclude promotional material — sponsor reads/ad-reads, "use code X" segments, unrelated third-party product pitches, the creator's own paid-course/consult pitches, Patreon/membership asks. Leave the raw transcript untouched conceptually (don't let promo segments generate or update Concept notes, don't count them toward "recurring concepts" in step 9). If a video is ENTIRELY promotional, note it as content-free in the rollup instead of forcing an extraction.
6. Save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` with `type: youtube` frontmatter (date, time, video-id, video-url, title, channel, published, view-count, like-count, duration, tags: [research, youtube], `ai-first: true`, `cost-usd: 0`, and `transcript_source: whisper-local` only if step 7.2b's fallback was used — omit the field entirely for the normal platform-caption path) and body:
   - `## For future Claude` preamble noting this is Claude-written directly from the free transcript (no external summarization model), quotes are verbatim.
   - `## TL;DR` (2-3 sentences)
   - `## Key Points` (5-12 specific bullets, promo material excluded)
   - `## Notable Quotes` — **verbatim only, copied character-for-character from the transcript text you read, never paraphrased or reconstructed from memory.** Quote what's actually in the transcript.
   - `## Themes & Topics`
   - `## Worth Following Up On`

If a video fails (no captions, private, deleted), log it and continue — one bad video never aborts the run. Append its ID to `processed_video_ids` (status `failed`) regardless (so we don't retry a permanently-broken video every refresh) but mark it failed in the rollup.

## 8. Checkpoint after EVERY video, not once at the end
Immediately after each video finishes (success, failure, or discard as irrelevant) — before moving to the next one:
1. Re-write `Research/YouTube/.state/<channel-slug>.json` with that video's result merged in (`processed_video_ids`, `channel_url`, `channel_name`, `last_run: <today>`). Do not batch this until the channel finishes — a run killed mid-channel must not lose progress on videos already completed.
2. Append one line to `Logs/youtube-ingest-progress.log` (create if absent): `YYYY-MM-DD HH:MM | <channel> | <video-id> | <ok|failed|skipped-irrelevant> | <short title>`. This is a clean, tail-friendly progress feed distinct from the command's full conversational output — the thing to watch for live status during a long unattended run.

This makes every video its own checkpoint: if the process is interrupted at any point, state and note-writes up to that point are already durable, and simply re-running the same command (or the `/youtube-queue` line it came from) picks up exactly where it left off via `processed_video_ids` — no re-fetching, no duplicate notes, no lost work beyond the one video in flight when it stopped.

## 9. Connect & deepen (only over videos processed THIS run)

**Concept notes are the primary reading layer of this vault; per-video `Research/YouTube/` notes are raw material, not first-class content.** A video note's job is to preserve verbatim quotes and provenance for citation — not to sit alongside Concept notes as independent standalone articles. Every run should leave `Concepts/` genuinely more thorough, not just more cross-linked.

1. **Aggregate concepts**: list every Concept this run's videos touched (excluding filtered promo material), with counts.
2. **Actively absorb, don't just link**: for each video that substantively addresses an existing Concept (not just a passing mention), rewrite that Concept note to actually incorporate the new material — new evidence, a new angle, a nuance the existing note lacked — the way `/obsidian-ingest` rewrites pages, not a bare `[[wikilink]]` bolted onto the bottom. If a video is genuinely the primary source for a Concept that doesn't exist yet, create it properly (structured, thorough, not a stub).
3. **Mark absorption on the video note itself**: once a video's substantive content has been fully incorporated into a Concept note, prepend one line right under the video note's frontmatter: `> [!info] Fully absorbed into [[Concepts/<name>]] — see there for the synthesized version. This note remains for verbatim quotes and citation.` This is what keeps `Research/YouTube/` from reading as a pile of independent duplicate articles once its substance lives properly in `Concepts/`. Don't add this if the video only partially overlaps a Concept — only when its substance is genuinely covered.
4. **Cross-link between Concepts**: where a video explicitly related two concepts, add/update `[[wikilinks]]` between those Concept notes too — the graph should reflect real connections, not just video-to-concept links.
5. **Find gaps**: concepts mentioned but never explained, claims without a stated mechanism, or contradictions between videos in this run left unresolved.
6. **Fill gaps**: for gaps central to the channel's throughline (not every passing mention), run `/research [gap topic]` (key-less by default) and use the result to extend the relevant Concept note — clearly mark that material as externally sourced, not from this channel, with its own citation.
7. Any contradiction between a video's claim and an existing vault note gets the normal `[!contradiction]` callout — never silently overwrite.

## 10. Rollup note
Write/update `Synthesis/Channels/<channel-name> - Channel Rollup.md`:
- `## For future Claude` preamble per `references/ai-first-rules.md` (SKILL_ROOT).
- Frontmatter: `type: channel-rollup`, `channel`, `channel-url`, `video-count-total`, `video-count-new-this-run`, `video-count-relevant`, `video-count-discarded-irrelevant`, `date`, `tags`.
- `[[wikilink]]` to every per-video note created/updated this run.
- Recurring concepts this run (with counts), and which are new links vs. reinforced existing ones.
- Contradictions surfaced this run, with links.
- Gaps filled this run (link to `/research` output used) and gaps still open.
- Videos skipped/failed and why, split into "failed (technical)" and "discarded (off-topic)".

## 11. Update "Channels to Follow"
Write/update the single shared note `Synthesis/Channels to Follow.md` (not per-channel — one running list across every channel ever processed). For this channel, add or update its entry:
- **Relevance hit-rate**: relevant videos / total videos checked this run (and cumulatively, if the channel has a prior entry).
- **Content signal**: does this channel consistently produce substantive, on-topic material, or was it mostly filler/promo even among the "relevant" videos?
- **Recommendation tier**: `follow closely` (consistently valuable, prioritize future runs), `follow loosely` (occasionally useful, low priority), `deprioritize` (mostly irrelevant or thin, technically not excluded but not worth actively re-checking often).
- Link to the channel's rollup note.

Do not duplicate this into the per-channel rollup — the rollup is about this run's content, `Channels to Follow.md` is the standing recommendation list across all channels.

## 12. Summary to user
Cap applied this run (none by default, or `--limit N` if passed), total videos on channel, new this run, how many were left over an explicit cap (if any — with the re-run instruction from step 5), failed, discarded as irrelevant, concepts linked, gaps filled, rollup note path, and this channel's recommendation tier. If this is a re-run, explicitly say "N new videos since last run on <date>". If excluded at step 3, this is the whole report (no rollup/follow-list update needed for an excluded channel).

**Anti-fabrication:** never invent a video's content if extraction failed, never invent a gap-fill fact — `/research` output only, cited. See `references/ai-first-rules.md` in SKILL_ROOT.
