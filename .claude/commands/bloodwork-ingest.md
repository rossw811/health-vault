---
description: Ingest a lab bloodwork panel (PDF/CSV/manual entry) into a structured note - every marker with its value, unit, and reference range EXACTLY as given in the source (never invented), flagged in/out of range, cross-referenced against documented family-history risk factors from Protocols/My Profile.md.
category: vault
---

Execute `/bloodwork-ingest [file path | "manual"]`:

## 1. Resolve the source
- A file path (PDF/CSV/image of a lab report): convert with `markitdown` (PDFs) or read directly (CSV). If it's an image, read it directly (OCR via vision).
- `manual`: ask the user to paste or type the values; if a marker's reference range wasn't given, ask for it or mark `TBD` — never fill in a "typical" range yourself. Reference ranges are lab- and method-specific; substituting a generic one is a real error, not a convenience.
- If neither the source nor the user gives a reference range for a marker, record `reference_range: TBD` and `flag: cannot-determine` — do not guess whether it's in range.

## 2. Extract every marker
For each marker present in the source: name (use the source's own terminology, don't normalize to a different name that could obscure which exact assay was run — e.g. "Total T" vs "Free T" are different tests), value, unit, reference range (verbatim from source), and computed flag (`normal` / `high` / `low` / `critical` if the source itself marks something critical / `cannot-determine` if no range given).

## 3. Cross-reference against documented family history
Read `Protocols/My Profile.md`'s family history section if it exists. For markers that map to a documented family risk factor, flag them for extra attention even if numerically "normal" (a normal-but-trending value matters more against a known risk):
- Maternal Hashimoto's/celiac -> TSH, Free T3/T4, rT3, TPO antibodies, Thyroglobulin antibodies, tTG-IgA, Total IgA
- Finnish/maternal cardiovascular risk -> NMR lipid panel, ApoB, Lp(a), hs-CRP, NT-proBNP, blood pressure
- Paternal probable prediabetes/insulin resistance -> Fasting glucose, fasting insulin, HbA1c
- Paternal grandfather cholesterol/BP -> lipid panel, blood pressure

Do not invent a family-history mapping that isn't actually documented in `Protocols/My Profile.md` — if that note doesn't exist or doesn't cover a given marker's family risk, say so rather than assuming.

## 4. Write the note
`Bloodwork/YYYY-MM-DD - Panel.md` (`type: bloodwork`, `date`, `lab` if known, `tags: [bloodwork, labs]`, `ai-first: true`):
- `## For future Claude` preamble: draw date, lab (if known), how many markers, how many flagged out-of-range or cannot-determine.
- `## Results` — one table per panel category (Thyroid/Hormonal/Metabolic/Inflammatory/Hepatic/Renal/Nutrients/Immune-Gut/Cardiac/Other, whichever actually appear) with columns Marker / Value / Unit / Reference Range / Flag.
- `## Family-history-relevant markers` — the cross-reference from step 3, with the specific documented risk factor named next to each marker.
- `## Out of range or undetermined` — every `high`/`low`/`critical`/`cannot-determine` marker pulled into one place so nothing gets buried in a long table.

## 5. Do not give medical interpretation beyond organizing the data
This command structures and flags what the lab report itself says. It does not diagnose, does not recommend treatment, and does not editorialize on what an out-of-range marker "means" beyond what the lab's own reference range already indicates. If the user wants that discussion, it happens in conversation, informed by this note, not written into it as if it were established fact.

## 6. Summary
Markers ingested, how many flagged high/low/critical/cannot-determine, family-history cross-references found, note path. If this is a second or later panel, mention `/bloodwork-trend` is now available to compare against the prior draw.

**Anti-fabrication:** never invent a reference range, a marker's clinical significance, or a family-history mapping not actually documented. `TBD`/`cannot-determine` is always the correct answer over a plausible-sounding guess.
