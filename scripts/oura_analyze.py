#!/usr/bin/env python3
"""Statistically honest analysis of Daily/ Oura data vs. active_protocols tags.

Design intent (read before changing): with likely a few hundred daily rows and
dozens of numeric metrics plus a handful of tags, this is a small-N / many-
features problem. Deep learning is the wrong tool here - it would overfit
immediately. This script deliberately uses interpretable, appropriately-scaled
methods (correlations, group comparisons with effect sizes, regularized linear
models, a shallow cross-validated random forest) and reports honestly when
there isn't enough data to trust a result. It never prints a naive in-sample
R^2 or an uncorrected p-value as if it were a finding.

Outputs a single JSON blob to stdout - Claude reads this and writes the
narrative Synthesis note; this script only computes, never interprets.
"""

import json
import re
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats
from statsmodels.stats.multitest import multipletests

warnings.filterwarnings("ignore")

VAULT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = VAULT_ROOT / "Daily"
PROTOCOLS_DIR = VAULT_ROOT / "Protocols"

NUMERIC_FIELDS = [
    "readiness_score", "readiness_hrv_balance", "readiness_resting_hr",
    "readiness_body_temp_deviation", "readiness_temp_trend_deviation",
    "readiness_recovery_index", "readiness_sleep_balance",
    "readiness_activity_balance", "readiness_previous_day_activity",
    "readiness_previous_night", "sleep_score", "sleep_total_hours",
    "sleep_efficiency", "sleep_latency_min", "sleep_rem_hours",
    "sleep_deep_hours", "sleep_light_hours", "sleep_time_in_bed_hours",
    "sleep_avg_breath", "sleep_restless_periods", "average_hrv", "resting_hr",
    "activity_score", "steps", "calories_active", "activity_total_min",
    "inactivity_min", "spo2_avg", "training_load_hrs",
    # Added 2026-08-01: these fields were already validated by schemas.py's
    # oura_daily_schema but never actually analyzed - synced and checked, then
    # silently ignored by every function below (correlation, tag comparisons,
    # rolling trends, anomaly detection, protocol before/after, modeling) since
    # they all key off this one list. Wiring them in here is the whole fix -
    # no other function needed to change.
    "readiness_sleep_regularity", "resilience_sleep_recovery",
    "resilience_daytime_recovery", "resilience_stress", "cardio_vascular_age",
    "cardio_pulse_wave_velocity", "vo2_max",
    "activity_contrib_meet_daily_targets", "activity_contrib_move_every_hour",
    "activity_contrib_recovery_time", "activity_contrib_stay_active",
    "activity_contrib_training_frequency", "activity_contrib_training_volume",
    "activity_equivalent_walking_distance_m", "activity_non_wear_min",
    "activity_resting_min", "activity_target_calories",
    "activity_total_calories", "activity_target_meters",
    "activity_meters_to_target",
]

# Below this row count, model results are exploratory-only, not trustworthy.
MIN_N_FOR_MODELING = 20
MIN_N_PER_GROUP_FOR_TEST = 5


def load_daily_frame():
    rows = []
    if not DAILY_DIR.exists():
        return pd.DataFrame()
    for path in sorted(DAILY_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        row = {"date": fm.get("date", path.stem)}
        for field in NUMERIC_FIELDS:
            val = fm.get(field)
            row[field] = val if isinstance(val, (int, float)) else np.nan
        protocols = fm.get("active_protocols") or []
        row["_protocols"] = protocols if isinstance(protocols, list) else []
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df.attrs["qc_warnings"] = validate_daily_frame(df)
    return df


def validate_daily_frame(df):
    """Flag biologically-impossible values (e.g. a mis-parsed frontmatter field)
    without blocking analysis - same anti-silent-failure principle as everywhere
    else in this vault. Returns a list of warning strings (empty if clean)."""
    from schemas import oura_daily_schema, validate_or_report

    if df.empty:
        return []
    ok, messages = validate_or_report(oura_daily_schema, df, "oura-daily")
    return [] if ok else messages


def correlation_matrix(df):
    numeric = df[NUMERIC_FIELDS].dropna(axis=1, how="all")
    if numeric.shape[1] < 2 or len(numeric) < 3:
        return {"note": "not enough data for a correlation matrix", "n_rows": len(numeric)}
    corr = numeric.corr(method="spearman", min_periods=3)
    pairs = []
    cols = corr.columns.tolist()
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r) and abs(r) >= 0.3:
                pairs.append({"a": a, "b": b, "spearman_r": round(float(r), 3)})
    pairs.sort(key=lambda p: -abs(p["spearman_r"]))
    return {"n_rows_used": len(numeric), "notable_pairs_abs_r_gte_0.3": pairs}


