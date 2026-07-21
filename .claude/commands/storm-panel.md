---
description: Stanford STORM-style multi-perspective panel grounded in this vault's actual sources - 4 domain-expert lenses debate a question, cross-examine disagreements, and synthesize a protocol note. Local simulation, no external search APIs.
category: research
---

Use this alongside the obsidian-second-brain skill. Execute `/storm-panel [question]`:

This combines the vault-grounding of `/vault-deep-synthesis` with the independent-verdict structure of `/obsidian-panel`, plus a cross-examination pass — the parts of Stanford STORM's method that matter here (multi-perspective, source-grounded, adversarial on disagreement) without the paid search-API infrastructure the original pipeline assumes.

1. Resolve the question from the argument. If none, ask what to put to the panel.

2. **Ground first, exhaustively.** Before any persona speaks, grep and read every note in `Sources/`, `Concepts/`, `Protocols/`, and `Research/` that touches the question — every plausible name, alias, and synonym, not a sample. This step is identical in rigor to `/vault-deep-synthesis` step 2–3: list what the vault agrees on, what's contradictory, what's stale, and what's simply missing. If the vault is thin on the topic, say so plainly — do not let personas invent evidence to fill the gap.

3. **Panel of 4 domain lenses** (override with user-specified personas if given; otherwise default to the performance-research defaults below). Each panelist writes an INDEPENDENT verdict grounded only in step 2's material (plus clearly-labeled general domain knowledge when the vault is silent) — position, strongest reasoning, and what evidence would change their mind. Do not let them converge prematurely:
   - **Perspective A — Neurological/performance coach**: CNS load, intensity management, neural drive and fatigue.
   - **Perspective B — Systemic volume scientist**: total training volume, periodization, fatigue-management-by-volume.
   - **Perspective C — Clinical/longevity physician**: biomarker-driven, risk/benefit, long-horizon health tradeoffs.
   - **Perspective D — Biochemical optimization practitioner**: supplementation, nutrient timing, recovery biochemistry.

4. **Cross-examination loop.** Identify every point where panelists disagree (this is the most useful output — do not paper over it). For each disagreement, have the panelists respond directly to each other's strongest point once. Note where disagreement resolves vs. where it's a genuine, irreducible tradeoff.

5. **Synthesize.** Write one master note to `Synthesis/YYYY-MM-DD - storm - <question-slug>.md`:
   - `## For future Claude` preamble per `references/ai-first-rules.md` (found under the obsidian-second-brain skill root).
   - Frontmatter: `type: synthesis`, `tags: [synthesis, storm-panel, research]`, `question`, `date`, list of source notes read in step 2.
   - Section per panelist verdict (with `[[wikilinks]]` to grounding notes).
   - Cross-examination section (resolved vs. irreducible disagreements).
   - A synthesized recommendation with its main risk and open questions/coverage gaps from step 2.
   - `[[wikilinks]]` to every Concept/Protocol/Source note actually used.

6. Cross-link from today's daily note.

**Anti-fabrication:** Every claim attributed to a panelist's framework must trace to either the grounding material from step 2 or clearly-labeled general domain knowledge — never invent a study, a number, or a source. Never manufacture false consensus; an irreducible disagreement is a valid, useful output. See `references/ai-first-rules.md` in the skill root for the full anti-fabrication and search-completeness rules.
