---
description: Synthesize a second-opinion-style interpretation of an already-ingested bloodwork panel, grounded in the People/Concepts graph's own collected expertise (e.g. Bianco on thyroid, Dayspring on lipids) rather than the vault inventing clinical judgment itself. Organizes and cross-references only - never diagnoses or recommends treatment, same boundary as /bloodwork-ingest.
category: vault
---

Execute `/bloodwork-second-opinion [panel note]`:

## 1. Require a real ingested panel first
Read the specified `Bloodwork/YYYY-MM-DD - Panel.md` note (or the most recent one if none specified). If no panel exists yet, say so and point to `/bloodwork-ingest` - this command interprets an already-structured panel, it doesn't ingest raw lab data itself.

## 2. Identify markers worth a second opinion
Pull every marker flagged `high`/`low`/`critical` in the panel's "Out of range or undetermined" section, plus every marker in its "Family-history-relevant markers" section (even if numerically normal - per this vault's existing bloodwork-ingest philosophy, a normal-but-trending value against a known family risk still matters).

## 3. Cross-reference against the People/Concepts graph's own collected expertise
For each flagged marker, check whether `People/` or `Concepts/` already has real, cited expertise directly relevant to it (e.g. a thyroid marker → `People/Antonio Bianco.md`'s deiodinase/tissue-local-thyroid-hormone work; a lipid marker → `People/Tom Dayspring.md`'s ApoB/lipoprotein research). This is the actual "second opinion" mechanism: synthesizing what already-tracked, real experts have published about this specific marker, not inventing a fresh interpretation. If no relevant expertise exists yet in the graph for a given marker, say so plainly and suggest `/web-expand` or `/institution-sweep` to find real expertise on it, rather than filling the gap with unsourced synthesis.

## 4. Write the synthesis
Append a `## Second opinion (via /bloodwork-second-opinion, <date>)` section to the panel note itself (don't create a separate note - this belongs directly alongside the data it interprets):
- Per flagged marker: what the panel shows, what the cross-referenced expert(s) have actually published about that marker/mechanism (cited, linking to the real `People/`/`Concepts/` note), and where their published position agrees or is silent on this specific case.
- If two cross-referenced experts' views on the same marker meaningfully diverge, present both - don't average them into a single synthesized "answer" that neither of them actually said.

## 5. The boundary, same as /bloodwork-ingest
This organizes and cross-references published expert positions against the panel's numbers - it does not diagnose, does not predict outcomes, and does not recommend treatment or a follow-up action beyond what's already implied by the source material's own reference ranges and the cross-referenced experts' own published statements. If the user wants an actual clinical read, that's a real physician's job, not this command's.

## 6. Summary
Which markers got a real cross-referenced second opinion, which had no relevant expertise yet in the graph (a real gap to flag, not to fill), and the panel note's updated path.

**Anti-fabrication:** every claim attributed to a person in the graph must trace to what's actually documented on their own `People/` note (which itself must already be sourced) - never invent what an expert "would probably say" about a marker they haven't actually been documented discussing.
