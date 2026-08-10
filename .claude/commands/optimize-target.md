---
description: Build or refresh a per-target optimization plan in Optimization/ - one note per marker (insulin sensitivity, ApoB, HRV) or per body system (brain, liver, fascia), driving a measured target toward an optimum rather than just flagging in/out of range. Populates from real Bloodwork/Daily data only; a target with no measurement says so rather than inventing a baseline.
category: protocol
---

Execute `/optimize-target [marker | system | "wave-1" | "all"] [--refresh]`:

## 0. Read first
- `Optimization/_Index.md` — the master target list, status legend, and build order. **If the requested target isn't in the index, add it there first**, then build the note.
- `Optimization/Insulin Sensitivity.md` — the canonical exemplar. Match its section order and depth.
- `Protocols/My Profile.md` — profile, family history, symptoms, supplement stack.
- `CLAUDE.md` — anti-fabrication, mental-health-as-first-class, dosing rules.

## 1. Gather real current state — never invent one
Pull actual values from, in order: `Bloodwork/` panels, `Daily/` frontmatter (Oura), documented figures in `Protocols/My Profile.md`.

**A target with no measurement gets the literal words "no measurement yet" and a `> [!warning]` that the plan can't be prioritized until it has one.** Never fill a plausible-looking placeholder. Family-history risk is context, not a measurement. Reference ranges come from the source panel or a cited study — never a generic "optimal range" supplied from memory (same rule as `/bloodwork-ingest`).

Set `data-status:` frontmatter to one of `data-now` / `needs-records` / `needs-new-test` / `no-test-needed`, matching the index.

## 2. Set the target honestly
If there's no baseline, **do not state a numeric target** — state what the target *will* be expressed in and why that marker was chosen over adjacent ones (e.g. fasting insulin over fasting glucose, because it moves years earlier). Defer the number.

## 3. Levers, tiered by evidence strength
Three tiers — Tier 1 (strongest evidence, largest effect), Tier 2 (real but smaller/more variable), Tier 3 (plausible, weak or indirect) — plus an explicit **"Explicitly not recommended"** section. That last section is not optional: naming what you're ruling out and why is what keeps these plans from reading as a supplement catalogue.

**The DRY rule:** a lever links its mechanism to a `Concepts/` note. It does not restate the mechanism. If no Concept note exists, create it (per `/obsidian-ingest` conventions) and link it. The same lever appearing in eight plans must resolve to one Concept, not eight paragraphs that drift apart.

**Dosing is in scope** (2026-08-02 rule change, `Protocols/My Profile.md`) — give literature-supported doses with a one-line evidence basis. Still flag physician involvement where it's genuinely warranted (interaction profiles, unresolved safety signals, anything touching the concussion history), not as blanket boilerplate.

## 4. Measurement plan
A table: what / how / cadence / status. **Separate what is already measured automatically from what is blocked** — the automatic ones are actionable today and should be called out as such. Where a target's levers are Oura-measurable but the target itself is not, say so explicitly and warn against reading an `/oura-analyze` correlation as a result for this target. That circularity trap is called out in `CLAUDE.md` and it's easy to fall into here.

## 5. Interactions with other targets
Link sibling `Optimization/` notes — where they share levers, where they genuinely conflict, and where a shared upstream driver is *plausible but untested*. Mark speculation as speculation; never promote it to a finding.

## 6. Open questions
Real unknowns, competing explanations for the same symptom, and what test would actually distinguish them. A symptom consistent with the target is not evidence for it — list the alternatives that fit equally well.

## 7. Summary
Targets built/refreshed, `data-status` split, new `Concepts/` notes created, dangling data dependencies, and what to order/measure next.

**Anti-fabrication:** identical to every other command here. No invented values, no invented reference ranges, no invented mechanisms, no dressing thin evidence as protocol — where a target's evidence base is genuinely weak (fascia is the clearest case), the plan says so plainly instead of manufacturing confidence.
