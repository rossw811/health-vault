---
description: Extension of "the Web" - for a tracked person, identify their institutional affiliation and sweep that institution's own relevant publication output, rather than stopping at the individual. Reuses /web-expand's dedup/tiering/anti-fabrication discipline.
category: research
---

Execute `/institution-sweep [person]`:

## 1. Resolve the anchor and their institution
Read `People/<person>.md`. Its "Published work / expertise" section (from earlier literature-sweep passes) or its main body usually already names an institutional affiliation (e.g. "UCSF," "Stanford," "Buck Institute for Research on Aging," "East Tennessee State University"). If no institution is documented on the note, do one targeted WebSearch to confirm it before proceeding — do not guess or assume from a person's general reputation.

If the person has no clear single institutional home (e.g. an independent practitioner, a media figure, a deceased pre-institutional-era coach), say so plainly and stop — this command doesn't apply to everyone in the graph, and forcing an institution onto someone who doesn't have one would be fabrication.

## 2. Scope the sweep
An institution can have an enormous publication output — this is not "read everything MIT has ever published." Scope to: work from that specific institution's relevant department/lab/center (not the whole university) that is genuinely relevant to this vault's domain (health, fitness/athletic performance, mental health). Use `/research --academic` (or a direct WebSearch/Google Scholar-style query) scoped by institution + department + this vault's topic areas, not a generic "everything from Stanford" query.

## 3. Real, citable findings only
Same anti-fabrication discipline as every other pass in this vault: every claim needs a real, checkable source (a specific paper, a lab's own publication page, a department press release) — not "Stanford is known for good neuroscience research" vague gesturing. If the institution-level sweep doesn't turn up anything beyond what the individual person's own note already covers, say so honestly rather than padding.

## 4. Output
Write a citation note: `Research/Web/YYYY-MM-DD - <Institution> Sweep (via <Person>).md` with a `## For future Claude` preamble, findings with real citations, and an explicit note on what was in scope vs. out of scope for this pass. If genuinely new people are discovered this way (e.g. a named co-author or lab colleague clearly relevant to this vault), they can be added to `People/` following the normal dedup/tiering/anti-fabrication rules from `web-expand.md` — but this command's primary output is institution-level publication findings, not new graph nodes; don't force new People notes if nothing real surfaces.

Do not touch YouTube for this — this is a pure web-research command, independent of any transcript/video pipeline.

## 5. Summary
Institution identified (or "not applicable, no clear institution"), scope of the sweep, real findings with citations, any new people discovered.

**Anti-fabrication:** never invent an institutional affiliation, a publication, or a finding's attribution. See `references/ai-first-rules.md` in the obsidian-second-brain skill root.
