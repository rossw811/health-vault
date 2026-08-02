---
description: Process every unchecked video/channel URL in "YouTube Queue.md" (or a given file) - discards off-topic videos before full processing, transcript + AI-first note per relevant video, ad/sponsor filtering, then link concepts and fill gaps across the batch via /research. Channel lines get every video the channel ever published considered by default (via /youtube-channel, no recency cap). Checks off each line as it's done, never blocks on a question.
category: research
---

Use this together with the obsidian-second-brain skill's `/youtube` and `/research` machinery. Execute `/youtube-queue [file path]`:

**No open-ended scoping questions, ever.** This is the command a scheduled/unattended task runs — if it stops to ask "how do you want to scope this?" there is no one there to answer, and the run just exits having processed nothing. If the total scope looks large (many channel lines), don't ask about it — apply the defaults below, note the scale plainly in the final summary, and let the queue's own resumability handle the rest across future runs.

**There is no background for this process. Ever. Do not say there is.** When this command runs unattended (`claude -p`, a scheduled task), it is a single, one-shot, synchronous invocation — when it produces its final response and exits, the process is gone. There is no "I'll keep working on the rest in the background and report once it's done," no "running a triage sweep in the background, I'll pick this up later" — that is not true in this execution mode, and writing it produces a run that silently does nothing after printing that sentence. If there is more work to do (more channels to triage, more videos to process), **keep doing it synchronously, right now, in this same invocation**, no matter how long that takes (hours is fine) — do not defer any of it to an imagined later check-in. The only legitimate way work carries over to "later" is the queue file's own unchecked lines and each channel's own state file, both of which are picked up correctly by the *next actual invocation* of this command (the next scheduled run, or the next time a human runs it) — not by this same process pretending to continue after it has already exited.

## 1. Resolve the queue file
Default: `YouTube Queue.md` at the vault root. If it doesn't exist, create it from the template already in the vault (see `YouTube Queue.md` for the exact format) and tell the user to paste links in, then stop. Strip stray placeholder/blank lines (e.g. a leftover `EXAMPLE` entry) while you're in the file, don't ask about it.

## 2. Parse unchecked lines
Read the file. Every `- [ ] <text with a youtube.com/youtu.be URL in it>` line is a pending item. Extract the URL (strip any leading description text). Lines already `- [x]` are done - skip them. De-duplicate identical URLs appearing on multiple lines (check off all copies once processed, note the dedup in the summary). A queue line can be a single video OR a channel URL - detect which (channel handle/`/channel/` URLs vs. `/watch`, `youtu.be/`, `/shorts/`) and branch:
- Single video -> process directly (step 3). Also check `Research/YouTube/.state/_excluded-channels.json` for whether the video's channel is on the permanent exclusion list (inactive/sparse) — if so, still process this individually-requested video (an explicit ask overrides the channel-level exclusion for this one video), but note the exclusion in the summary.
- Channel URL -> hand off to the full `/youtube-channel [url]` flow for that one entry (no recency cap by default — every video the channel published gets at least a relevance check, per its own rules) — it has its own resumable state and permanent exclusion check for inactive/sparse channels — then treat the queue line as done once that command returns. If the channel was excluded, check off the line with `(excluded: <reason>)` instead of a note link.

## 3. Resolve SKILL_ROOT
```bash
find ~/.claude/plugins/cache/obsidian-second-brain -maxdepth 3 -type d -name commands | sed 's#/commands$##'
```

## 4. Per-video processing (same rules as /youtube-channel — no external LLM call)
The skill's own `/youtube` hard-requires a Gemini/XAI key for summarization. We don't use it: fetch the free transcript and free metadata yourself, then write the note directly — this guarantees verbatim quotes.

