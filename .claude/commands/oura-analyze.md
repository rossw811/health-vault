---
description: The most thorough personal-health analysis this vault can honestly support - correlations, FDR-corrected tag comparisons, rolling 7d/28d trends, personal-baseline (not population-baseline) anomaly detection, lag-correlation (does a leading behavior predict tomorrow's outcome, not just same-day), protocol before/after effectiveness testing, and appropriately-scaled predictive modeling. Writes actionable findings to Synthesis/. Never overclaims from a small sample - thorough means more rigorous, not just more claims.
category: research
---

Execute `/oura-analyze`:

## 1. Run the analysis script
```bash
python "scripts/generate_dashboard.py"
python "scripts/oura_analyze.py"
```
`oura_analyze.py` does ALL the actual math (correlations, group comparisons with FDR-corrected significance, cross-validated model fits, multi-method regime detection) and prints one JSON blob. **You do not compute statistics yourself — read its output, don't recompute or approximate numbers by eye.** This script is designed for this dataset's actual shape (a few hundred rows at most, dozens of features) — it tests a wide model panel (RidgeCV, RandomForest, ExtraTrees, XGBoost, and — gated behind a much higher row-count floor, `MIN_N_FOR_DEEP_LEARNING` — a small regularized MLP), but every model reports an explicit `overfit_gap` (train R² minus cross-validated R²) so overfitting shows up as a number, not something inferred from the CV score alone. Regime detection similarly runs three distinct methods (k-means, GMM, HMM) rather than one, since they make different structural assumptions (hard spherical clusters vs. soft/elliptical clusters vs. sequential state persistence) and agreement between them is a stronger signal than any single method. If you think a different method is warranted, extend the script, don't hand-wave results in prose.

## 2. Read the output honestly
- `n_daily_notes_found` and `date_range` — state this plainly up front. If it's small, say so before anything else, not buried at the end.
- `correlations.notable_pairs_abs_r_gte_0.3` — Spearman correlations across all numeric Oura fields. Report the actual pairs and coefficients; do not editorialize causation onto a correlation.
- `tag_comparisons` — per-`active_protocols`-tag comparison against every metric, **already FDR-corrected** (`significant_after_fdr_correction`). Only report a tag/metric relationship as "significant" if that flag is true — an uncorrected `p_raw < 0.05` alone is NOT a finding at this scale (with dozens of tag x metric combinations tested, some will look significant by chance alone; that's exactly what the correction is for).
- `predictive_models` — if a target shows `"skipped"` or the top-level `_warning` fired (below the 20-day floor), report that plainly and stop there for modeling — do not try to describe a model that wasn't fit. Each target that DID fit has a `models` dict with up to five entries (`ridge_linear`, `random_forest`, `extra_trees`, `xgboost`, `mlp_deep_learning` — the last one itself may say `"skipped"` if below `MIN_N_FOR_DEEP_LEARNING`). For every model that ran: `cv_r2_mean` is the number that matters, not `train_r2` — a near-zero or negative CV R² means "no real predictive signal found," a valid, reportable finding. Also read `overfit_gap`/`likely_overfitting` for every model — a model with decent `cv_r2_mean` but `likely_overfitting: true` should be reported with that caveat explicitly, not presented as clean. Report whichever model has the best genuinely-cross-validated (not in-sample) performance as the headline for that target, and note if multiple models roughly agree on the same top features/coefficients — cross-model agreement is stronger evidence than any single model's output.
- `regime_analysis_kmeans` / `regime_analysis_gmm` / `regime_analysis_hmm` — three structurally different regime-detection methods over the same features. k-means/GMM report `silhouette_score`/BIC-selected k and per-cluster profiles; HMM additionally reports a `transition_matrix` (state persistence) and a `state_timeline` (when transitions actually happened), plus its own `train_vs_holdout_gap_at_chosen_k`/`likely_overfitting`. Report where the methods agree (similar cluster count and profiles) as the stronger finding; report disagreement honestly as ambiguous structure, not resolved in favor of one method.
- `rolling_trends` — per metric: `latest_7d_avg`/`latest_28d_avg` against `overall_mean`/`overall_std` (this is the personal-baseline view — "high for you," not "high in general"), and `week_over_week_delta`. Report metrics whose 7-day average sits meaningfully away from their own overall mean (roughly beyond half an `overall_std`) as the headline trend items.
- `personal_baseline_anomalies` — days in the last 14 where a metric was ≥2 SD from *that metric's own* full-history mean. An empty list is a real, reportable finding ("nothing unusual recently"), not a null result to skip past. Note deviation direction (above/below) — "above" isn't automatically good or bad, depends on the metric (e.g. resting HR above baseline is the opposite valence of readiness above baseline).
- `lag_correlations` — already FDR-corrected. Only report a `leading_metric -> outcome_metric` relationship as a real lag effect if `significant_after_fdr_correction` is true. This is what tells you "yesterday's activity level" vs. "today's readiness," which same-day correlation structurally cannot show.
- `protocol_before_after` — FDR-corrected before/after comparison for every Protocol with a `start_date`. Only report `significant_after_fdr_correction: true` results as "this protocol appears associated with a change" — and even then, phrase it as association, not proof the protocol caused it (something else could have changed at the same time). `note`/`protocols_seen` fields mean nothing testable exists yet — report that plainly rather than skipping the section.

## 3. Turn findings into actionable recommendations - this is the point of "thorough"
A pile of correlations is not "actionable information." For every result that actually survived FDR correction (tag comparison, lag correlation, or protocol before/after) OR every rolling-trend metric sitting meaningfully away from its own baseline: search `Concepts/` for a note that already explains a plausible mechanism. If one exists, cross-link it and state the mechanism briefly - this is what makes a finding actionable rather than just a number ("HRV lag-correlates with prior-day steps below X; `[[Concepts/...]]` already documents the autonomic-recovery mechanism this is consistent with"). If no mechanism note exists yet, say so and suggest `/research` or `/concept-audit` as the next step rather than inventing a mechanism yourself. Write this as its own `## Actionable findings` section, ranked by how well-supported each one is (FDR-significant > rolling-trend-notable > exploratory), not just listed in discovery order.

## 4. Write the Synthesis note
`Synthesis/Oura Analysis - YYYY-MM-DD.md` (`type: synthesis`, tags `[synthesis, oura, statistics]`, `ai-first: true`):
- `## For future Claude` preamble stating the sample size and date range up front.
- `## Sample size and what that means for confidence` — first substantive section, not a footnote. Be explicit about `MIN_N_FOR_MODELING`/`MIN_N_PER_GROUP_FOR_TEST` gates and what's usable vs. not yet.
- `## Correlations across biometrics` — the notable pairs, described factually.
- `## Personal-baseline trends and anomalies` — rolling trends + anomaly list.
- `## Lag effects` — FDR-significant leading→outcome relationships, or "none found yet."
- `## Tag vs. biometric comparisons` — only the FDR-significant ones as "findings"; everything else goes in a clearly-separated "did not survive correction" or "not enough data yet" list, not mixed in as if equally reliable.
- `## Protocol before/after` — FDR-significant protocol effects, or "no protocol has enough before/after data yet."
- `## Predictive modeling` — per target: whether it ran, and for each model that fit, its cross-validated R² and `overfit_gap`/`likely_overfitting` flag. Lead with whichever model has the best genuinely-cross-validated performance; only report top features/coefficients for a model that shows real signal (meaningfully positive CV R²) AND isn't flagged `likely_overfitting`. State plainly when a model found nothing, or when a decent CV R² came with an overfitting flag attached.
- `## Regime detection` — k-means/GMM/HMM results: chosen state count per method, whether the methods broadly agree, and (for HMM) state persistence/transitions. Note any method flagged `likely_overfitting` and don't present its state definitions as settled.
- `## Actionable findings` — the step 3 synthesis, ranked by evidence strength.
- `## Open questions / what more data would resolve` — what this analysis can't yet answer given current N, so future re-runs have a target.

## 5. Re-run cadence
This is not scheduled automatically — re-run manually as `Daily/` history grows (especially after an Oura backfill), or fold a periodic call into `/vault-update` later if it proves useful enough to want standing.

## 6. Summary to user
Sample size, headline correlations, personal-baseline trend/anomaly highlights, any FDR-significant lag/tag/protocol findings (or "none survived correction yet"), model results (or why modeling was skipped), top actionable findings, and the note path.

**Anti-fabrication:** every number in the note must come directly from the script's JSON output - never estimate, round more than the script already did, or state a relationship the script didn't actually report. If the script's output is thin, the note is thin - don't pad it with generic health advice to fill space.
