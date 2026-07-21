---
description: Ingest a YouTube channel into the vault (resumable, permanently excludes inactive/sparse channels, discards off-topic videos before full processing, skips ads/sponsor segments), then link concepts across the run, fill gaps via /research, and update a standing "Channels to Follow" recommendation note. Defaults to the 15 most recent videos per run - pass --all for the full back-catalog, --limit N for a different cap. --visual for frame reading.
category: research
---

Use this together with the obsidian-second-brain skill's `/research` machinery. Execute `/youtube-channel [channel url] [--limit N] [--all] [--visual]`:

**No open-ended scoping questions, ever.** This command runs both interactively and unattended (scheduled tasks, `/youtube-queue` batches) — a question that blocks waiting for an answer is fatal in the unattended case, since there's no one there to answer it and the run just exits having done nothing. Apply the default below automatically and report it loudly in the summary instead of asking.

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
(If the URL already points at a specific playlist/tab, use it as-is.) This is the full list. Diff against `processed_video_ids` from state — the videos actually eligible this run are only the new ones.

**Default scope: the 15 most recent new videos per run.** `--all` processes every new video regardless of count (only use this when explicitly passed — a large back-catalog channel run this way can take hours); `--limit N` sets a different cap. Report the actual cap applied, total videos found, how many are new, and — if the default cap left videos unprocessed — say explicitly "N more new videos exist, re-run with --all or a higher --limit to continue" so the truncation is loud, not silent. A capped run is always safe to re-run later: already-processed IDs are skipped via state, so repeated runs progressively work through a large back-catalog without reprocessing anything.

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
2. Fetch the free transcript (needed either way — for the relevance skim if title/description is ambiguous, or for the full note if it's relevant):
```bash
uv run --directory "SKILL_ROOT" python -c "
import sys
sys.path.insert(0, '.')
from scripts.research.lib.youtube import get_transcript
print(get_transcript(sys.argv[1]) or '')
" "<video-id>" > "<tmp-file>"
```
3. If the transcript is empty (no captions), log it as failed and move on — do not fabricate content.
4. **Relevance check.** Before doing any real extraction, judge whether this video is about health, fitness/athletic performance, or mental health in any way. Decide from title + description first; if genuinely ambiguous, read the first ~2000 characters of the fetched transcript before deciding — don't skip straight to a transcript read for every video, only when title/description doesn't settle it. If it's not related in the slightest (e.g. a fitness channel's off-topic vlog, unboxing, unrelated Q&A), **discard**: do not write a `Research/YouTube/` note, add its ID to `processed_video_ids` tagged `skipped-irrelevant` in state so it's never re-checked, and record it in the rollup's skipped list with a one-line reason. Move to the next video.
5. Read the transcript file yourself (Read tool) and write the note. Before treating anything as a "concept," identify and exclude promotional material — sponsor reads/ad-reads, "use code X" segments, unrelated third-party product pitches, the creator's own paid-course/consult pitches, Patreon/membership asks. Leave the raw transcript untouched conceptually (don't let promo segments generate or update Concept notes, don't count them toward "recurring concepts" in step 9). If a video is ENTIRELY promotional, note it as content-free in the rollup instead of forcing an extraction.
6. Save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` with `type: youtube` frontmatter (date, time, video-id, video-url, title, channel, published, view-count, like-count, duration, tags: [research, youtube], `ai-first: true`, `cost-usd: 0`) and body:
   - `## For future Claude` preamble noting this is Claude-written directly from the free transcript (no external summarization model), quotes are verbatim.
   - `## TL;DR` (2-3 sentences)
   - `## Key Points` (5-12 specific bullets, promo material excluded)
   - `## Notable Quotes` — **verbatim only, copied character-for-character from the transcript text you read, never paraphrased or reconstructed from memory.** Quote what's actually in the transcript.
   - `## Themes & Topics`
   - `## Worth Following Up On`

If a video fails (no captions, private, deleted), log it and continue — one bad video never aborts the run. Append its ID to `processed_video_ids` (status `failed`) regardless (so we don't retry a permanently-broken video every refresh) but mark it failed in the rollup.

## 8. Update state
Write `Research/YouTube/.state/<channel-slug>.json` with the merged `processed_video_ids` (each with its status: `ok` / `failed` / `skipped-irrelevant`), `channel_url`, `channel_name`, and `last_run: <today>`.

## 9. Connect & deepen (only over videos processed THIS run)
1. **Aggregate concepts**: list every Concept this run's videos touched (excluding filtered promo material), with counts.
2. **Link**: for concepts appearing in 2+ videos, or where a video explicitly related two concepts, add/update `[[wikilinks]]` between those Concept notes so the graph reflects it — don't just co-mention them in the rollup, edit the actual Concept notes.
3. **Find gaps**: concepts mentioned but never explained, claims without a stated mechanism, or contradictions between videos in this run left unresolved.
4. **Fill gaps**: for gaps central to the channel's throughline (not every passing mention), run `/research [gap topic]` (key-less by default) and use the result to extend the relevant Concept note — clearly mark that material as externally sourced, not from this channel, with its own citation.
5. Any contradiction between a video's claim and an existing vault note gets the normal `[!contradiction]` callout — never silently overwrite.

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
Cap applied this run (default 15 / `--all` / `--limit N`), total videos on channel, new this run, how many were left over the cap (if any — with the explicit re-run instruction from step 5), failed, discarded as irrelevant, concepts linked, gaps filled, rollup note path, and this channel's recommendation tier. If this is a re-run, explicitly say "N new videos since last run on <date>". If excluded at step 3, this is the whole report (no rollup/follow-list update needed for an excluded channel).

**Anti-fabrication:** never invent a video's content if extraction failed, never invent a gap-fill fact — `/research` output only, cited. See `references/ai-first-rules.md` in SKILL_ROOT.
