---
description: Produce a safe-to-share copy of one or more notes by stripping [!hidden] callout blocks (the in-note privacy convention in CLAUDE.md), and heuristically flag content that looks personal but wasn't marked. Pure Python, no LLM calls, no vault modification.
category: meta
---

Execute `/export-safe-copy [note path | --folder <folder>]`:

## 1. Run the exporter
Run `scripts/export_safe_copy.py` with the vault's correct Python interpreter (per `CLAUDE.md`'s hardware-optimization note — use `C:\Python313-arm64\python.exe` explicitly on this machine, never bare `python`):

```
C:\Python313-arm64\python.exe scripts/export_safe_copy.py "Concepts/Some Note.md"
C:\Python313-arm64\python.exe scripts/export_safe_copy.py --folder Optimization
```

If the user gave a note name or folder in `$ARGUMENTS`, pass it straight through. If they gave neither, ask which note(s) — don't guess at scope for something privacy-related.

This is pure Python + regex, no API calls. It never edits the source note — it writes a sanitized copy under `Exports/` (gitignored, local-only, mirrors the source's relative path) and never overwrites anything already there without the same filename colliding on purpose.

## 2. What it does (and does not do)
1. Strips every `[!hidden]` callout block (any fold state) from the note, replacing each with a single visible "[private content removed]" marker line — so the reader can tell something was removed, not just get a smaller note.
2. Heuristically **warns** (never auto-redacts) about content left over that still looks personal: the vault owner's name, links into `Bloodwork/`, `Protocols/My Profile`, `Daily/`, or `People/`, and dose/self-report-shaped text. False negatives are expected — this is a net, not a guarantee.
3. If a note has **zero** `[!hidden]` blocks, the tool says so explicitly as "not evidence this is safe," not a silent pass-through.

It does **not** publish, send, or upload anything anywhere, and it does not touch git. It produces a local file for a human to actually read before deciding to share it.

## 3. Report back
Show the per-note summary (blocks removed, any warnings) exactly as the script prints it — don't re-summarize away the warnings. If warnings exist, say plainly that the export is not confirmed safe to share and point at what to check. Never tell the user something is "safe to share" — only the script's factual findings plus a suggestion to read the actual output file.
