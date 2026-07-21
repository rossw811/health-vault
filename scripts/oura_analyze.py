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
import sys
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

NUMERIC_FIELDS = [
    "readiness_score", "readiness_hrv_balance", "readiness_resting_hr",
    "readiness_body_temp_deviation", "readiness_recovery_index",
    "readiness_sleep_balance", "sleep_score", "sleep_total_hours",
    "sleep_efficiency", "sleep_latency_min", "sleep_rem_hours",
    "sleep_deep_hours", "sleep_light_hours", "average_hrv", "resting_hr",
    "activity_score", "steps", "calories_active", "activity_total_min",
    "inactivity_min", "spo2_avg", "training_load_hrs",
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
    return df


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
        has_tag = df["_protocols"].apply(lambda p: tag in p)
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
    for r, p_adj, sig in zip(raw_results, pvals_fdr, reject):
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
                [{"feature": f, "coef": round(float(c), 4)} for f, c in zip(feature_cols, ridge.coef_)],
                key=lambda d: -abs(d["coef"]),
            )[:8],
            "random_forest_cv_r2_mean": round(float(rf_scores.mean()), 3),
            "random_forest_top_features": sorted(
                [{"feature": f, "importance": round(float(i), 4)} for f, i in zip(feature_cols, rf.feature_importances_)],
                key=lambda d: -d["importance"],
            )[:8],
            "interpretation_note": (
                "cv_r2_mean near or below 0 means the model found no real predictive signal - "
                "report that plainly, don't just report the coefficients as if they mattered."
            ),
        }
    return out


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

    result["correlations"] = correlation_matrix(df)
    result["tag_comparisons"] = tag_group_comparisons(df)
    result["predictive_models"] = predictive_modeling(df)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
