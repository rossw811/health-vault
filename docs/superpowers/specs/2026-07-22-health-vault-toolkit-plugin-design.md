# Health Vault Toolkit — Plugin Design

**Status**: approved, not yet implemented
**Date**: 2026-07-22

## Goal

Package this vault's custom Claude Code tooling (`.claude/commands/`, `scripts/`, `.mcp.json` config) into a distributable, installable plugin — `health-vault-toolkit` — so the same workflow (YouTube ingestion, biometric analysis, "the Web" people-graph, bloodwork ingestion, concussion protocol, book discovery, personal tailoring, synthesis/critique) is reproducible both for future-you (a new vault, or a clean reinstall of this one) and for other people with their own Obsidian vaults.

## Audience

Both: personal reuse across future vaults, **and** genuinely installable by a stranger who has never seen this vault. This rules out a light "mostly ship as-is" pass — real genericization is required (see below), and the README/docs need to be written for someone with zero context, not as a personal dev log.

## Repo strategy

**New, separate repo**: `health-vault-toolkit` (name provisional — confirm before creating). Structured the same way as the `obsidian-second-brain` plugin it depends on. This existing repo (`rossw811/health-vault`) is unaffected in its own history — it keeps `CLAUDE.md`, `_CLAUDE.md`, `development.md`, `buglog.md`, and all personal vault content exactly as they are. Once the toolkit plugin exists, this repo's role changes from "duplicates the commands locally" to "installs `health-vault-toolkit` as a plugin + layers this vault's own `CLAUDE.md`/`_CLAUDE.md` customization on top" — the same relationship this vault already has with `obsidian-second-brain` itself.

## Plugin structure

```
health-vault-toolkit/
  .claude-plugin/
    plugin.json               # name, description, version, commands path, mcpServers
  commands/                   # all 13 commands, genericized (see below)
    youtube-channel.md
    youtube-queue.md
    web-expand.md
    book-discovery.md
    tailor-profile.md
    concussion-protocol.md
    <device>-sync.md          # e.g. oura-sync.md — one per supported wearable adapter
    biometric-analyze.md      # renamed from oura-analyze.md — device-agnostic
    bloodwork-ingest.md
    bloodwork-trend.md
    storm-panel.md
    concept-audit.md
    vault-update.md
  scripts/
    sync/
      oura_sync.py            # Oura-specific adapter (or .mjs, matching current run-oura-mcp.mjs approach)
    biometric_analyze.py       # renamed from oura_analyze.py — reads canonical + device-extra fields generically
    generate_dashboard.py      # device-agnostic, same generalization
  templates/
    CLAUDE.md.template         # starter narrative rules + folder-map convention, meant to be copied and customized per vault
  README.md                    # written for a stranger installing this cold
  requirements.txt
```

**Dependency**: requires `obsidian-second-brain` installed first — several commands rely on its `SKILL_ROOT` resolution, `/research`, and AI-first note conventions (verbatim quotes, anti-fabrication rules). State this plainly as a prerequisite in the README rather than duplicating that machinery inside this plugin.

## Genericization — command by command

Most commands already generalize cleanly because they read from the user's own `Protocols/My Profile.md` as data, not hardcoded values (`tailor-profile`, `concussion-protocol`, `storm-panel`, `concept-audit`, `web-expand`, `book-discovery`, `vault-update`, `youtube-channel`/`youtube-queue`). One concrete fix identified:

- **`bloodwork-ingest.md`**: currently hardcodes this user's specific family-history-to-marker mapping (e.g. "Maternal Hashimoto's/celiac → TSH, Free T3/T4..."). Change to: read whatever family-history conditions the user's own profile documents, and map *generically* to standard marker categories per condition-type (autoimmune thyroid → thyroid panel + antibodies, cardiovascular risk → lipid panel + ApoB/Lp(a), metabolic/diabetes risk → glucose/insulin/HbA1c, etc.) — the mapping *logic* stays, the specific conditions become an input rather than a fixed list.

## Biometric pipeline — canonical schema + device adapters

Split into two layers with a documented interface:

**Canonical Daily-note schema** (device-agnostic, what the analyzer/dashboard consume):
```
readiness_score, sleep_score, hrv, resting_hr,
sleep_total_hours, sleep_efficiency, sleep_rem_hours, sleep_deep_hours, sleep_light_hours,
activity_score, steps, calories_active, activity_total_min,
workouts, active_protocols, training_load_hrs
```

**Device-specific extras**: every additional metric a given device's API exposes gets captured too (matching the existing "pull everything the API exposes" philosophy, not a curated subset) — namespaced as `<device>_<field_name>` (e.g. `oura_readiness_sleep_balance`, `oura_recovery_index`, a future `whoop_strain_score`) so multiple devices' data in the same vault's history never collide.

**Adapter contract**: a new device sync command must map that device's API fields into the canonical schema above, and may add any number of `<device>_*` extras. Nothing else in the pipeline changes.

**Analyzer/dashboard**: `biometric_analyze.py`/`generate_dashboard.py` already operate generically over "every numeric field present across Daily notes" rather than a hardcoded enum (this is how the current Oura version gracefully handles fields with varying null-rates) — so device-specific extras get folded into correlations/modeling automatically, zero special-casing required per device.

**Ships with this plugin**: only the Oura adapter (`oura-sync`/`oura_sync.py`), since that's the only one actually built and tested. The Whoop (or other) adapter is documented as a contract for someone else to implement, not built speculatively.

## CLAUDE.md template

`templates/CLAUDE.md.template` ships as a starter, not a live config — a new user copies it into their own vault root and customizes: folder names (if they want different ones than the default `Concepts/`, `Protocols/`, `Daily/`, `Synthesis/`, `Research/`, `People/`, `Bloodwork/`), domain framing (this vault's mental-health-as-first-class-domain principle is worth keeping as a strong default recommendation, but should be clearly editable, not hardcoded assertion), and personal-tailoring specifics. Mirrors the `_CLAUDE.md` folder-map-override pattern the parent skill already uses.

## Out of scope for this pass

- Building an actual Whoop (or other device) adapter — only the contract is documented.
- A public marketplace listing / `marketplace.json` — can follow once the plugin repo exists and is tested by installing it into a second, fresh vault.
- Migrating this existing repo to actually consume the new plugin (a follow-on step once the plugin is built and verified, not part of this design).
- Any change to vault content conventions (Daily note frontmatter shape stays the same for Oura users; this design only affects how the *tooling* is packaged and how a *different* device would plug in).

## Open questions for implementation planning

- Final plugin name (`health-vault-toolkit` is provisional).
- Whether `.claude-plugin/plugin.json` needs its own `mcpServers` block for the Oura MCP server, or whether that stays a per-vault `.mcp.json` concern (matching how `oura`/`excel` are currently registered in *this* repo's `.mcp.json`, not bundled into `obsidian-second-brain`'s own plugin.json).
- Versioning scheme for the new repo (start at `0.1.0`, matching the parent skill's convention).
