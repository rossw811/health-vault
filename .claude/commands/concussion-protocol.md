---
description: Research and cite the published graduated return-to-play concussion protocols (Berlin/Amsterdam Consensus Statement, CDC HEADS UP), then map the user's documented history against them into a concrete current-stage position. Not a substitute for physician clearance - flags exactly where that matters, not as a blanket disclaimer.
category: vault
---

Execute `/concussion-protocol`:

## 1. Require documented history first
Read `Protocols/My Profile.md`. If it doesn't exist or has no concussion history documented, say so and suggest running `/tailor-profile` first — do not proceed on assumed or inferred history.

## 2. Research the actual published protocol — don't invent one
```
/research "Berlin Consensus Statement concussion sport graduated return to play protocol" --academic
/research "CDC HEADS UP concussion return to play guidelines" --academic
```
Pull the real, current graduated stage structure (as of whichever consensus statement is most recent — Amsterdam 2022 superseded Berlin 2016, cite whichever the research actually surfaces and note the supersession if both appear). The standard structure is stages from symptom-limited activity through light aerobic exercise, sport-specific exercise, non-contact training drills, full-contact practice, to return to competition — but pull the ACTUAL current stage names/criteria from the research output, don't reconstruct from memory only.

## 3. Write the reference note
`Protocols/Concussion Return-to-Training.md` (`type: protocol`, tags `[protocol, concussion, cited]`, `sources` listing every research output used): the full published stage structure, each stage's actual clinical criteria for advancing to the next (symptom-free duration, exertion tolerance, etc.), cited to the specific consensus statement/guideline.

## 4. Map current position — this is the actual "prescription"
Cross-reference `Protocols/My Profile.md`'s documented history (count, recency, current symptom status, activity tolerance) against the stage structure from step 3. State plainly and specifically: "based on the published protocol and what's documented, you're positioned at Stage X; advancing to Stage X+1 requires [specific published criterion]." This must be a concrete position, not a vague "consult your doctor" deflection — that was the explicit ask.

## 5. The one place caution attaches — and exactly why
History of 4-5 concussions is NOT the general single-incident population the standard protocol was validated against — repeat concussion history is associated with cumulative risk that a generic protocol doesn't fully price in. So: at the SPECIFIC stage-advancement decision points where symptoms could plausibly recur (this is a clinical fact about the protocol, not a blanket legal disclaimer), state explicitly that a physician/neurologist should confirm before advancing — attached to those specific transitions, not smeared across the whole note as boilerplate. Everywhere else in the note, be as concrete and directive as the published protocol itself is.

## 6. Never do
- Invent a novel protocol or modify the published stage criteria.
- Declare the general-population protocol sufficient on its own for a documented multi-concussion history without the flag in step 5.
- Present this note as equivalent to an actual medical clearance — it's a cited reference + your documented position within it, which is a different (and more useful, and honestly presented) thing.

## 7. Summary
Which consensus statement/guideline was used, current stage position and why, the specific next-stage criterion, and exactly which transition(s) carry the physician-confirmation flag.

**Anti-fabrication:** every stage criterion must trace to the actual `/research` output, not general knowledge dressed up as a citation. If the research comes back thin, say so rather than filling gaps with plausible-sounding clinical detail.
