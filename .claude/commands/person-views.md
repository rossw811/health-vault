---
description: Backfill a per-person "Views & Claims" section - what a tracked person stated as fact, their stated opinions/stances, and their stated reasoning, per subject - across existing video/podcast notes that cite them. The note-taking counterpart to /web-expand (which only ever captures identity/citation-graph metadata, never content).
category: research
---

Execute `/person-views [person name | "all"]`:

## 1. Resolve scope
A specific person -> just their `People/<name>.md` note. `all` or no argument -> every note in `People/`. If scope is "all" and there are more than ~15 people, say so up front and confirm before burning a full pass, or offer to batch it (e.g. Tier 1 first, then Tier 2/3, then derived-tier hops).

## 2. Find what they've actually said
For the person in scope, find every note in `Research/YouTube/`, `Research/Podcasts/`, and `Synthesis/Channels/` that cites, quotes, or is *about* them (their own channel, or an appearance as a guest/interviewee elsewhere - `/web-expand`'s own discovery records in the `People/` note's `discovered_via_source` field point at the originating note; also grep for their name across `Research/`). Read each one fully, not just the `Notable Quotes` section - opinion/reasoning content often sits in `Key Points` or the general narrative, not always in a pulled quote.

## 3. Extract fact / opinion / reasoning, per subject
For each distinct subject the person addressed on record, extract up to three things - **never invent any of them if the source doesn't actually give it**:
- **Stated as fact** — a claim they presented as established/settled, not their own interpretation. Must be traceable to the source note (quote or close paraphrase + link).
- **Stated opinion/stance** — a claim they explicitly framed as their own view, interpretation, or prediction rather than settled fact. Same source-link discipline.
- **Stated reasoning** — *why* they hold that view, in their own words where the source actually explains it. If the source states the opinion but never gives a reason, say "reasoning not given" rather than inferring one.

A given subject may have only fact, only opinion, only opinion+reasoning, or all three - don't force all fields to be populated. Skip subjects where the person is only quoted making a passing/incidental remark, not substantively addressing the topic.

## 4. Write to the person's note
Append or update a `## Views & Claims` section on `People/<name>.md` (create it if this is the first pass for this person), one entry per subject:

```markdown
### <Subject>
- **Stated as fact**: <claim> — [[<source note>]]
- **Stated opinion**: <claim> — [[<source note>]]
- **Stated reasoning**: <their reasoning, or "not given in source">
```

If a subject already has an entry from a prior `/person-views` run and a newly-read source adds a new angle on the *same* subject (not a contradiction, just more detail), extend the existing entry rather than duplicating the `### <Subject>` heading. If a newly-read source actually **contradicts** an existing entry (e.g. they've changed their stated position over time), don't silently overwrite - add both with dates/sources and note the shift explicitly, same discipline as this vault's `[!contradiction]` convention for Concepts.

## 5. Summary to user
People processed, subjects/entries added or updated per person, and how many source notes were read. If a person in scope has no video/podcast notes citing them yet (a `People/` stub created via `/web-expand` but never actually the subject of ingested content), say so plainly rather than fabricating an empty pass as a success.

**Anti-fabrication**: every fact/opinion/reasoning entry must trace to an actual quote or clear paraphrase from a real ingested note - never infer what someone "probably thinks" from their general reputation or from other people's descriptions of them. If a source is ambiguous about whether something was stated as fact or opinion, say so in the entry rather than guessing a label. See `references/ai-first-rules.md` in the obsidian-second-brain skill root.
