---
description: Fast, cheap, no-Claude-cost structural/hygiene lint of the vault - orphaned wikilinks, missing ai-first preamble/frontmatter, stale TBD markers, near-duplicate filenames, orphan notes, and aged [!contradiction] callouts. Pure Python, no LLM calls.
category: meta
---

Execute `/vault-lint`:

## 1. Run the linter
Run `scripts/vault_lint.py` with the vault's correct Python interpreter (per `CLAUDE.md`'s hardware-optimization note - use `C:\Python313-arm64\python.exe` explicitly on this machine, never bare `python`):

```
C:\Python313-arm64\python.exe scripts/vault_lint.py
```

This is pure Python + regex, no API calls, no vault modification - it only reads and reports. It should finish in a couple of seconds. It also writes the same report to `Logs/vault-lint-YYYY-MM-DD.log` automatically (the script does this itself, don't duplicate it).

## 2. What it checks (and does NOT check)
Seven purely mechanical/structural checks - never semantic/quality judgment:
1. Orphaned `[[wikilinks]]` across `Concepts/`, `Optimization/`, `Protocols/`, `Synthesis/`, `People/` that don't resolve to a real file (Obsidian's flexible bare-filename resolution, not just same-folder).
2. Missing `## For future Claude` preamble in `Concepts/`, `Optimization/`, `Protocols/`, `Synthesis/` (the ai-first content folders per `CLAUDE.md`/`ai-first-rules.md`).
3. Missing/incomplete frontmatter (`type`, one of `date`/`created`/`updated`, `tags`, `ai-first: true`) in those same four folders.
4. Literal stale `TBD` markers left in prose/tables, counted and located.
5. Near-identical filenames within the same folder (simple string-similarity, not semantic) - the known duplicate-protocol-file failure mode.
6. Notes with zero inbound AND zero outbound `[[wikilinks]]` - disconnected from the graph.
7. `[!contradiction]` callouts, flagged with their age in days when a nearby date can be found - never auto-resolved.

This is deliberately **not** `/concept-audit` (adversarial claim-verification against `/research --academic`, much more expensive) and **not** the bundled skill's `/obsidian-health` (semantic contradiction/staleness/freshness-policy scanning via Claude). Run this one often and cheaply; run those two deliberately.

## 3. Report back
Summarize the seven counts from the SUMMARY block, then call out anything that looks like a real, actionable structural problem (a genuinely broken link, a genuine duplicate pair, a note that's actually meant to be orphaned vs. one that should be linked). Point to the log file path for the full detail rather than re-pasting the whole report. Do not attempt to fix anything automatically - flagging is the whole point; a human/Claude decides what to do about each finding in a separate pass.
