---
description: Local semantic search over the vault (scripts/vault_search.py) — a discovery layer that surfaces notes keyword grep/glob misses (synonyms, paraphrase, conceptual matches), never an answer layer. Every result still requires a full Read before being used in synthesis.
category: research
---

Execute `/vault-search <query>`:

> [!warning] **This is a discovery tool, not an answer tool.** It returns ranked (note path, section heading, snippet) results from a local embedding index — never full chunk text meant to be quoted or synthesized from directly. Any note this surfaces still needs a real `Read` before it's used in an answer, a `/storm-panel`, a `/concept-audit`, or anywhere else — same anti-fabrication discipline as every other command in this vault. The value here is catching a relevant note that keyword search would miss (different wording, a paraphrase, a conceptually-related-but-lexically-different note), not skipping the read.

## 1. Check the index is current
Run `python scripts/vault_search.py --reindex --changed` first — cheap (only re-embeds notes whose content hash changed since the last index build), keeps results honest. Skip this only if you just ran it moments ago in the same session.

## 2. Search
Run `python scripts/vault_search.py "<query>" -k 10` (or higher `-k` for a broader sweep). Read the ranked list — lower distance = more semantically similar.

## 3. Follow up on real hits
For every result that looks genuinely relevant (use judgment — semantic similarity isn't the same as relevance, and the snippet is a preview, not the full picture), `Read` the actual note before using anything from it. Discard results that turn out to be superficial keyword-adjacent noise once you've actually looked.

## 4. When to reach for this vs. Grep/Glob
- Grep/Glob first for anything with a known exact term, filename, or tag — they're faster and don't need the index to be current.
- Reach for `/vault-search` when you suspect a relevant note exists under different wording than what you're searching for, when starting a broad research/synthesis pass (`/storm-panel`, `/concept-audit`, gap analysis) where missing a related note is the actual risk, or when Grep/Glob came up empty and you're not confident that means nothing exists.

## Maintenance
The index lives at `.vault_search_index.sqlite3` (vault root, gitignored — add it if not already). It excludes `Sources/`, `Raw/`, `.drafts/`, `.lite/` on purpose (raw/unprocessed material would just dilute results with duplicate, unsynthesized content). Full rebuild: `python scripts/vault_search.py --reindex` (no `--changed`) — needed if the chunking logic itself changes, not for routine content updates.