def tag_group_comparisons(df):
    if "_protocols" not in df.columns:
        return {"note": "no active_protocols data present"}
    all_tags = sorted({t for row in df["_protocols"] for t in row})
    if not all_tags:
        return {"note": "no active_protocols have been logged in any Daily note yet"}

    raw_results = []
    for tag in all_tags:
        has_tag = df["_protocols"].apply(lambda p, tag=tag: tag in p)  # noqa: B023 - bound via default arg for clarity; .apply() already runs this immediately per-iteration
        for metric in NUMERIC_FIELDS:
            with_vals = df.loc[has_tag, metric].dropna()
            without_vals = df.loc[~has_tag, metric].dropna()
            if len(with_vals) < MIN_N_PER_GROUP_FOR_TEST or len(without_vals) < MIN_N_PER_GROUP_FOR_TEST:
                continue
            stat, pval = stats.mannwhitneyu(with_vals, without_vals, alternative="two-sided")
            pooled_std = np.sqrt(((len(with_vals) - 1) * with_vals.std() ** 2 +
                                   (len(without_vals) - 1) * without_vals.std() ** 2) /
                                  (len(with_vals) + len(without_vals) - 2)) if (len(with_vals) + len(without_vals)) > 2 else np.nan
            cohens_d = (with_vals.mean() - without_vals.mean()) / pooled_std if pooled_std and pooled_std > 0 else np.nan
            raw_results.append({
                "tag": tag, "metric": metric,
                "n_with": int(len(with_vals)), "n_without": int(len(without_vals)),
                "mean_with": round(float(with_vals.mean()), 2),
                "mean_without": round(float(without_vals.mean()), 2),
                "cohens_d": round(float(cohens_d), 3) if pd.notna(cohens_d) else None,
                "p_raw": float(pval),
            })

    if not raw_results:
        return {
            "note": f"found tags but no metric had >= {MIN_N_PER_GROUP_FOR_TEST} days both with and without it yet - too little data to compare",
            "tags_seen": all_tags,
        }

    pvals = [r["p_raw"] for r in raw_results]
    reject, pvals_fdr, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
    for r, p_adj, sig in zip(raw_results, pvals_fdr, reject, strict=True):
        r["p_fdr_corrected"] = round(float(p_adj), 4)
        r["significant_after_fdr_correction"] = bool(sig)
    raw_results.sort(key=lambda r: r["p_fdr_corrected"])
    return {"n_tests_run": len(raw_results), "results": raw_results}


def rolling_trends(df):
    """7d/28d rolling averages, latest vs. overall baseline, week-over-week delta.
    This is what a personal-baseline view gives you that a population-relative
    app score doesn't: 'high for a Tuesday' vs 'high for YOU'."""
    out = {}
    for metric in NUMERIC_FIELDS:
        series = df.set_index("date")[metric].dropna()
        if len(series) < 10:
            continue
        overall_mean = float(series.mean())
        overall_std = float(series.std())
        roll7 = series.rolling("7D").mean()
        roll28 = series.rolling("28D").mean()
        latest_7d = float(roll7.iloc[-1]) if pd.notna(roll7.iloc[-1]) else None
        latest_28d = float(roll28.iloc[-1]) if pd.notna(roll28.iloc[-1]) else None
        # Week-over-week: compare the last 7 days' mean to the 7 days before that.
        last_date = series.index.max()
        this_week = series[series.index > last_date - pd.Timedelta(days=7)]
        prior_week = series[(series.index <= last_date - pd.Timedelta(days=7)) &
                             (series.index > last_date - pd.Timedelta(days=14))]
        wow_delta = None
        if len(this_week) >= 3 and len(prior_week) >= 3:
            wow_delta = round(float(this_week.mean() - prior_week.mean()), 3)
        out[metric] = {
            "n": len(series),
            "overall_mean": round(overall_mean, 2),
            "overall_std": round(overall_std, 2),
            "latest_7d_avg": round(latest_7d, 2) if latest_7d is not None else None,
            "latest_28d_avg": round(latest_28d, 2) if latest_28d is not None else None,
            "week_over_week_delta": wow_delta,
        }
    return out


