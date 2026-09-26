---
description: Turn candidates from scripts/journal_watch.py (Research/Web/Journal-Watch-Candidates/*.json) into real vault findings - title-triage first to control cost, then real relevance-gating and note-appending for whatever survives. The Claude-costing half of the standing journal-watch monitor scoped 2026-09-10 (see ideas.md), separated from the free discovery script the same way /process-raw-transcripts is separated from collect_raw_transcripts.py.
category: research
---

Execute `/journal-watch-process [--batch-size N]`:

> [!warning] Never dispatch per-candidate subagents.
> Same rule as `/process-raw-transcripts`, same 2026-07-26 incident it's grounded in: this entire command runs as ONE sequential agent working through its own internal loop, never parallel per-item dispatch.

## 1. Load unprocessed candidates

Read every file in `Research/Web/Journal-Watch-Candidates/*.json` not yet marked processed in `Research/Web/.state/journal-watch-processed.json` (create empty `{"processed_files": []}` if absent). Each candidate file is a flat list of `{pmid, arm, source_journal, title, journal, pubdate, doi}` objects from a single discovery run - `arm` is `"journal"` (from the known-journal watch) or `"niche"` (the broad MeSH-category discovery arm).

## 2. Title-triage pass - ONE batched judgment call, not per-item

**This is the real cost control for this pipeline - read it before skipping to step 3.** The niche arm in particular can produce hundreds to low-thousands of candidates per run (confirmed live: a single 14-day niche-arm window returned 4,749 real results). Fetching a full abstract for every one of those before judging relevance would make this command prohibitively expensive to run regularly. Instead:

- List every candidate's `title` + `journal` + `arm` in one message to yourself (a single pass over the batch, not a tool call per title) and judge, title-only, whether each looks worth reading the abstract for. This is a real judgment call, not a keyword match - use the same "is this about health, fitness/performance, or mental health at all" bar `/youtube-channel`'s relevance gate already uses, applied to the title alone.
- **Bias toward inclusion at this stage, not exclusion** - a title-only judgment is necessarily uncertain, and the cost of reading one extra abstract that turns out irrelevant is far lower than the cost of silently discarding a real niche finding because its title alone was ambiguous. Reserve title-stage rejection for titles that are unambiguously off-topic (a different species entirely with no health-relevance context, a pure agricultural/industrial-process study, a clearly unrelated disease area with no plausible cross-relevance) - "sounds boring" or "sounds niche" is not a rejection reason, the niche arm exists specifically for what sounds niche.
- Mark each candidate `title_triage: pass | reject` with a one-line reason, and record this in the per-candidate-file checkpoint (step 5) even for rejects - so a rejected title is never silently lost, it's an auditable decision.
- Candidates from the `"journal"` arm (known, already-trusted journals) can default toward a looser title bar than the `"niche"` arm, since the journal itself is already a signal of relevance/quality - reserve stricter title-scrutiny for the niche arm specifically, where volume is the real cost problem.

## 3. Abstract fetch + real relevance-gate, only for titles that passed triage

For each `title_triage: pass` candidate:
- Fetch the real abstract via PubMed E-utilities `efetch` directly (`GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=text`) - same rule as `/journal-sweep`/`/concept-audit`: never rely on OpenAlex's reconstructed abstract when a PMID exists, PubMed's own text is the source of truth.
- **Real relevance-gate** (title alone was a cheap pre-filter, this is the real check): does the abstract's actual content matter to this vault - health, fitness/performance, mental health, or a documented interest area (peptides/compounds, longevity, nutrition)? If the title looked relevant but the abstract doesn't hold up, reject here with a reason - this is expected and not a failure of step 2's triage, it's exactly why the two-stage design exists.
- **Niche arm gets an additional bias check, per the standing vault research-depth rule** ([[feedback_research_depth_primary_literature]]): prefer primary research (original studies, including preclinical/animal/mechanism-level work) over review articles at this stage for the niche arm specifically - a review found via the niche arm is lower-priority than a review found via the known-journal arm, since the known-journal arm already surfaces reviews from trusted sources reliably and the niche arm's real value is catching primary findings nobody else would have surfaced.
- If rejected: record `status: rejected-at-abstract` with a one-line reason in the checkpoint, move to the next candidate.

## 4. For each real, relevant finding - append, don't fabricate a new note

Search the vault (`Concepts/`, `Optimization/`) for the best-matching existing note for this finding's topic - same search discipline `/concept-audit` and `/obsidian-ingest` already use.

- **A good match exists**: append a dated addendum to that note. Real citation (title/authors/year/journal/PMID/DOI), **quote exact statistics from the abstract (p-values, CIs, sample sizes, effect sizes) rather than paraphrasing "found an effect"** - same rule as `/journal-sweep`. Tag it with the same Verified/Contradicted/Inconclusive framing `/concept-audit` uses relative to what the note already says. If it conflicts with existing content in that note, use a `[!contradiction]` callout grouping the opposing claims - **never silently overwrite a prior claim**, standing vault rule.
- **No good match exists**: do NOT create a new note to force a home for this finding - that's a real editorial decision this unattended-ish pipeline shouldn't make on its own. Instead, record it in the batch summary (step 6) under "No matching note found" with the citation and a one-line note on what topic area it would need. A real new Concept note is still a legitimate outcome of a genuinely novel/niche finding - it just needs a deliberate decision, made by reading the summary, not auto-generated mid-batch.
- **Anti-fabrication, absolute**: abstract-only or confirmed-open-access full text (PMC), never a paywalled full-text fetch under any circumstance - same hard boundary as `/journal-sweep`/`/book-discovery`. Never invent a study's methodology, sample size, or conclusion beyond what the actual abstract/full-text states.

## 5. Checkpoint per candidate file, not just at the end

After finishing an entire candidate file's worth of triage/gating/appending, mark it processed in `Research/Web/.state/journal-watch-processed.json` (append its filename to `processed_files`) - matches this vault's established "interrupted run loses at most one file's worth of work" checkpointing discipline, same pattern as the YouTube/concept-audit pipelines.

## 6. Batch summary

Report: candidates loaded, title-triage pass/reject counts (split journal-arm vs. niche-arm), abstract-stage pass/reject counts, real findings appended (which notes, which findings), and the full "No matching note found" list for Ross to review and decide on manually. State plainly which candidate files were fully processed and checkpointed.

**No results found is a point-in-time fact, not a permanent verdict** - if the niche arm turns up nothing genuinely new/relevant in a given run, say so plainly rather than padding the summary; an empty or near-empty run is a normal, expected outcome for a monitor like this, not something to manufacture findings to avoid.
