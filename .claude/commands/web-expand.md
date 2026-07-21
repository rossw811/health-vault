---
description: Grow "the Web" - process a Tier-1/2/3 anchor's content (or research their own influences), discover every real named person they reference, create tiered People/ notes with a decimal hop notation, and recurse up to 2 hops by default. Reuses /youtube-channel's ingestion so concepts get linked too.
category: research
---

Execute `/web-expand [person name | channel url] [--depth N] [--influenced-by]`:

## 1. Resolve the anchor
If given a `People/<name>.md` note, use its `tier`/`derived_tier` and `channel_url`. If given a channel URL not yet tracked, ask what tier (1/2/3) to assign before creating its `People/` note — tier assignment is a judgment call, never assign it silently. If no argument, ask which person/channel.

## 2. Choose direction
- Default (forward): find who THIS person references/interviews/cites in their own content.
- `--influenced-by`: research who influenced/taught/mentored this person (biographical interviews, tributes, their own writings' citations) via `/research` rather than their own channel — for anchors with no active channel (e.g. deceased sources) this is the only applicable direction. This is the influence-genealogy use case.

## 3. Depth bookkeeping
Default max depth is **2 hops** from the anchor's own tier (hard cap — `--depth N` can raise or lower it for one run, but never skip the cap check). Track a `visited` set of canonical person identities (name + channel/handle) for THIS run only, to avoid re-walking someone already processed in the same invocation (cycle safety).

## 4. Forward mode: process the anchor's content
Reuse `/youtube-channel`'s full pipeline (state file, resumability, relevance gate, ad/sponsor filtering, transcript-grounded note-writing, concept linking) exactly as documented in `.claude/commands/youtube-channel.md` — every video gets ingested the same way, so `Research/YouTube/` notes and `Concepts/` links happen exactly as they would from a direct `/youtube-channel` run.

**Additional extraction pass per video** (on top of, not instead of, the concept extraction): identify every **real, identifiable named individual** the video treats as a source — an interviewee, a researcher whose work is credited by name, someone explicitly cited as "as Dr. X found/said." Do NOT count passing mentions ("some studies show"), generic references ("researchers at Stanford"), or unnamed people. This bar is intentionally strict — the Web should only grow from real, attributable connections.

For each named individual found:
1. **Dedup by identity first** — search ALL existing `People/` notes by name and any known channel/handle before creating anything new. A person may already exist from a different discovery path.
   - If new: create `People/<name>.md` with `derived_tier: "<anchor's own tier or base of derived_tier>.<hop>"` (e.g. anchor is tier 1 → hop-1 discovery gets `"1.1"`; if that hop-1 person is later expanded, their own discoveries get `"1.2"`), `discovered_via: "[[People/<anchor>]]"`, `discovered_via_source: "[[Research/YouTube/<the specific note>]]"`.
   - If it already exists: compare paths. Keep the **better** one — lower base tier number wins first, then lower hop count. If this run's path is worse, don't touch the existing tier; just add this occurrence as an additional `discovered_via_source` (a note can have more than one discovery source over time — track them as a list once there's more than one).
2. Never create a duplicate note for the same person under a slightly different name spelling — if uncertain whether two names are the same person, say so and ask rather than guessing.

## 5. Influence-genealogy mode (`--influenced-by`)
Instead of processing a channel, run `/research "<person>'s own influences teachers mentors early career"` (and similar targeted queries) via the skill's key-less research. Extract real named people identified as having taught/influenced/mentored the anchor. Same dedup/tiering rules as step 4, except `discovered_via_source` points to the `/research` output note instead of a video, and the relationship is recorded as `influenced-by` rather than the default outward-reference direction (add an `influenced-by: ["[[People/...]]"]` frontmatter field alongside `discovered_via` — they can differ: someone can be *discovered via* one path but the *actual relationship* is mentorship rather than citation).

## 6. Recurse (bounded)
For each hop-1 person newly discovered (or already known but now in scope), if depth budget allows, run this same process on them (forward mode, using their own channel if they have one) to find hop-2 people. Stop at the depth cap — do not go further even if more connections are visible. Skip anyone already in `visited` for this run.

## 7. Summary to user
People discovered this run (new vs. already-known-but-reinforced), their tiers/hops, depth reached, any name-ambiguity cases you flagged instead of guessing, and a reminder that grouping/visualizing this data (by tier, by confidence, by category) happens in Extended Graph or a Base view — no data changes needed to try a different grouping.

**Anti-fabrication:** never invent a person's identity, credentials, or relationship to the anchor. If a video references someone by first name only or ambiguously, do not create a stub — note it as an unresolved reference instead. See `references/ai-first-rules.md` in the obsidian-second-brain skill root for the underlying anti-fabrication rules this inherits.