def personal_baseline_anomalies(df, lookback_days=14):
    """Flag recent days that deviate >=2 SD from THIS metric's own full-history
    mean - a personal baseline, not a population one. This is the thing Whoop/
    Oura's own score can't do: 'unusual for you' vs 'unusual in general'."""
    anomalies = []
    if len(df) < 15:
        return {"note": "fewer than 15 days total - too little history to define a personal baseline yet"}
    recent_cutoff = df["date"].max() - pd.Timedelta(days=lookback_days)
    for metric in NUMERIC_FIELDS:
        series = df.set_index("date")[metric].dropna()
        if len(series) < 15:
            continue
        mean, std = float(series.mean()), float(series.std())
        if not std or std == 0:
            continue
        recent = series[series.index > recent_cutoff]
        for date, val in recent.items():
            z = (val - mean) / std
            if abs(z) >= 2:
                anomalies.append({
                    "date": date.strftime("%Y-%m-%d"), "metric": metric, "value": round(float(val), 2),
                    "personal_mean": round(mean, 2), "z_score": round(float(z), 2),
                    "direction": "above" if z > 0 else "below",
                })
    anomalies.sort(key=lambda a: (a["date"], -abs(a["z_score"])))
    return {"lookback_days": lookback_days, "anomalies": anomalies}


def lag_correlation(df):
    """Does a 'leading' behavioral metric predict an 'outcome' metric 1-3 days
    later? Same-day correlation (already computed above) can't tell you this -
    it's the difference between 'these move together' and 'this might be
    driving that'. Still correlation, not proof of causation, but a same-day-
    only view is structurally blind to lagged effects entirely."""
    leading = ["steps", "activity_score", "activity_total_min", "training_load_hrs", "inactivity_min"]
    outcomes = ["readiness_score", "average_hrv", "sleep_score", "resting_hr"]
    leading = [c for c in leading if c in df.columns]
    outcomes = [c for c in outcomes if c in df.columns]
    indexed = df.set_index("date")

    raw_results = []
    for lead in leading:
        for outcome in outcomes:
            if lead == outcome:
                continue
            for lag in (1, 2, 3):
                shifted_lead = indexed[lead].shift(lag)
                pair = pd.concat([shifted_lead, indexed[outcome]], axis=1).dropna()
                if len(pair) < MIN_N_PER_GROUP_FOR_TEST + 5:
                    continue
                r, p = stats.spearmanr(pair.iloc[:, 0], pair.iloc[:, 1])
                if pd.isna(r):
                    continue
                raw_results.append({
                    "leading_metric": lead, "lag_days": lag, "outcome_metric": outcome,
                    "n": len(pair), "spearman_r": round(float(r), 3), "p_raw": float(p),
                })
    if not raw_results:
        return {"note": "not enough overlapping data yet for any lag pair"}
    pvals = [r["p_raw"] for r in raw_results]
    reject, pvals_fdr, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
    for r, p_adj, sig in zip(raw_results, pvals_fdr, reject, strict=True):
        r["p_fdr_corrected"] = round(float(p_adj), 4)
        r["significant_after_fdr_correction"] = bool(sig)
    raw_results = [r for r in raw_results if abs(r["spearman_r"]) >= 0.25 or r["significant_after_fdr_correction"]]
    raw_results.sort(key=lambda r: r["p_fdr_corrected"])
    return {"n_tests_run": len(pvals), "notable_or_significant_pairs": raw_results}


