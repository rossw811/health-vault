---
description: Adversarially critique Concept/Protocol notes to find weak claims, single-source assumptions, missing mechanisms, and unresolved contradictions - a "bulletproofing" pass. Verifies critical claims via /research and gauges online sentiment via last30days. Different from /obsidian-challenge (which red-teams a proposed idea against your own past decisions) - this systematically critiques the concepts themselves.
category: research
---

Execute `/concept-audit [concept name | "all"] [--skip-sentiment] [--skip-verify]`:

## 1. Resolve scope
A specific note name -> just that one (plus anything it directly links to, for context). `all` or no argument -> every note in `Concepts/` and `Protocols/`. If scope is "all" and there are more than ~15 notes, say so up front and confirm before burning a full pass, or offer to batch it.

## 2. Per-concept adversarial critique
For each note in scope, read it fully plus everything it wikilinks to. Then critique it from three distinct, genuinely independent lenses - don't let them converge into one generic pass:

- **The mechanist**: for every causal or prescriptive claim ("do X to get Y"), demand the stated mechanism. Flag any claim with no mechanism given, a mechanism that doesn't actually support the conclusion, or a mechanism that's plausible but unverified.
- **The evidence auditor**: for every claim, check how many independent sources back it in this vault. Flag anything presented as settled fact that traces to a single source (one video, one guide), anachronistic mixing (an old finding a newer source in the vault has already superseded but this note wasn't updated), or subject-matter mismatch (e.g. animal-study or bro-science conflated with human clinical evidence, no caveat given).
- **The contrarian**: actively construct the strongest reasonable counter-position a well-informed skeptic would raise. Search the rest of the vault (other Concepts/Protocols/Synthesis notes, including prior `/storm-panel` outputs) for material that already contradicts this note but hasn't been cross-linked as a `[!contradiction]`.

## 3. Synthesize per-concept findings
For each note, produce:
- **Weak claims** — quote the exact claim, which lens flagged it, and why.
- **Oversights** — things a thorough treatment of this topic would address but this note doesn't touch at all.
- **Unresolved contradictions** — cross-references within the vault that conflict with this note but aren't yet flagged.
- **Severity** — rank each finding: critical (undermines the note's core claim), moderate (weakens a supporting point), minor (missing nuance/caveat).

Do not soften findings to be agreeable. If a note holds up well under all three lenses, say so plainly and briefly - don't manufacture weaknesses to pad the report.

## 4. Verify critical claims against actual studies (skip with --skip-verify)
For every CRITICAL-severity finding from step 2 (and any claim the evidence auditor flagged as single-source), don't stop at "this is unverified" - go look:

```
/research "<the specific claim>" --academic
```
This restricts to scholarly sources (arXiv, Semantic Scholar, OpenAlex, CrossRef) - we want actual studies, not blog summaries of studies. For each study that comes back relevant:
- **What it actually found** - the real result, not the abstract's spin.
- **Sample** - size, population (human/animal, age range, trained/untrained, etc.) - flag any mismatch with how the vault's claim generalizes it.
- **Methodology shortcomings** - underpowered sample, no control group, self-reported outcomes, short duration, industry funding, non-replication if known.
- **Verdict**: does this study support, contradict, or only partially/conditionally support the vault's claim? Be specific about the condition.

Update the finding with a **Verified / Contradicted / Inconclusive** tag and cite the actual study (title, year, and what specifically it found) - not just "research suggests." If `/research --academic` turns up nothing relevant, say that plainly rather than treating silence as support.

## 5. Online sentiment (skip with --skip-sentiment)
For the concept as a whole (not per-claim), use the `last30days` skill to check what people are actually saying about it right now - Reddit, HN, X, YouTube, etc. Look specifically for: is this concept broadly accepted, actively debated, or has it been recently debunked/superseded somewhere the vault hasn't caught up to yet? Summarize as a short **Online Sentiment** section: dominant view, any notable dissent, recency of the discourse. This is directional color, not a source of truth - don't let it override the study-level verification in step 3.

## 6. Write output
- Full report: `Synthesis/Critiques/<concept-slug> - critique - YYYY-MM-DD.md` (`type: critique`, tags `[critique, thinking]`, `sources` listing every note read plus every study/source pulled in step 4, per `references/ai-first-rules.md` in the obsidian-second-brain skill root). Include the Online Sentiment section from step 5.
- On the actual Concept/Protocol note being critiqued: prepend a `> [!warning] Open critique (YYYY-MM-DD)` callout linking to the full report, listing only the CRITICAL-severity findings inline with their Verified/Contradicted/Inconclusive tag. Do not silently resolve or rewrite the note's claims here - this command surfaces weaknesses, it doesn't fix them. Fixing is a separate follow-up (e.g. `/research` on a specific gap, or a user decision).

## 7. Summary to user
Notes audited, count of findings by severity, how many were verified/contradicted/inconclusive against actual studies, and which notes came through clean.

**Anti-fabrication:** every flagged weakness must cite the exact claim and its location - never invent a weakness to seem thorough. If a lens finds nothing to flag, say so rather than reaching. See `references/ai-first-rules.md` in the obsidian-second-brain skill root.
