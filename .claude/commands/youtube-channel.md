---
description: Ingest every video from a YouTube channel into the vault (resumable, skips ads/sponsor segments in the analysis), then link concepts across the run and fill gaps via /research. Add --limit N to cap a run, --visual for frame reading.
category: research
---

Use this together with the obsidian-second-brain skill's `/youtube` and `/research` machinery. Execute `/youtube-channel [channel url] [--limit N] [--visual]`:

## 1. Resolve inputs
Accept a channel handle URL (`https://www.youtube.com/@handle`), a `/channel/UC...` URL, or a bare `@handle`. If none given, ask "Which YouTube channel?". Compute `channel-slug` (lowercased, hyphenated handle/name) for state and rollup filenames.

## 2. Load state (resumability)
Read `Research/YouTube/.state/<channel-slug>.json` if it exists: `{channel_url, channel_name, processed_video_ids[], last_run}`. If absent, this is a first run (empty processed list).

## 3. Enumerate videos
```bash
yt-dlp --flat-playlist --print "%(id)s" "<channel-url>/videos"
```
(If the URL already points at a specific playlist/tab, use it as-is.) This is the full list, oldest-to-newest as returned. **Default is every video** — do not silently cap. Only apply `--limit N` if the user passed it explicitly, and say so in your summary if you did. Diff against `processed_video_ids` from state — the videos actually processed this run are only the new ones. Tell the user up front: total videos found, how many are new, how many already done.

## 4. Resolve SKILL_ROOT
```bash
find ~/.claude/plugins/cache/obsidian-second-brain -maxdepth 3 -type d -name commands | sed 's#/commands$##'
```

## 5. Per-video ingestion — Claude writes the note directly (no external LLM call, no key needed)
The skill's own `/youtube` command delegates summarization to a cloud call (Gemini/Grok) that hard-requires an API key. We don't use that path: transcript fetching is free and key-less, and Claude (already in this session) writes the note directly — this also guarantees verbatim quotes are pulled from the real transcript, not a second model's paraphrase.

For each new video ID, in order:

1. Fetch the free transcript:
```bash
uv run --directory "SKILL_ROOT" python -c "
import sys
sys.path.insert(0, '.')
from scripts.research.lib.youtube import get_transcript
print(get_transcript(sys.argv[1]) or '')
" "<video-id>" > "<tmp-file>"
```
2. Fetch free metadata via yt-dlp (no key needed):
```bash
yt-dlp --skip-download --print title --print channel --print upload_date --print duration_string --print view_count --print like_count "https://www.youtube.com/watch?v=<video-id>"
```
3. If the transcript is empty (no captions), log it as failed and move on — do not fabricate content.
4. Read the transcript file yourself (Read tool) and write the note. Before treating anything as a "concept," identify and exclude promotional material — sponsor reads/ad-reads, "use code X" segments, unrelated third-party product pitches, the creator's own paid-course/consult pitches, Patreon/membership asks. Leave the raw transcript untouched conceptually (don't let promo segments generate or update Concept notes, don't count them toward "recurring concepts" in step 7). If a video is ENTIRELY promotional, note it as content-free in the rollup instead of forcing an extraction.
5. Save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` with `type: youtube` frontmatter (date, time, video-id, video-url, title, channel, published, view-count, like-count, duration, tags: [research, youtube], `ai-first: true`, `cost-usd: 0`) and body:
   - `## For future Claude` preamble noting this is Claude-written directly from the free transcript (no external summarization model), quotes are verbatim.
   - `## TL;DR` (2-3 sentences)
   - `## Key Points` (5-12 specific bullets, promo material excluded)
   - `## Notable Quotes` — **verbatim only, copied character-for-character from the transcript text you read, never paraphrased or reconstructed from memory.** Quote what's actually in the transcript.
   - `## Themes & Topics`
   - `## Worth Following Up On`

If a video fails (no captions, private, deleted), log it and continue — one bad video never aborts the run. Append its ID to `processed_video_ids` regardless (so we don't retry a permanently-broken video every refresh) but mark it failed in the rollup.

## 6. Update state
Write `Research/YouTube/.state/<channel-slug>.json` with the merged `processed_video_ids`, `channel_url`, `channel_name`, and `last_run: <today>`.

## 7. Connect & deepen (only over videos processed THIS run)
1. **Aggregate concepts**: list every Concept this run's videos touched (excluding filtered promo material), with counts.
2. **Link**: for concepts appearing in 2+ videos, or where a video explicitly related two concepts, add/update `[[wikilinks]]` between those Concept notes so the graph reflects it — don't just co-mention them in the rollup, edit the actual Concept notes.
3. **Find gaps**: concepts mentioned but never explained, claims without a stated mechanism, or contradictions between videos in this run left unresolved.
4. **Fill gaps**: for gaps central to the channel's throughline (not every passing mention), run `/research [gap topic]` (key-less by default) and use the result to extend the relevant Concept note — clearly mark that material as externally sourced, not from this channel, with its own citation.
5. Any contradiction between a video's claim and an existing vault note gets the normal `[!contradiction]` callout — never silently overwrite.

## 8. Rollup note
Write/update `Synthesis/Channels/<channel-name> - Channel Rollup.md`:
- `## For future Claude` preamble per `references/ai-first-rules.md` (SKILL_ROOT).
- Frontmatter: `type: channel-rollup`, `channel`, `channel-url`, `video-count-total`, `video-count-new-this-run`, `date`, `tags`.
- `[[wikilink]]` to every per-video note created/updated this run.
- Recurring concepts this run (with counts), and which are new links vs. reinforced existing ones.
- Contradictions surfaced this run, with links.
- Gaps filled this run (link to `/research` output used) and gaps still open.
- Videos skipped/failed and why.

## 9. Summary to user
Total videos on channel, new this run, failed, concepts linked, gaps filled, rollup note path. If this is a re-run, explicitly say "N new videos since last run on <date>".

**Anti-fabrication:** never invent a video's content if extraction failed, never invent a gap-fill fact — `/research` output only, cited. See `references/ai-first-rules.md` in SKILL_ROOT.