def load_protocol_start_dates():
    """Protocols/*.md with a start_date - the anchor for before/after testing."""
    protocols = []
    if not PROTOCOLS_DIR.exists():
        return protocols
    for path in sorted(PROTOCOLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        start = fm.get("start_date")
        if start:
            protocols.append({"name": path.stem, "start_date": str(start)})
    return protocols


def protocol_before_after(df):
    """For every Protocol with a documented start_date: compare each metric in
    the window before vs. after that date. This is the actual 'did this
    protocol do anything' test - a graph with a vertical line on it is not a
    statistical comparison, this is."""
    protocols = load_protocol_start_dates()
    if not protocols:
        return {"note": "no Protocols/*.md have a start_date set yet - nothing to test before/after"}

    raw_results = []
    for proto in protocols:
        try:
            start = pd.Timestamp(proto["start_date"])
        except (ValueError, TypeError):
            continue
        before = df[df["date"] < start]
        after = df[df["date"] >= start]
        for metric in NUMERIC_FIELDS:
            b = before[metric].dropna()
            a = after[metric].dropna()
            if len(b) < MIN_N_PER_GROUP_FOR_TEST or len(a) < MIN_N_PER_GROUP_FOR_TEST:
                continue
            stat, pval = stats.mannwhitneyu(b, a, alternative="two-sided")
            pooled_std = np.sqrt(((len(b) - 1) * b.std() ** 2 + (len(a) - 1) * a.std() ** 2) /
                                  (len(b) + len(a) - 2)) if (len(b) + len(a)) > 2 else np.nan
            cohens_d = (a.mean() - b.mean()) / pooled_std if pooled_std and pooled_std > 0 else np.nan
            raw_results.append({
                "protocol": proto["name"], "start_date": proto["start_date"], "metric": metric,
                "n_before": int(len(b)), "n_after": int(len(a)),
                "mean_before": round(float(b.mean()), 2), "mean_after": round(float(a.mean()), 2),
                "cohens_d": round(float(cohens_d), 3) if pd.notna(cohens_d) else None,
                "p_raw": float(pval),
            })
    if not raw_results:
        return {
            "note": f"protocols with start_date exist but no metric has >= {MIN_N_PER_GROUP_FOR_TEST} days both before and after yet",
            "protocols_seen": [p["name"] for p in protocols],
        }
    pvals = [r["p_raw"] for r in raw_results]
    reject, pvals_fdr, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
    for r, p_adj, sig in zip(raw_results, pvals_fdr, reject, strict=True):
        r["p_fdr_corrected"] = round(float(p_adj), 4)
        r["significant_after_fdr_correction"] = bool(sig)
    raw_results.sort(key=lambda r: r["p_fdr_corrected"])
    return {"n_tests_run": len(raw_results), "results": raw_results}


def predictive_modeling(df):
    targets = ["readiness_score", "average_hrv", "sleep_score", "activity_score"]
    out = {}
    n = len(df)
    if n < MIN_N_FOR_MODELING:
        out["_warning"] = (
            f"Only {n} days of data - below the {MIN_N_FOR_MODELING}-day floor this script "
            "requires before modeling. Any model fit here would be memorizing noise, not "
            "finding a real signal. Skipping modeling entirely rather than printing a "
            "misleading result."
        )
        return out

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import RidgeCV
    from sklearn.model_selection import KFold, cross_val_score

    all_feature_cols = [c for c in NUMERIC_FIELDS if c not in targets]
    k = min(5, n // 4) if n >= 20 else 2
    for target in targets:
        # Only require the TARGET to be present - features are median-imputed.
        # Listwise deletion across every feature column is wrong here: Oura
        # fields like spo2_avg/stress vary in sensor/tier availability day to
        # day, so requiring all of them non-null can (and did) leave zero
        # usable rows even with 40+ days of real target data.
        sub = df[df[target].notna()].copy()
        if len(sub) < MIN_N_FOR_MODELING:
            out[target] = {"skipped": f"only {len(sub)} rows with a real {target} value, below floor"}
            continue
        feature_cols = [c for c in all_feature_cols if sub[c].notna().sum() >= MIN_N_FOR_MODELING]
        if len(feature_cols) < 2:
            out[target] = {"skipped": f"only {len(feature_cols)} feature(s) have enough non-null data yet"}
            continue
        X = sub[feature_cols].fillna(sub[feature_cols].median())
        y = sub[target]
        kf = KFold(n_splits=k, shuffle=True, random_state=0)

        ridge = RidgeCV(alphas=np.logspace(-2, 3, 20))
        ridge_scores = cross_val_score(ridge, X, y, cv=kf, scoring="r2")
        ridge.fit(X, y)

        rf = RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=max(2, len(sub) // 20), random_state=0)
        rf_scores = cross_val_score(rf, X, y, cv=kf, scoring="r2")
        rf.fit(X, y)

        out[target] = {
            "n_rows": len(sub),
            "ridge_cv_r2_mean": round(float(ridge_scores.mean()), 3),
            "ridge_cv_r2_all_folds": [round(float(s), 3) for s in ridge_scores],
            "ridge_top_coefficients": sorted(
                [{"feature": f, "coef": round(float(c), 4)} for f, c in zip(feature_cols, ridge.coef_, strict=True)],
                key=lambda d: -abs(d["coef"]),
            )[:8],
            "random_forest_cv_r2_mean": round(float(rf_scores.mean()), 3),
            "random_forest_top_features": sorted(
                [{"feature": f, "importance": round(float(i), 4)} for f, i in zip(feature_cols, rf.feature_importances_, strict=True)],
                key=lambda d: -d["importance"],
            )[:8],
            "interpretation_note": (
                "cv_r2_mean near or below 0 means the model found no real predictive signal - "
                "report that plainly, don't just report the coefficients as if they mattered."
            ),
        }
    return out


def short_vs_long_term_ranges(df, short_window_days=14):
    """Explicit short-term vs. long-term range comparison, added 2026-08-01.
    rolling_trends() already reports 7d/28d *means* vs. the overall mean, but
    that's a single-number comparison - it doesn't say whether the current
    short-term window is actually operating in a different RANGE (min/max/
    spread) than the metric's long-term history, which is what 'regime'
    actually means physiologically (e.g. resting HR has settled 5bpm higher
    for two weeks - the mean shift alone doesn't tell you if that's a blip or
    a genuine new operating range). short_window_days=14 (not 7) deliberately
    differs from rolling_trends' 7d window - this function answers 'has my
    range shifted', which needs slightly more days to be meaningful than a
    same-day mean check does."""
    out = {}
    if len(df) < 15:
        return {"note": "fewer than 15 days total - too little history to compare short vs. long-term ranges yet"}
    cutoff = df["date"].max() - pd.Timedelta(days=short_window_days)
    for metric in NUMERIC_FIELDS:
        series = df.set_index("date")[metric].dropna()
        long_term = series
        short_term = series[series.index > cutoff]
        if len(long_term) < 15 or len(short_term) < 5:
            continue
        lt_mean, lt_std = float(long_term.mean()), float(long_term.std())
        st_mean, st_std = float(short_term.mean()), float(short_term.std())
        if not lt_std or lt_std == 0:
            continue
        # Simple, honest divergence flag reusing this file's existing z-score
        # convention (personal_baseline_anomalies uses the same >=2 threshold)
        # rather than inventing a new statistical test for this function.
        z = (st_mean - lt_mean) / lt_std
        out[metric] = {
            "short_term_window_days": short_window_days,
            "short_term": {"n": len(short_term), "mean": round(st_mean, 2), "std": round(st_std, 2) if pd.notna(st_std) else None,
                            "min": round(float(short_term.min()), 2), "max": round(float(short_term.max()), 2)},
            "long_term": {"n": len(long_term), "mean": round(lt_mean, 2), "std": round(lt_std, 2),
                          "min": round(float(long_term.min()), 2), "max": round(float(long_term.max()), 2)},
            "short_term_mean_z_vs_long_term": round(float(z), 2),
            "range_shift_flag": abs(z) >= 2,
        }
    shifted = {k: v for k, v in out.items() if v["range_shift_flag"]}
    return {
        "short_window_days": short_window_days,
        "n_metrics_compared": len(out),
        "metrics_with_a_range_shift": shifted,
        "all_metrics": out,
    }


def regime_analysis(df, k_range=(2, 5)):
    """K-means clustering over standardized daily biometrics to find distinct
    'regimes' (recurring physiological/behavioral states), added 2026-08-01.
    This is genuinely new capability, not wiring up something already present -
    everything else in this script is correlation/comparison/regression;
    nothing before this clustered days into groups. k is chosen via silhouette
    score across k_range rather than fixed, and reported honestly - a low
    silhouette score means the 'regimes' found are weak/overlapping, not a
    clean multi-state structure, and this function says so rather than
    presenting whichever k scored best as if it were a strong finding."""
    if len(df) < MIN_N_FOR_MODELING:
        return {"note": f"only {len(df)} days - below the {MIN_N_FOR_MODELING}-day floor this script requires before clustering. Skipping rather than fitting noise."}

    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    # Same median-imputation-after-availability-filter approach as
    # predictive_modeling() - requiring every feature non-null for every row
    # would leave near-zero usable rows given Oura's per-field sensor/tier
    # availability gaps.
    feature_cols = [c for c in NUMERIC_FIELDS if df[c].notna().sum() >= MIN_N_FOR_MODELING]
    if len(feature_cols) < 3:
        return {"note": f"only {len(feature_cols)} feature(s) have enough non-null data yet - too few dimensions to cluster meaningfully"}
    sub = df[["date"] + feature_cols].dropna(thresh=len(feature_cols) // 2 + 1, subset=feature_cols).copy()
    if len(sub) < MIN_N_FOR_MODELING:
        return {"note": f"only {len(sub)} rows have enough real (non-imputed-majority) feature coverage - below the {MIN_N_FOR_MODELING}-day floor"}
    X_raw = sub[feature_cols].fillna(sub[feature_cols].median())
    X = StandardScaler().fit_transform(X_raw)

    best_k, best_score, best_labels = None, -1.0, None
    scores_by_k = {}
    max_k = min(k_range[1], len(sub) // 5)  # never try more clusters than ~5 rows/cluster could support
    for k in range(k_range[0], max(k_range[0], max_k) + 1):
        if k >= len(sub):
            continue
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(X, labels)
        scores_by_k[k] = round(float(score), 3)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels
    if best_k is None:
        return {"note": "clustering did not converge to any valid k in range - not enough data structure to find regimes yet"}

    sub = sub.assign(_cluster=best_labels)
    cluster_profiles = []
    for c in sorted(set(best_labels)):
        rows = sub[sub["_cluster"] == c]
        profile_metrics = {}
        for metric in feature_cols:
            vals = rows[metric].dropna()
            if len(vals):
                profile_metrics[metric] = round(float(vals.mean()), 2)
        cluster_profiles.append({
            "cluster": int(c), "n_days": len(rows),
            "date_range": [rows["date"].min().strftime("%Y-%m-%d"), rows["date"].max().strftime("%Y-%m-%d")],
            "mean_profile": profile_metrics,
        })

    # Regime timeline: contiguous date-ordered runs of the same cluster label -
    # this is what makes it "regime" analysis rather than just a static
    # grouping - when did the state actually change, not just what states exist.
    sub_sorted = sub.sort_values("date")
    timeline = []
    prev_cluster, run_start = None, None
    for _, row in sub_sorted.iterrows():
        if row["_cluster"] != prev_cluster:
            if prev_cluster is not None:
                timeline.append({"cluster": int(prev_cluster), "start": run_start, "end": prev_date})
            prev_cluster, run_start = row["_cluster"], row["date"].strftime("%Y-%m-%d")
        prev_date = row["date"].strftime("%Y-%m-%d")
    if prev_cluster is not None:
        timeline.append({"cluster": int(prev_cluster), "start": run_start, "end": prev_date})

    return {
        "n_days_clustered": len(sub),
        "features_used": feature_cols,
        "k_chosen": best_k,
        "silhouette_score": round(float(best_score), 3),
        "silhouette_scores_by_k_tried": scores_by_k,
        "interpretation_note": (
            "silhouette_score ranges roughly -1 to 1; below ~0.25 means the clusters found are weak/"
            "overlapping, not a clean multi-regime structure - report that plainly rather than treating "
            "a low-silhouette k as a confident finding of distinct regimes."
        ),
        "cluster_profiles": cluster_profiles,
        "regime_timeline": timeline,
    }


def main():
    df = load_daily_frame()
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_daily_notes_found": len(df),
        "date_range": [
            df["date"].min().strftime("%Y-%m-%d") if len(df) else None,
            df["date"].max().strftime("%Y-%m-%d") if len(df) else None,
        ],
    }
    if len(df) == 0:
        result["warning"] = "No Daily/ notes found at all - nothing to analyze yet."
        print(json.dumps(result, indent=2))
        return

    qc_warnings = df.attrs.get("qc_warnings", [])
    if qc_warnings:
        result["qc_warnings"] = qc_warnings

    result["correlations"] = correlation_matrix(df)
    result["tag_comparisons"] = tag_group_comparisons(df)
    result["rolling_trends"] = rolling_trends(df)
    result["personal_baseline_anomalies"] = personal_baseline_anomalies(df)
    result["lag_correlations"] = lag_correlation(df)
    result["protocol_before_after"] = protocol_before_after(df)
    result["predictive_models"] = predictive_modeling(df)
    result["short_vs_long_term_ranges"] = short_vs_long_term_ranges(df)
    result["regime_analysis"] = regime_analysis(df)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
