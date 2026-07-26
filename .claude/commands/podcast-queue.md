---
description: Discover a creator's podcast RSS feed and add it to Podcast Queue.md - the search/discovery half of podcast ingestion (scripts/podcast_collector.py does the mechanical download+transcribe half separately, no Claude/API cost).
category: research
---

Execute `/podcast-queue [person or channel name]`:

## 1. Resolve the feed
Try, in order, stopping at the first real match:
1. **Apple's public podcast search API** (no key needed): `https://itunes.apple.com/search?term=<name>&media=podcast&limit=5`. Its `feedUrl` field is the real RSS feed URL directly - no scraping needed. Check the top few results' `artistName`/`collectionName` actually match the person/channel before accepting one; a common name can return an unrelated show, and a multi-word name can return several distinct shows (e.g. searching a well-known host can surface both their real feed and unrelated fan-made spinoffs) - verify against the actual channel/person, don't just take the first hit.
2. If nothing matches, one targeted WebSearch (`"<name>" podcast RSS feed`) - many shows publish their own feed URL on their site or Spotify-for-Podcasters page. Verify it's real (fetch it, confirm it parses as RSS with real episodes) before adding it.
3. If no real podcast exists for this person/channel, say so plainly and stop - don't force a queue entry for a creator who only publishes on YouTube.

**"Spotify-exclusive" is not a reliable reason to skip a search.** Some shows have genuinely closed, app-only distribution with no RSS at all, but plenty that are commonly assumed exclusive (or moved to Spotify at some point) still have a real, current public feed underneath - Apple's directory indexes the same feed most shows use regardless of where a listener happens to play it. Don't assume "this creator is on Spotify" means no feed exists; check.

## 1.5. Verify the feed is actually live, not a stale/defunct artifact
Before queuing, parse the candidate feed and check its most recent episode's `pub_date` - if the newest episode is many months/years old relative to the channel's known YouTube activity, this is either a dead show or a stale mirror, not the real active feed. Don't queue a feed you haven't confirmed has genuinely recent episodes.

## 2. Add to the queue
Append `- [ ] <feed URL>` to the `## Feeds` section of `Podcast Queue.md` (create the file from the template if missing - see the file for the exact header). Dedupe against existing lines first (same feed already queued = skip, note why).

## 3. Do NOT process episodes in this command
This command only discovers and queues the feed - the actual download+transcribe work happens via `python scripts/podcast_collector.py`, separately (mirrors the `/youtube-queue` vs. `scripts/collect_raw_transcripts.py` split: discovery/search needs Claude+WebSearch, mechanical fetch/transcribe work doesn't and shouldn't cost Claude session budget). If the user wants episodes processed right now, tell them to run the script directly or that the scheduled collector will pick it up.

## 4. Summary
Feed found (or "no podcast exists for this creator"), how it was verified, whether it was newly added or already queued.

**Anti-fabrication:** never invent or guess a feed URL - verify by actually fetching and parsing it as RSS before adding to the queue.
