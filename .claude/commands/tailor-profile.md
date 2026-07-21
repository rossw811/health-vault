---
description: Structured multi-turn intake to build Protocols/My Profile.md - injury/medical history, training background, constraints, mental-health context. Marks the shift from broad data-gathering mode to tailored research mode. Routes concussion history to /concussion-protocol.
category: vault
---

Execute `/tailor-profile`:

## 1. Check for an existing profile
If `Protocols/My Profile.md` exists, show it and ask whether this is an update (which sections) or a full redo, rather than starting blind.

## 2. Interview — one question at a time
Same Socratic pattern as the skill's own `/obsidian-brainstorm`: ask one question, wait for the answer, let it inform the next question rather than firing a fixed questionnaire. Cover, in roughly this order:
1. **Injury/medical history** — including concussion count, approximate dates/recency, current symptom status, whether any were medically evaluated at the time. If concussion history comes up, note it for step 4 but don't try to build the return-to-training piece inline here — that's `/concussion-protocol`'s job with its own dedicated research.
2. **Training background** — current activity (the queue's channel list suggests combat sports specifically — confirm), experience level, current volume/frequency.
3. **Goals** — what "best possible version of yourself, physically and mentally" actually means in concrete terms for you, not just the abstract framing.
4. **Constraints** — time, equipment, any current physical limitations.
5. **Sleep/lifestyle factors** — relevant to HRV/readiness interpretation later.
6. **Mental-health-relevant context** — stress load, motivation patterns, anything relevant given this vault's explicit mental-health scope (per `CLAUDE.md`) — asked with the same care as the physical questions, not as an afterthought.

## 3. Write the profile
`Protocols/My Profile.md` (`type: profile`, tags `[profile, personal]`, `ai-first: true`, `updated: <date>`): organized by the sections above, written in second person ("you have..."), not clinical third person. This note is what future `/storm-panel` and `/concept-audit` runs read to check whether a protocol/claim is even applicable to you.

## 4. Route concussion history
If concussion history was documented in step 2.1, ask whether to run `/concussion-protocol` now or later — don't force it into this same session if the user wants to stop after the intake.

## 5. Mark the phase shift
Once `Protocols/My Profile.md` exists, update `CLAUDE.md`'s scope note (or add one if absent) that the vault has entered tailored-research mode — future ingestion/synthesis should actively check applicability against the profile, not just accumulate broadly.

**Anti-fabrication:** write only what was actually said in the interview — never infer or pad a section the user didn't address; mark it `TBD` and move on. See `references/ai-first-rules.md` in the obsidian-second-brain skill root.
