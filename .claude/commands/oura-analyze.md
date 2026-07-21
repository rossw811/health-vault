---
description: Statistically honest analysis of all Daily/ Oura data - correlations across every metric, tag-based group comparisons (active_protocols vs. biometrics, FDR-corrected), and appropriately-scaled predictive modeling (regularized regression + shallow random forest, cross-validated, small-N-aware). Writes findings to Synthesis/. Never overclaims from a small sample.
category: research
---

Execute `/oura-analyze`:

## 1. Run the analysis script
```bash
python "scripts/generate_dashboard.py"
python "scripts/oura_analyze.py"
```
`oura_analyze.py` does ALL the actual math (correlations, group comparisons with FDR-corrected significance, cross-validated model fits) and prints one JSON blob. **You do not compute statistics yourself — read its output, don't recompute or approximate numbers by eye.** This script is deliberately designed for this dataset's actual shape (a few hundred rows at most, dozens of features) — regularized linear models and a shallow cross-validated random forest, not deep learning, which would simply overfit noise at this scale. If you think a different method is warranted, extend the script, don't hand-wave results in prose.

## 2. Read the output honestly
- `n_daily_notes_found` and `date_range` — state this plainly up front. If it's small, say so before anything else, not buried at the end.
- `correlations.notable_pairs_abs_r_gte_0.3` — Spearman correlations across all numeric Oura fields. Report the actual pairs and coefficients; do not editorialize causation onto a correlation.
- `tag_comparisons` — per-`active_protocols`-tag comparison against every metric, **already FDR-corrected** (`significant_after_fdr_correction`). Only report a tag/metric relationship as "significant" if that flag is true — an uncorrected `p_raw < 0.05` alone is NOT a finding at this scale (with dozens of tag x metric combinations tested, some will look significant by chance alone; that's exactly what the correction is for).
- `predictive_models` — if a target shows `"skipped"` or the top-level `_warning` fired (below the 20-day floor), report that plainly and stop there for modeling — do not try to describe a model that wasn't fit. If a model DID fit, `*_cv_r2_mean` is the number that matters, not any in-sample fit — a near-zero or negative CV R² means "no real predictive signal found," and that is a valid, useful, reportable finding, not a failure to hide.

## 3. Write the Synthesis note
`Synthesis/Oura Analysis - YYYY-MM-DD.md` (`type: synthesis`, tags `[synthesis, oura, statistics]`, `ai-first: true`):
- `## For future Claude` preamble stating the sample size and date range up front.
- `## Sample size and what that means for confidence` — first substantive section, not a footnote. Be explicit about `MIN_N_FOR_MODELING`/`MIN_N_PER_GROUP_FOR_TEST` gates and what's usable vs. not yet.
- `## Correlations across biometrics` — the notable pairs, described factually.
- `## Tag vs. biometric comparisons` — only the FDR-significant ones as "findings"; everything else goes in a clearly-separated "did not survive correction" or "not enough data yet" list, not mixed in as if equally reliable.
- `## Predictive modeling` — per target: whether it ran, cross-validated R², and (only if the model shows real signal, i.e. meaningfully positive CV R²) its top features/coefficients. State plainly when a model found nothing.
- `## Open questions / what more data would resolve` — what this analysis can't yet answer given current N, so future re-runs have a target.

## 4. Re-run cadence
This is not scheduled automatically — re-run manually as `Daily/` history grows (especially after an Oura backfill), or fold a periodic call into `/vault-update` later if it proves useful enough to want standing.

## 5. Summary to user
Sample size, headline correlations, any FDR-significant tag findings (or "none survived correction yet"), model results (or why modeling was skipped), and the note path.

**Anti-fabrication:** every number in the note must come directly from the script's JSON output - never estimate, round more than the script already did, or state a relationship the script didn't actually report. If the script's output is thin, the note is thin - don't pad it with generic health advice to fill space.
