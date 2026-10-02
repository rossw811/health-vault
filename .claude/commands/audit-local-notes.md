---
description: Spot-audit notes written by the local Part 2b pipeline (scripts/finish_drafts_local.py) against their raw transcripts - every flagged note plus a 1-in-10 random sample, queued in Research/.local-2b-audit-queue.json. Claude-costing; run deliberately, not on a timer.
category: research
---

Execute `/audit-local-notes [--limit N]` (default 10):

> [!info] Why this exists. Local notes (`finished_by: local-...`, `trust_tier: local-verified`) pass programmatic gates (verbatim evidence, two-model verification, contradiction check, exact quotes) but no Claude review. The 2026-10-01 gate found the main residual risk is **meaning errors that fool the model consistently** (e.g. a double negative read backwards), plus thinner coverage than Claude on conversational content. This audit keeps local quality *measured* instead of assumed. Same single-sequential-agent rule as `/finish-draft-notes`: no per-file parallel dispatch.

## 1. Pick notes
Read `Research/.local-2b-audit-queue.json`. Take entries with `audited: false`, `reason: flagged` first, then `random-sample`, up to `--limit`.

## 2. Per note, sequentially
- Read the note, then the raw transcript (`Research/*/Raw/*[<id>]_full.txt`). Read the parts each Key Point and flagged item rests on closely, not the whole file blindly.
- **Accuracy**: check every Key Point's direction and numbers against the transcript, especially negations, conditionals and dose units. Any wrong claim: fix it in place and log it (step 3).
- **Garble flags**: resolve each `[transcript term may be garbled - verify]` marker. If the intended term is clear from context, write it as `<transcript term> (likely <intended term>)`; if not, leave the flag. Never silently "correct" a verbatim quote.
- **Coverage**: note any important point the local note missed, prioritizing mental-health content, safety/risk statements, and study design/results. Add the missing points (verbatim-quote rules unchanged).
- **Risk flags** (`(model risk flag, unverified)`): keep, rewrite, or remove each one based on what the transcript actually supports.
- Leave `trust_tier: local-verified` and add `audited: <date>` plus `audit_result: clean | corrected | rewritten` to the frontmatter.

## 3. Record
- Set the queue entry to `audited: true` with `result` and a one-line `finding`.
- Append a summary line per run to `Logs/local-2b-audit.log`: notes audited, clean/corrected/rewritten counts, error types found.
- **If corrections cluster** (e.g. 2+ meaning inversions in one run, or repeated misses of one content type), say so plainly in the summary. That means the routing or the gates need changing in `scripts/finish_drafts_local.py`, not just this batch fixing.

**Anti-fabrication**: identical bar to `/finish-draft-notes`. Only what the transcript says, verbatim quotes only from text actually read.