```bash
yt-dlp --skip-download --print title --print description --print channel --print upload_date --print duration_string --print view_count --print like_count "https://www.youtube.com/watch?v=<video-id>"
python scripts/fetch_transcript_auto.py "<video-id>" > "<tmp-file>" 2> "<diag-file>"
```
This single script already tries official captions first and automatically falls back to local Whisper transcription (audio download + `faster-whisper`, unaffected by the caption-endpoint block) if that fails with `IpBlocked`/`RequestBlocked`/`429` — fully automatic, no judgment call needed. Check `<diag-file>` (stderr) for `method: official captions` vs `method: local whisper` and set `transcript_source: whisper-local` in frontmatter only for the latter. Never use a third-party "free transcript" site instead — at least one has already been taken down over this exact use case. Needs `ffmpeg` on PATH and `faster-whisper` installed for the fallback — if both methods fail (exit code 1), the diagnostic file explains why.

**Relevance check** (same as `/youtube-channel` step 7.4): judge from title+description whether this is about health, fitness/athletic performance, or mental health at all; if ambiguous, skim the first ~2000 characters of the transcript. If not related in the slightest, discard it — check the line off with `(discarded: not health-related)` instead of a note link, do not write a note, and skip it from the concept-linking pass below.

If relevant: read the transcript file yourself, exclude sponsor reads/ad-reads/unrelated product pitches/course-consult pitches/membership asks from concept extraction (raw transcript stays untouched). **Signal-density flag** (same as `/youtube-channel` step 4.5): after extraction, judge the ratio of substantive/citable content to total on-topic runtime and set `signal_density: high | mixed | low` in frontmatter — `high` for dense/substantive, `mixed` for real content diluted by a lot of tangential material (typical of a long interview show where health is one thread among several), `low` for thin/repetitive despite technically being on-topic. Then save `Research/YouTube/YYYY-MM-DD - <title-slug>.md` with `type: youtube` frontmatter (`cost-usd: 0`, `signal_density`) and the same body structure as `/youtube-channel` step 8: `## For future Claude`, `## TL;DR`, `## Key Points`, `## Notable Quotes` (verbatim, copied character-for-character from the transcript - never paraphrased), `## Themes & Topics`, `## Worth Following Up On`. If a video fails (no captions, private, deleted), still check it off (so it's not retried forever) but append `(failed: <reason>)` after the URL on its line instead of a note link.

## 5. Update the queue file
For each processed line: change `- [ ]` to `- [x]`, append ` -> [[<note title>]]` on success or ` (failed: <reason>)` on failure. Append one line to the `## Run Log` section: `- YYYY-MM-DD HH:MM - N processed, M failed`. Channel-line hand-offs inherit `/youtube-channel`'s own per-video checkpointing (state file + `Logs/youtube-ingest-progress.log`) automatically — for single-video lines processed directly here, append to that same progress log too, so it's one unified feed regardless of which path a video came through.

## 6. Connect & deepen (over items processed THIS run only)
Same as `/youtube-channel` step 9: Concept notes are the primary reading layer, per-video notes are raw citation material. Actively absorb each video's substance into the relevant Concept note (rewrite/deepen it, don't just link), mark the video note as absorbed with a one-line pointer once its content genuinely lives in the Concept note, cross-link Concepts that were explicitly related, identify gaps central to what was watched, and run `/research [gap topic]` to fill the significant ones - clearly marked as externally sourced. Any contradiction with an existing note gets the normal `[!contradiction]` callout.

## 7. Summary to user
Total lines in queue, how many were channels vs. single videos vs. duplicates skipped, videos/channels actually processed (every video considered per channel, no cap), failures with reasons, concepts linked, gaps filled, and the queue file's updated state. A large channel taking a long time to fully work through is expected — checkpointing means an interrupted run just resumes, and re-running the queue continues any channel that didn't finish in one pass.

**Anti-fabrication:** never invent a video's content if extraction failed, never invent a gap-fill fact - `/research` output only, cited. See `references/ai-first-rules.md` in SKILL_ROOT.
