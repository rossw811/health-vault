---
description: Structure a raw DNA/genetic test result (23andMe-style raw data or a clinical genetic panel) into a note - each marker with its called genotype and only the interpretation the source itself provides, cross-referenced against documented family-history risk factors. Same organize-and-flag-only philosophy as /bloodwork-ingest - never diagnoses or predicts outcomes beyond what the source states.
category: vault
---

Execute `/genetics-ingest [file path | "manual"]`:

## 1. Resolve the source
- A raw data file (23andMe/AncestryDNA-style raw SNP export, or a clinical lab's genetic panel report/PDF): read directly or convert with `markitdown` (PDF).
- `manual`: ask the user to paste specific marker results (rsID + genotype, or a named condition/trait result from a commercial report) - never infer a genotype from a partial description.
- **Reference interpretations come only from the source or from real cited literature fetched via `/research --academic` for that specific marker** - never invent what a genotype "means" from general knowledge. A raw SNP export (just rsID + genotype, no interpretation) requires a genuine `/research --academic` pass per marker before any interpretive claim is written; don't skip this and improvise.

## 2. Extract markers relevant to this vault's scope
This vault is about health/fitness/mental-health, not full genome curiosity browsing - focus extraction on markers with real, documented relevance to: athletic performance/injury risk (e.g. ACTN3, COL1A1/5A1), metabolic/nutrient processing (e.g. MTHFR, APOE, caffeine/CYP1A2 metabolism), and documented family-history-relevant conditions (see step 3). A raw export will contain hundreds of thousands of irrelevant SNPs - do not attempt to process all of them; scope to markers with a real, citable health/performance/mental-health relevance.

## 3. Cross-reference against documented family history
Read `Protocols/My Profile.md`'s family history section. For markers that map to a documented family risk factor (same categories `/bloodwork-ingest` already uses - autoimmune thyroid, cardiovascular, metabolic/diabetes), flag them for extra attention, same logic as bloodwork. Do not invent a family-history mapping that isn't actually documented.

## 4. Write the note
`Genetics/<date> - <source description>.md` (`type: genetics`, `tags: [genetics, dna]`, `ai-first: true`):
- `## For future Claude` preamble: source type, how many markers extracted, confidence/quality caveats (raw consumer DNA tests have real, documented accuracy limitations for individual SNP calls - state this plainly, don't present raw-export results with false clinical confidence).
- `## Markers` - one table: Marker/rsID, Genotype, What it's associated with (cited), Evidence quality (human GWAS vs. a single small study vs. commercial-report marketing claim - be honest about which).
- `## Family-history-relevant markers` - the cross-reference from step 3.
- `## Explicitly not covered` - state plainly that this is a scoped subset (per step 2), not a full-genome analysis, so nothing implies completeness it doesn't have.

## 5. The boundary
Same as `/bloodwork-ingest`: organizes and flags what's documented about each marker - never diagnoses, never predicts an individual outcome from a genotype (genotype-phenotype relationships for almost everything in this space are probabilistic and population-level, not individually deterministic - state this explicitly rather than implying otherwise), never recommends treatment/supplementation based on a genotype alone.

## 6. Summary
Markers extracted and their category, family-history cross-references found, evidence-quality distribution (how many are well-established GWAS findings vs. thin/commercial-only claims), note path.

**Anti-fabrication:** never invent a marker's association, a genotype's real-world effect size, or a family-history mapping not actually documented. Consumer genetic reports' own marketing-style claims are not automatically reliable citations - if a report claims something a real GWAS/academic search can't corroborate, flag that explicitly rather than repeating it as established fact.
