---
description: Process every unchecked video URL in "YouTube Queue.md" (or a given file) - transcript + AI-first note per video, ad/sponsor filtering, then link concepts and fill gaps across the batch via /research. Checks off each line as it's done.
category: research
---

Use this together with the obsidian-second-brain skill's `/youtube` and `/research` machinery. Execute `/youtube-queue [file path]`:

## 1. Resolve the queue file
Default: `YouTube Queue.md` at the vault root. If it doesn't exist, create it from the template already in the vault (see `YouTube Queue.md` for the exact format) and tell the user to paste links in, then stop.

## 2. Parse unchecked lines
Read the file. Every `- [ ] <text with a youtube.com/youtu.be URL in it>` line is a pending item. Extract the URL (strip any leading description text). Lines already `- [x]` are done - skip them. A queue line can be a single video OR a channel URL - detect which (channel handle/`/channel/` URLs vs. `/watch`, `youtu.be/`, `/shorts/`) and branch:
- Single video -> process directly (step 3). Also check `Research/YouTube/.state/_excluded-channels.json` for whether the video's channel is on the permanent exclusion list (inactive/sparse) — if so, still process this individually-requested video (an explicit ask overrides the channel-level exclusion for this one video), but note the exclusion in the summary.
- Channel URL -> hand off to the full `/youtube-channel [url]` flow for that one entry (it has its own resumable state and its own permanent exclusion check for inactive/sparse channels), then treat the queue line as done once that command returns. If the channel was excluded, check off the line with `(excluded: <reason>)` instead of a note link.

## 3. Resolve SKILL_ROOT
```bash
find ~/.claude/plugins/cache/obsidian-second-brain -maxdepth 3 -type d -name commands | sed 's#/commands$##'
```

## 4. Per-video processing (same rules as /youtube-channel — no external LLM call)
The skill's own `/youtube` hard-requires a Gemini/XAI key for summarization. We don't use it: fetch the free transcript and free metadata yourself, then write the note directly — this guarantees verbatim quotes.

```bash
uv run --directory "SKILL_ROOT" python -c "
import sys
sys.path.insert(0, '.')
from scripts.research.lib.youtube import get_transcript
print(get_transcript(sys.argv[1]) or '')
" "<video-id>" > "<tmp-file>"
yt-dlp --skip-download --print title --print channel --print upload_date --print duration_string --print view_count --print like_count "https://www.youtube.com/watch?v=<video-id>"
```
Read the transcript file yourself, exclude sponsor reads/ad-reads/unrelated product pitches/course-consult pitches/membership asks from concept extraction (raw transcript stays untouched), then save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` with `type: youtube` frontmatter (`cost-usd: 0`) and the same body structure as `/youtube-channel` step 5: `## For future Claude`, `## TL;DR`, `## Key Points`, `## Notable Quotes` (verbatim, copied character-for-character from the transcript - never paraphrased), `## Themes & Topics`, `## Worth Following Up On`. If a video fails (no captions, private, deleted), still check it off (so it's not retried forever) but append `(failed: <reason>)` after the URL on its line instead of a note link.

## 5. Update the queue file
For each processed line: change `- [ ]` to `- [x]`, append ` -> [[<note title>]]` on success or ` (failed: <reason>)` on failure. Append one line to the `## Run Log` section: `- YYYY-MM-DD HH:MM - N processed, M failed`.

## 6. Connect & deepen (over items processed THIS run only)
Same as `/youtube-channel` step 7: aggregate concepts touched this run (excluding filtered promo material), add/update `[[wikilinks]]` between Concept notes that co-occurred or were explicitly related, identify gaps central to what was watched, and run `/research [gap topic]` to fill the significant ones - clearly marked as externally sourced. Any contradiction with an existing note gets the normal `[!contradiction]` callout.

## 7. Summary to user
Videos/channels processed, failures with reasons, concepts linked, gaps filled, and the queue file's updated state.

**Anti-fabrication:** never invent a video's content if extraction failed, never invent a gap-fill fact - `/research` output only, cited. See `references/ai-first-rules.md` in SKILL_ROOT.
