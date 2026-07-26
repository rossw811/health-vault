---
description: Map how a concept/topic connects to everything already covered in the vault, then surface two distinct expansion directions - branch out (adjacent topics mentioned but never given their own treatment) and deep dive (existing thin/single-source concepts worth substantially deepening). Distinct from /concept-audit (adversarial critique) and /web-expand (people graph) - this is connection-mapping and direction-finding.
category: vault
---

Execute `/concept-connect [concept name | topic]`:

## 1. Resolve the anchor
A specific `Concepts/<name>.md` note, or a bare topic string if no note exists yet for it (in which case skip straight to step 3's branch-out analysis - there's nothing to deep-dive yet).

## 2. Map existing connections
For a real anchor concept, gather everything already touching it:
- Direct `[[wikilinks]]` to/from the concept note itself.
- Other `Concepts/` notes sharing tags or clearly overlapping subject matter (even if not explicitly linked yet - a real gap worth closing).
- `People/` notes whose `topics:` field (from the forward-expansion work) names this subject or something clearly adjacent - these are real, already-researched-but-unused connections sitting in the graph.
- Any `Research/YouTube/`, `Research/Web/`, or `Sources/Books/` note that substantively touches this topic but isn't yet absorbed into the concept (check for the absence of a `> [!info] Fully absorbed into...` pointer pointing here).

Present this as an actual map (a list grouped by connection type), not just a count - the point is to see the real shape of what's connected, not a single "N related items" number.

## 3. Branch-out candidates
From the map in step 2, identify topics that are **mentioned or referenced but never given their own Concept note** - e.g. a concept note that name-drops "cortisol" or "HRV" in passing without either linking to an existing dedicated note or acknowledging none exists yet. Also check `People/` notes with a `topics:` entry that has no corresponding `Concepts/` note at all - a tracked expert's documented specialty that hasn't been turned into vault knowledge yet. Rank by how many independent connections point at the same gap (a topic mentioned by 3 different sources is a stronger branch-out candidate than one mentioned once).

## 4. Deep-dive candidates
From the existing connected concepts (not the anchor itself, its neighbors), flag ones that are thin: single-source, `confidence: low` or `medium`, or explicitly marked with open questions/unverified claims in their own "Open questions" section. These are candidates for a real research pass (via `/web-expand`, `/institution-sweep`, `/journal-sweep`, or literature-sweep-style research) rather than staying as one-source stubs.

## 5. Output
Write (or append to, if re-run on the same anchor) `Synthesis/Connections/<anchor> - Connection Map.md`:
- `## For future Claude` preamble stating the anchor and when this map was built/last updated.
- `## Existing connections` - the map from step 2.
- `## Branch-out candidates` - ranked list from step 3, each with what's already pointing at it and why it's a real gap (not manufactured).
- `## Deep-dive candidates` - ranked list from step 4, each with why it's thin and what a real deepening pass would need (a specific missing angle, not just "more research").
- Do NOT actually execute the branch-out or deep-dive work in this same pass - this command's job is the map and the menu, not the research itself. That's a deliberate separation: mapping should be cheap and frequent, research passes are the expensive/deliberate next step chosen from this menu.

## 6. Summary
Anchor, connection count by type, top 3 branch-out candidates, top 3 deep-dive candidates, map note path.

**Anti-fabrication:** every connection listed must be real (an actual existing wikilink, tag match, or `topics:` field value) - never invent a plausible-sounding connection that isn't actually present in the vault's own notes.
