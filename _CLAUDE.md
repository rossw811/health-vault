# Vault operating manual

The obsidian-second-brain skill's commands read this file (`_CLAUDE.md`) by convention (`references/folder-map.md` rule 1: this file's `## Folder Map` table is authoritative). The vault's narrative rules — ingestion behavior, YouTube single-video/channel pipeline, Oura frontmatter schema, `/storm-panel` usage — live in `CLAUDE.md` in this same directory (also auto-loaded by Claude Code as standard project memory). Read both.

## Folder Map

| Note type | Folder |
|-----------|--------|
| Raw source (immutable: PDFs, articles, transcripts) | `Sources/` (`Sources/Paid/` for licensed content — gitignored) |
| Idea / concept / framework | `Concepts/` |
| Protocol / experimental program | `Protocols/` |
| Daily note | `Daily/` |
| Synthesis (panel, storm-panel, deep-synthesis, channel rollups) | `Synthesis/` (channel rollups under `Synthesis/Channels/`) |
| Research output (single YouTube video, podcast, web research) | `Research/` (`Research/YouTube/`, `Research/Web/`, etc. — skill default, unchanged) |

Vault is Obsidian-style, not wiki-style. For any note type not listed above, fall back to the Obsidian-style column in `references/folder-map.md`.
