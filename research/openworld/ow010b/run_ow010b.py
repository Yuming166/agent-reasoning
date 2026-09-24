#!/usr/bin/env python3
"""Run the frozen OW-010B blind nested temporal/structural signal test.

This runner consumes only the OW-010A aggregate feature table, a compact
pre-cutoff score composition aggregate, and the physically separate
future-outcome aggregate table. It never opens any external-label source.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "research" / "openworld" / "ow010b"
DATA = BASE / "data"
EXP = BASE / "experiments"
RESULTS = BASE / "results"

SEED = 20260918
CUTOFF_LABELS = {
    1654041600: "2022-06-01",
    1656633600: "2022-07-01",
    1659312000: "2022-08-01",
}
TRAIN_CUTOFF = "2022-06-01"
DEV_CUTOFF = "2022-07-01"
TEST_CUTOFF = "2022-08-01"
EXPECTED_HISTORY_COUNTS = {"2022-06-01": 17156, "2022-07-01": 15736, "2022-08-01": 14683}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce").astype(float)


def safe_log1p(x: pd.Series | np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    return np.log1p(np.clip(a, 0.0, None))


def safe_asinh(x: pd.Series | np.ndarray) -> np.ndarray:
    return np.arcsinh(np.asarray(x, dtype=float))


def safe_ratio(n: pd.Series | np.ndarray, d: pd.Series | np.ndarray) -> np.ndarray:
    n_a = np.asarray(n, dtype=float)
    d_a = np.asarray(d, dtype=float)
    return np.divide(n_a, d_a, out=np.full(n_a.shape, np.nan, dtype=float), where=np.isfinite(d_a) & (d_a != 0))


def smoothed_share(count: pd.Series | np.ndarray, total: pd.Series | np.ndarray, alpha: float = 0.5, categories: int = 3) -> np.ndarray:
    c = np.asarray(count, dtype=float)
    t = np.asarray(total, dtype=float)
    return (c + alpha) / (np.clip(t, 0.0, None) + alpha * categories)


def finite_or_zero(x: pd.Series | np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    return np.where(np.isfinite(a), a, 0.0)


def as_cutoff_label(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    # BigQuery REST returns TIMESTAMP values as epoch seconds in this export.
    dt = pd.to_datetime(values, unit="s", utc=True)
    return dt.dt.strftime("%Y-%m-%d")


def load_panel() -> tuple[pd.DataFrame, dict[str, Any]]:
    f = pd.read_csv(DATA / "ow010b_discovery_features.csv", low_memory=False)
    o = pd.read_csv(DATA / "ow010b_future_outcomes_evaluation_only.csv", low_memory=False)
    s = pd.read_csv(DATA / "ow010b_score7_asof_composition.csv", low_memory=False)
    for df in (f, o, s):
        df["cutoff_label"] = as_cutoff_label(df["cutoff_time"])
    keys = ["anchor_wallet", "anchor_exgraph_node_id", "cutoff_label"]
    qa: dict[str, Any] = {
        "feature_rows": int(len(f)),
        "outcome_rows": int(len(o)),
        "score_rows": int(len(s)),
        "feature_duplicate_keys": int(f.duplicated(keys).sum()),
        "outcome_duplicate_keys": int(o.duplicated(keys).sum()),
        "score_duplicate_keys": int(s.duplicated(keys).sum()),
        "feature_cutoffs": sorted(f["cutoff_label"].dropna().unique().tolist()),
        "outcome_cutoffs": sorted(o["cutoff_label"].dropna().unique().tolist()),
        "score_cutoffs": sorted(s["cutoff_label"].dropna().unique().tolist()),
        "feature_data_roles": f["data_role"].value_counts(dropna=False).to_dict(),
        "outcome_data_roles": o["data_role"].value_counts(dropna=False).to_dict(),
        "outcome_evaluation_only_false": int((o["evaluation_only"].astype(str).str.lower() != "true").sum()),
    }
    if qa["feature_duplicate_keys"] or qa["outcome_duplicate_keys"] or qa["score_duplicate_keys"]:
        raise RuntimeError(f"duplicate input keys: {qa}")
    f_key = f[keys].astype(str).apply(tuple, axis=1)
    o_key = o[keys].astype(str).apply(tuple, axis=1)
    s_key = s[keys].astype(str).apply(tuple, axis=1)
    qa["feature_outcome_key_diff"] = int(len(set(f_key) ^ set(o_key)))
    qa["history_eligible_score_key_diff"] = int(len(set(tuple(x) for x in f.loc[f.history_event_count_30d >= 1, keys].astype(str).to_numpy()) ^ set(s_key)))
    if qa["feature_outcome_key_diff"] or qa["history_eligible_score_key_diff"]:
        raise RuntimeError(f"key-set mismatch: {qa}")
    panel = f.merge(o, on=keys, how="left", suffixes=("", "_outcome"), validate="one_to_one")
    panel = panel.merge(s, on=keys, how="left", suffixes=("", "_score"), validate="one_to_one")
    # Restore a canonical numeric cutoff label and stable row id.
    panel["cutoff_label"] = panel["cutoff_label"].astype(str)
    panel["row_key"] = panel["anchor_wallet"].astype(str) + "|" + panel["cutoff_label"]
    panel["history_eligible"] = num(panel, "history_event_count_30d") >= 1
    panel["future7_complete"] = panel["future7_window_coverage_status"].astype(str).eq("OBSERVED_FULL_WINDOW")
    panel["future30_complete"] = panel["future30_window_coverage_status"].astype(str).eq("OBSERVED_FULL_WINDOW")
    for c in ["history_event_count_30d", "event_count_7d", "active_days_30d", "active_days_7d", "unique_counterparties_30d", "score_unique_counterparties_7d"]:
        if c in panel:
            panel[c] = pd.to_numeric(panel[c], errors="coerce")
    for label, expected in EXPECTED_HISTORY_COUNTS.items():
        got = int(((panel["cutoff_label"] == label) & panel["history_eligible"]).sum())
        qa[f"history_ge1_{label}"] = got
        if got != expected:
            raise RuntimeError(f"history count mismatch at {label}: got {got}, expected {expected}")
    qa["future7_complete_by_cutoff"] = panel.groupby("cutoff_label")["future7_complete"].sum().astype(int).to_dict()
    qa["future30_complete_by_cutoff"] = panel.groupby("cutoff_label")["future30_complete"].sum().astype(int).to_dict()
    qa["discovery_rows_by_cutoff"] = panel.groupby("cutoff_label")["history_eligible"].sum().astype(int).to_dict()
    # Score aggregate is history eligible only; exact count conservation is checked here.
    for c in ["score_external_native_7d", "score_token_7d", "score_internal_7d", "score_incoming_7d", "score_outgoing_7d", "score_self_7d", "score_event_count_7d"]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce")
    elig = panel["history_eligible"]
    qa["score_event_count_feature_mismatch"] = int((num(panel.loc[elig], "score_event_count_7d") != num(panel.loc[elig], "event_count_7d")).sum())
    qa["score_family_sum_mismatch"] = int((num(panel.loc[elig], "score_external_native_7d") + num(panel.loc[elig], "score_token_7d") + num(panel.loc[elig], "score_internal_7d") != num(panel.loc[elig], "score_event_count_7d")).sum())
    qa["score_direction_sum_mismatch"] = int((num(panel.loc[elig], "score_incoming_7d") + num(panel.loc[elig], "score_outgoing_7d") + num(panel.loc[elig], "score_self_7d") != num(panel.loc[elig], "score_event_count_7d")).sum())
    if any(qa[k] for k in ["score_event_count_feature_mismatch", "score_family_sum_mismatch", "score_direction_sum_mismatch"]):
        raise RuntimeError(f"score aggregate mismatch: {qa}")
    # Ensure the input role boundary is exactly the OW-010A contract.
    if set(panel.loc[panel["history_eligible"], "data_role"].astype(str)) != {"DISCOVERY_ONLY"}:
        raise RuntimeError("non-discovery feature row in eligible panel")
    if set(panel["data_role_outcome"].astype(str)) != {"EVALUATION_ONLY"}:
        raise RuntimeError("non-evaluation outcome row in panel")
    DATA_QA_RUNTIME = DATA / "data_qa_runtime.json"
    DATA_QA_RUNTIME.write_text(json.dumps(qa, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return panel, qa


def build_target(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Primary Y7. All operands are compact pre-cutoff/future aggregates only.
    score_total = num(panel, "score_event_count_7d")
    future_total = num(panel, "future7_event_count")
    y7 = pd.DataFrame(index=panel.index)
    y7["event_log_change_7d"] = safe_log1p(future_total) - safe_log1p(score_total)
    y7["counterparty_log_change_7d"] = safe_log1p(num(panel, "future7_unique_counterparties")) - safe_log1p(num(panel, "score_unique_counterparties_7d"))
    y7["active_day_change_7d"] = num(panel, "future7_active_days") - num(panel, "active_days_7d")
    y7["incoming_share_change_7d"] = smoothed_share(num(panel, "future7_incoming_events"), future_total) - smoothed_share(num(panel, "score_incoming_7d"), score_total)
    y7["outgoing_share_change_7d"] = smoothed_share(num(panel, "future7_outgoing_events"), future_total) - smoothed_share(num(panel, "score_outgoing_7d"), score_total)
    y7["native_share_change_7d"] = smoothed_share(num(panel, "future7_native_events"), future_total) - smoothed_share(num(panel, "score_external_native_7d"), score_total)
    y7["token_share_change_7d"] = smoothed_share(num(panel, "future7_token_events"), future_total) - smoothed_share(num(panel, "score_token_7d"), score_total)
    # Secondary Y30 is intentionally limited to dimensions exposed by the table.
    y30 = pd.DataFrame(index=panel.index)
    y30["event_log_change_30d"] = safe_log1p(num(panel, "future30_event_count")) - safe_log1p(num(panel, "history_event_count_30d"))
    y30["counterparty_log_change_30d"] = safe_log1p(num(panel, "future30_unique_counterparties")) - safe_log1p(num(panel, "unique_counterparties_30d"))
    y30["active_day_change_30d"] = num(panel, "future30_active_days") - num(panel, "active_days_30d")
    return y7, y30


def add_col(df: pd.DataFrame, name: str, value: Any) -> None:
    if name in df.columns:
        raise RuntimeError(f"duplicate engineered feature: {name}")
    df[name] = np.asarray(value, dtype=float)


def build_features(panel: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, list[str]]]:
    m0 = pd.DataFrame(index=panel.index)
    count_cols = [
        "history_event_count_30d", "event_count_1d", "event_count_7d", "event_count_30d",
        "active_days_7d", "active_days_30d", "active_hours_30d",
        "incoming_event_count_7d", "outgoing_event_count_7d", "self_event_count_7d",
        "incoming_event_count_30d", "outgoing_event_count_30d", "self_event_count_30d",
        "unique_counterparties_30d", "mapped_counterparties_30d", "unmapped_counterparties_30d",
        "score_unique_counterparties_7d", "native_event_count_30d", "token_event_count_30d", "internal_event_count_30d",
        "token_contract_diversity_30d", "token_item_diversity_30d",
    ]
    for c in count_cols:
        add_col(m0, f"log1p_{c}", safe_log1p(num(panel, c)))
    for c in ["native_event_ratio_30d", "token_event_ratio_30d", "internal_event_ratio_30d"]:
        add_col(m0, c, num(panel, c))
    add_col(m0, "log1p_native_inflow_30d", safe_log1p(num(panel, "native_inflow_30d").fillna(0)))
    add_col(m0, "log1p_native_outflow_30d", safe_log1p(num(panel, "native_outflow_30d").fillna(0)))
    add_col(m0, "asinh_native_netflow_30d", safe_asinh(num(panel, "native_netflow_30d").fillna(0)))
    add_col(m0, "native_amount_observed", (panel["native_amount_status"].astype(str) == "OBSERVED").astype(float))

    m1 = m0.copy()
    for c in ["inter_event_gap_mean_sec_30d", "inter_event_gap_std_sec_30d", "inter_event_gap_median_sec_30d", "inter_event_gap_min_sec_30d", "inter_event_gap_max_sec_30d"]:
        add_col(m1, f"log1p_{c}", safe_log1p(num(panel, c)))
    gap_mean = num(panel, "inter_event_gap_mean_sec_30d")
    gap_std = num(panel, "inter_event_gap_std_sec_30d")
    add_col(m1, "gap_stats_missing", ((num(panel, "history_event_count_30d") < 2) | gap_mean.isna()).astype(float))
    add_col(m1, "gap_cv", safe_ratio(gap_std, gap_mean))
    for c in ["mean_events_per_active_hour_7d", "std_events_per_active_hour_7d", "max_events_per_active_hour_7d"]:
        add_col(m1, f"log1p_{c}", safe_log1p(num(panel, c)))
    hour_mean = num(panel, "mean_events_per_active_hour_7d")
    hour_std = num(panel, "std_events_per_active_hour_7d")
    hour_max = num(panel, "max_events_per_active_hour_7d")
    add_col(m1, "hourly_cv", safe_ratio(hour_std, hour_mean))
    add_col(m1, "hourly_max_to_mean", safe_ratio(hour_max, hour_mean))
    prior_events = num(panel, "history_event_count_30d") - num(panel, "score_event_count_7d")
    prior_days = num(panel, "active_days_30d") - num(panel, "active_days_7d")
    prior_cp = num(panel, "prior_unique_counterparties_23d")
    score_cp = num(panel, "score_unique_counterparties_7d")
    add_col(m1, "prior_event_count_23d", prior_events)
    add_col(m1, "prior_active_days_23d", prior_days)
    add_col(m1, "event_log_change_score_vs_prior", safe_log1p(num(panel, "score_event_count_7d")) - safe_log1p(prior_events))
    add_col(m1, "active_day_change_score_vs_prior", num(panel, "active_days_7d") - prior_days)
    add_col(m1, "counterparty_growth_log", safe_log1p(score_cp) - safe_log1p(prior_cp))
    add_col(m1, "counterparty_new_rate", safe_ratio(num(panel, "new_counterparties_7d"), score_cp))
    add_col(m1, "counterparty_repeat_rate", safe_ratio(num(panel, "repeat_counterparties_7d"), score_cp))
    add_col(m1, "counterparty_turnover_rate", safe_ratio(num(panel, "new_counterparties_7d"), prior_cp + score_cp))
    # Exact family composition dynamics from the compact score7 aggregate.
    score_total = num(panel, "score_event_count_7d")
    prior_external = num(panel, "native_event_count_30d") - num(panel, "score_external_native_7d")
    prior_token = num(panel, "token_event_count_30d") - num(panel, "score_token_7d")
    prior_internal = num(panel, "internal_event_count_30d") - num(panel, "score_internal_7d")
    prior_total = prior_external + prior_token + prior_internal
    add_col(m1, "score_external_native_ratio", safe_ratio(num(panel, "score_external_native_7d"), score_total))
    add_col(m1, "score_token_ratio", safe_ratio(num(panel, "score_token_7d"), score_total))
    add_col(m1, "score_internal_ratio", safe_ratio(num(panel, "score_internal_7d"), score_total))
    add_col(m1, "family_external_ratio_change", smoothed_share(num(panel, "score_external_native_7d"), score_total) - smoothed_share(prior_external, prior_total))
    add_col(m1, "family_token_ratio_change", smoothed_share(num(panel, "score_token_7d"), score_total) - smoothed_share(prior_token, prior_total))
    add_col(m1, "family_internal_ratio_change", smoothed_share(num(panel, "score_internal_7d"), score_total) - smoothed_share(prior_internal, prior_total))
    prior_in = num(panel, "incoming_event_count_30d") - num(panel, "score_incoming_7d")
    prior_out = num(panel, "outgoing_event_count_30d") - num(panel, "score_outgoing_7d")
    add_col(m1, "direction_incoming_share_change", smoothed_share(num(panel, "score_incoming_7d"), score_total) - smoothed_share(prior_in, prior_total))
    add_col(m1, "direction_outgoing_share_change", smoothed_share(num(panel, "score_outgoing_7d"), score_total) - smoothed_share(prior_out, prior_total))

    m2 = m1.copy()
    cp_count = num(panel, "unique_counterparties_30d")
    entropy = num(panel, "counterparty_entropy_30d")
    add_col(m2, "counterparty_entropy_30d", entropy)
    add_col(m2, "normalized_counterparty_entropy", safe_ratio(entropy, np.log(np.maximum(cp_count, 2.0))))
    prior_recip = num(panel, "reciprocal_counterparties_prior_23d")
    full_recip = num(panel, "reciprocal_counterparties_30d")
    add_col(m2, "reciprocity_rate_prior", safe_ratio(prior_recip, prior_cp))
    add_col(m2, "reciprocity_rate_30d", safe_ratio(full_recip, cp_count))
    add_col(m2, "reciprocity_rate_change", safe_ratio(full_recip, cp_count) - safe_ratio(prior_recip, prior_cp))
    add_col(m2, "log1p_max_fan_in_counterparties_per_hour_7d", safe_log1p(num(panel, "max_fan_in_counterparties_per_hour_7d")))
    add_col(m2, "log1p_max_fan_out_counterparties_per_hour_7d", safe_log1p(num(panel, "max_fan_out_counterparties_per_hour_7d")))
    rapid = num(panel, "rapid_forwarding_adjacent_count_30d")
    add_col(m2, "log1p_rapid_forwarding_adjacent_count_30d", safe_log1p(rapid))
    add_col(m2, "rapid_forwarding_rate", safe_ratio(rapid, np.maximum(num(panel, "history_event_count_30d") - 1, 1)))
    add_col(m2, "events_per_counterparty", safe_ratio(num(panel, "history_event_count_30d"), cp_count))
    add_col(m2, "score_events_per_counterparty", safe_ratio(num(panel, "score_event_count_7d"), score_cp))

    for name, frame in [("M0", m0), ("M1", m1), ("M2_CORE", m2)]:
        if frame.columns.duplicated().any():
            raise RuntimeError(f"duplicate columns in {name}")
    cols = {"M0": list(m0.columns), "M1": list(m1.columns), "M2_CORE": list(m2.columns)}
    return {"M0": m0, "M1": m1, "M2_CORE": m2}, cols


@dataclass
class FittedScaler:
    medians: pd.Series
    means: pd.Series
    scales: pd.Series
    columns: list[str]

    @classmethod
    def fit(cls, x: pd.DataFrame) -> "FittedScaler":
        columns = list(x.columns)
        med = x[columns].median(axis=0, skipna=True).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        filled = x[columns].replace([np.inf, -np.inf], np.nan).fillna(med)
        means = filled.mean(axis=0).fillna(0.0)
        scales = filled.std(axis=0, ddof=0).replace(0.0, 1.0).fillna(1.0)
        return cls(medians=med, means=means, scales=scales, columns=columns)

    def transform(self, x: pd.DataFrame) -> np.ndarray:
        z = x[self.columns].replace([np.inf, -np.inf], np.nan)
        missing = z.isna().astype(float).to_numpy()
        z = z.fillna(self.medians)
        z = ((z - self.means) / self.scales).to_numpy(dtype=float)
        return np.concatenate([z, missing], axis=1)


@dataclass
class TargetScaler:
    means: np.ndarray
    scales: np.ndarray

    @classmethod
    def fit(cls, y: pd.DataFrame) -> "TargetScaler":
        a = y.to_numpy(dtype=float)
        means = np.nanmean(a, axis=0)
        scales = np.nanstd(a, axis=0)
        scales = np.where(np.isfinite(scales) & (scales > 0), scales, 1.0)
        return cls(means=means, scales=scales)

    def transform(self, y: pd.DataFrame) -> np.ndarray:
        return (y.to_numpy(dtype=float) - self.means) / self.scales


def loss(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean((y_true - y_pred) ** 2))


def per_dim_loss(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    return np.mean((y_true - y_pred) ** 2, axis=0)


def fit_ridge_ladder(
    ladder: str,
    bundle: dict[str, pd.DataFrame],
    y7: pd.DataFrame,
    train_idx: pd.Index,
    dev_idx: pd.Index,
    test_idx: pd.Index,
) -> dict[str, Any]:
    x = bundle[ladder]
    xtr, xdev, xtest = x.loc[train_idx], x.loc[dev_idx], x.loc[test_idx]
    ytr, ydev, ytest = y7.loc[train_idx], y7.loc[dev_idx], y7.loc[test_idx]
    pre = FittedScaler.fit(xtr)
    tscale = TargetScaler.fit(ytr)
    Xtr, Xdev = pre.transform(xtr), pre.transform(xdev)
    Ytr, Ydev = tscale.transform(ytr), tscale.transform(ydev)
    grid = [0.01, 0.1, 1.0, 10.0, 100.0]
    dev_rows = []
    fitted_by_alpha: dict[float, Ridge] = {}
    for alpha in grid:
        model = Ridge(alpha=alpha, fit_intercept=True)
        model.fit(Xtr, Ytr)
        pred = model.predict(Xdev)
        fitted_by_alpha[alpha] = model
        dev_rows.append({"alpha": alpha, "dev_loss": loss(Ydev, pred)})
    best_loss = min(r["dev_loss"] for r in dev_rows)
    tied = [r["alpha"] for r in dev_rows if r["dev_loss"] <= best_loss + 0.001]
    best_alpha = max(tied)
    best_model = fitted_by_alpha[best_alpha]
    dev_pred = best_model.predict(Xdev)
    # Final fit uses only June+July; no August target or feature statistic is used.
    fit_idx = train_idx.append(dev_idx)
    final_pre = FittedScaler.fit(x.loc[fit_idx])
    final_tscale = TargetScaler.fit(y7.loc[fit_idx])
    Xfit = final_pre.transform(x.loc[fit_idx])
    Xtest = final_pre.transform(xtest)
    Yfit = final_tscale.transform(y7.loc[fit_idx])
    Ytest = final_tscale.transform(ytest)
    final_model = Ridge(alpha=best_alpha, fit_intercept=True)
    final_model.fit(Xfit, Yfit)
    test_pred = final_model.predict(Xtest)
    return {
        "ladder": ladder,
        "model_family": "ridge",
        "alpha_grid": grid,
        "selected_alpha": best_alpha,
        "dev_tuning": dev_rows,
        "train_preprocessor": pre,
        "train_target_scaler": tscale,
        "dev_true": Ydev,
        "dev_pred": dev_pred,
        "dev_row_index": dev_idx,
        "test_true": Ytest,
        "test_pred": test_pred,
        "test_row_index": test_idx,
        "final_preprocessor": final_pre,
        "final_target_scaler": final_tscale,
        "final_model": final_model,
        "fit_row_count": int(len(fit_idx)),
    }


def fit_tree_ladder(
    ladder: str,
    bundle: dict[str, pd.DataFrame],
    y7: pd.DataFrame,
    train_idx: pd.Index,
    dev_idx: pd.Index,
    test_idx: pd.Index,
) -> dict[str, Any]:
    x = bundle[ladder]
    xtr, xdev, xtest = x.loc[train_idx], x.loc[dev_idx], x.loc[test_idx]
    ytr, ydev, ytest = y7.loc[train_idx], y7.loc[dev_idx], y7.loc[test_idx]
    pre = FittedScaler.fit(xtr)
    tscale = TargetScaler.fit(ytr)
    Xtr, Xdev = pre.transform(xtr), pre.transform(xdev)
    Ytr, Ydev = tscale.transform(ytr), tscale.transform(ydev)
    base = HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=200, max_leaf_nodes=15,
        min_samples_leaf=50, l2_regularization=1.0, random_state=SEED,
    )
    model = MultiOutputRegressor(base)
    model.fit(Xtr, Ytr)
    dev_pred = model.predict(Xdev)
    fit_idx = train_idx.append(dev_idx)
    final_pre = FittedScaler.fit(x.loc[fit_idx])
    final_tscale = TargetScaler.fit(y7.loc[fit_idx])
    Xfit = final_pre.transform(x.loc[fit_idx])
    Xtest = final_pre.transform(xtest)
    Yfit = final_tscale.transform(y7.loc[fit_idx])
    Ytest = final_tscale.transform(ytest)
    final_model = MultiOutputRegressor(HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=200, max_leaf_nodes=15,
        min_samples_leaf=50, l2_regularization=1.0, random_state=SEED,
    ))
    final_model.fit(Xfit, Yfit)
    test_pred = final_model.predict(Xtest)
    return {
        "ladder": ladder,
        "model_family": "hist_gradient_boosting",
        "selected_alpha": None,
        "dev_tuning": [{"fixed": True, "dev_loss": loss(Ydev, dev_pred)}],
        "train_preprocessor": pre,
        "train_target_scaler": tscale,
        "dev_true": Ydev,
        "dev_pred": dev_pred,
        "dev_row_index": dev_idx,
        "test_true": Ytest,
        "test_pred": test_pred,
        "test_row_index": test_idx,
        "final_preprocessor": final_pre,
        "final_target_scaler": final_tscale,
        "final_model": final_model,
        "fit_row_count": int(len(fit_idx)),
    }


def scalar_summary(y_scaled: np.ndarray, pred_scaled: np.ndarray) -> dict[str, float]:
    obs = np.sqrt(np.mean(y_scaled ** 2, axis=1))
    pred = np.sqrt(np.mean(pred_scaled ** 2, axis=1))
    mae = float(np.mean(np.abs(obs - pred)))
    mse = float(np.mean((obs - pred) ** 2))
    rho = float(spearmanr(obs, pred).statistic) if len(obs) > 2 and np.std(obs) > 0 and np.std(pred) > 0 else float("nan")
    return {"scalar_surprise_mse": mse, "scalar_surprise_mae": mae, "scalar_surprise_spearman": rho}


def bootstrap_diff(y_true: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray, wallets: pd.Series, seed: int, reps: int = 2000) -> tuple[float, float, float]:
    # Difference is loss(a) - loss(b), so positive means b improves over a.
    row_diff = np.mean((y_true - pred_a) ** 2, axis=1) - np.mean((y_true - pred_b) ** 2, axis=1)
    temp = pd.DataFrame({"wallet": wallets.astype(str).to_numpy(), "diff": row_diff})
    by_wallet = temp.groupby("wallet", sort=True)["diff"].mean().to_numpy()
    rng = np.random.default_rng(seed)
    draws = np.empty(reps, dtype=float)
    n = len(by_wallet)
    for i in range(reps):
        draws[i] = float(np.mean(by_wallet[rng.integers(0, n, size=n)]))
    return float(np.mean(row_diff)), float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        pd.DataFrame().to_csv(path, index=False)
    else:
        pd.DataFrame(rows).to_csv(path, index=False)


def activity_bin(values: pd.Series) -> pd.Series:
    v = pd.to_numeric(values, errors="coerce").fillna(0)
    return pd.cut(v, bins=[-np.inf, 0, 2, 9, 19, np.inf], labels=["0", "1-2", "3-9", "10-19", ">=20"], right=True, include_lowest=True).astype(str)


def permute_added(bundle: dict[str, pd.DataFrame], panel: pd.DataFrame, ladder: str, base_cols: list[str], seed: int) -> pd.DataFrame:
    out = bundle[ladder].copy()
    added = [c for c in out.columns if c not in base_cols]
    groups = panel["cutoff_label"].astype(str) + "|" + activity_bin(panel["history_event_count_30d"])
    rng = np.random.default_rng(seed)
    for c in added:
        for _, idx in groups.groupby(groups).groups.items():
            vals = out.loc[idx, c].to_numpy(copy=True)
            rng.shuffle(vals)
            out.loc[idx, c] = vals
    return out


def group_metric_rows(
    panel: pd.DataFrame, result_by_ladder: dict[str, dict[str, Any]], fit_idx: pd.Index, test_idx: pd.Index,
    fit_panel: pd.DataFrame, name: str, groups: pd.Series,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    test_groups = groups.loc[test_idx]
    for g in sorted(test_groups.dropna().astype(str).unique()):
        idx = test_groups.index[test_groups.astype(str) == g]
        if len(idx) == 0:
            continue
        rows_by_ladder = {}
        for ladder, r in result_by_ladder.items():
            pos = r["test_row_index"].get_indexer(idx)
            valid = pos >= 0
            yy = r["test_true"][pos[valid]]
            pp = r["test_pred"][pos[valid]]
            rows_by_ladder[ladder] = loss(yy, pp) if len(yy) else float("nan")
        out.append({
            "audit": name, "stratum": g, "n_rows": int(len(idx)),
            "m0_loss": rows_by_ladder.get("M0", float("nan")),
            "m1_loss": rows_by_ladder.get("M1", float("nan")),
            "m2_loss": rows_by_ladder.get("M2_CORE", float("nan")),
            "m1_minus_m0_improvement": rows_by_ladder.get("M0", np.nan) - rows_by_ladder.get("M1", np.nan),
            "m2_minus_m1_improvement": rows_by_ladder.get("M1", np.nan) - rows_by_ladder.get("M2_CORE", np.nan),
            "m2_minus_m0_improvement": rows_by_ladder.get("M0", np.nan) - rows_by_ladder.get("M2_CORE", np.nan),
        })
    return out


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for d in [EXP / "m0_baseline", EXP / "m1_temporal", EXP / "m2_structural", EXP / "negative_controls", EXP / "robustness"]:
        d.mkdir(parents=True, exist_ok=True)
    panel, qa = load_panel()
    y7, y30 = build_target(panel)
    bundle, col_registry = build_features(panel)
    # Primary evaluation rows: history-eligible and complete future 7d target.
    primary = panel["history_eligible"] & panel["future7_complete"] & y7.notna().all(axis=1)
    test_primary = primary & (panel["cutoff_label"] == TEST_CUTOFF)
    train_primary = primary & (panel["cutoff_label"] == TRAIN_CUTOFF)
    dev_primary = primary & (panel["cutoff_label"] == DEV_CUTOFF)
    train_idx, dev_idx, test_idx = panel.index[train_primary], panel.index[dev_primary], panel.index[test_primary]
    if min(len(train_idx), len(dev_idx), len(test_idx)) <= 0:
        raise RuntimeError(f"empty split: train={len(train_idx)}, dev={len(dev_idx)}, test={len(test_idx)}")
    qa.update({"primary_rows_by_cutoff": panel.loc[primary].groupby("cutoff_label").size().astype(int).to_dict(), "train_rows": int(len(train_idx)), "dev_rows": int(len(dev_idx)), "test_rows": int(len(test_idx)), "target_y7_finite_rows": int(y7.notna().all(axis=1).sum())})
    (DATA / "data_qa_runtime.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Freeze feature registry hash for the run.
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for ladder in ["M0", "M1", "M2_CORE"]:
        results[("ridge", ladder)] = fit_ridge_ladder(ladder, bundle, y7, train_idx, dev_idx, test_idx)
    # Secondary fixed tree model; deterministic and predeclared, not used for decisions.
    for ladder in ["M0", "M1", "M2_CORE"]:
        results[("hist_gradient_boosting", ladder)] = fit_tree_ladder(ladder, bundle, y7, train_idx, dev_idx, test_idx)

    primary_rows: list[dict[str, Any]] = []
    per_cutoff_rows: list[dict[str, Any]] = []
    pred_store: dict[tuple[str, str], pd.DataFrame] = {}
    for (family, ladder), r in results.items():
        dev_scalar = scalar_summary(r["dev_true"], r["dev_pred"])
        test_scalar = scalar_summary(r["test_true"], r["test_pred"])
        for split, true, pred, idx, scal in [("dev", r["dev_true"], r["dev_pred"], r["dev_row_index"], dev_scalar), ("test", r["test_true"], r["test_pred"], r["test_row_index"], test_scalar)]:
            primary_rows.append({
                "model_family": family, "ladder": ladder, "split": split,
                "n_rows": int(len(idx)), "n_wallets": int(panel.loc[idx, "anchor_wallet"].nunique()),
                "multivariate_standardized_mse": loss(true, pred),
                **scal, "selected_alpha": r.get("selected_alpha"),
            })
            dims = per_dim_loss(true, pred)
            for dname, dloss in zip(y7.columns, dims):
                per_cutoff_rows.append({"model_family": family, "ladder": ladder, "cutoff": DEV_CUTOFF if split == "dev" else TEST_CUTOFF, "evaluation_role": "development" if split == "dev" else "frozen_test", "n_rows": int(len(idx)), "target_dimension": dname, "mse": float(dloss), "mae": float(np.mean(np.abs(true[:, list(y7.columns).index(dname)] - pred[:, list(y7.columns).index(dname)])))})
        # Store frozen test predictions for audit and posthoc reporting.
        frame = pd.DataFrame({"anchor_wallet": panel.loc[r["test_row_index"], "anchor_wallet"].astype(str).to_numpy(), "cutoff": TEST_CUTOFF})
        for j, c in enumerate(y7.columns):
            frame[f"true_{c}"] = r["test_true"][:, j]
            frame[f"pred_{c}"] = r["test_pred"][:, j]
        frame["row_key"] = panel.loc[r["test_row_index"], "row_key"].astype(str).to_numpy()
        pred_store[(family, ladder)] = frame
        outdir = EXP / ({"M0": "m0_baseline", "M1": "m1_temporal", "M2_CORE": "m2_structural"}[ladder])
        frame.to_csv(outdir / f"{family}_test_predictions.csv", index=False)
        (outdir / f"{family}_fit_manifest.json").write_text(json.dumps({"model_family": family, "ladder": ladder, "selected_alpha": r.get("selected_alpha"), "dev_tuning": r.get("dev_tuning"), "fit_row_count": r.get("fit_row_count"), "n_test": len(r["test_row_index"])}, indent=2, sort_keys=True) + "\n")

    # Incremental gains and cluster bootstrap intervals for both preregistered model families.
    gain_rows: list[dict[str, Any]] = []
    ci_rows: list[dict[str, Any]] = []
    comparisons = [("M0", "M1", "temporal"), ("M1", "M2_CORE", "structural"), ("M0", "M2_CORE", "total")]
    for family in ["ridge", "hist_gradient_boosting"]:
        for baseline, model, contrast in comparisons:
            a = results[(family, baseline)]
            b = results[(family, model)]
            base_loss, model_loss = loss(a["test_true"], a["test_pred"]), loss(b["test_true"], b["test_pred"])
            improvement = base_loss - model_loss
            rel = improvement / base_loss if base_loss else float("nan")
            mean_diff, lo, hi = bootstrap_diff(a["test_true"], a["test_pred"], b["test_pred"], panel.loc[test_idx, "anchor_wallet"], SEED + len(ci_rows), 2000)
            ci_rows.append({"model_family": family, "contrast": contrast, "baseline": baseline, "model": model, "n_test_rows": int(len(test_idx)), "n_test_wallets": int(panel.loc[test_idx, "anchor_wallet"].nunique()), "point_improvement": mean_diff, "ci_lower": lo, "ci_upper": hi, "bootstrap_replicates": 2000, "bootstrap_unit": "anchor_wallet", "seed": SEED + len(ci_rows)})
            gain_rows.append({"model_family": family, "contrast": contrast, "baseline": baseline, "model": model, "n_test_rows": int(len(test_idx)), "baseline_loss": base_loss, "model_loss": model_loss, "improvement": improvement, "relative_improvement": rel, "ci_lower": lo, "ci_upper": hi})
    # Per-cutoff train/dev/test summary: only dev/test are inferential; June is explicitly omitted from primary metrics.
    write_csv(RESULTS / "primary_metrics.csv", primary_rows)
    write_csv(RESULTS / "incremental_gain.csv", gain_rows)
    write_csv(RESULTS / "bootstrap_intervals.csv", ci_rows)
    write_csv(RESULTS / "per_cutoff_metrics.csv", per_cutoff_rows)

    # Wallet overlap audit, with addresses used only as keys/strata.
    overlap_rows: list[dict[str, Any]] = []
    eligible_sets = {c: set(panel.loc[panel["history_eligible"] & (panel["cutoff_label"] == c), "anchor_wallet"].astype(str)) for c in [TRAIN_CUTOFF, DEV_CUTOFF, TEST_CUTOFF]}
    for a, b in [(TRAIN_CUTOFF, DEV_CUTOFF), (TRAIN_CUTOFF, TEST_CUTOFF), (DEV_CUTOFF, TEST_CUTOFF)]:
        inter = eligible_sets[a] & eligible_sets[b]
        union = eligible_sets[a] | eligible_sets[b]
        overlap_rows.append({"audit": "eligible_wallet_overlap", "left_cutoff": a, "right_cutoff": b, "left_n": len(eligible_sets[a]), "right_n": len(eligible_sets[b]), "intersection_n": len(inter), "union_n": len(union), "jaccard": len(inter) / len(union)})
    train_union = eligible_sets[TRAIN_CUTOFF] | eligible_sets[DEV_CUTOFF]
    test_wallets = set(panel.loc[test_idx, "anchor_wallet"].astype(str))
    overlap_rows.extend([
        {"audit": "test_wallet_stratum", "stratum": "repeated", "n_wallets": len(test_wallets & train_union), "definition": "August wallet with eligible June or July primary row"},
        {"audit": "test_wallet_stratum", "stratum": "unseen", "n_wallets": len(test_wallets - train_union), "definition": "August wallet with no eligible June or July primary row"},
    ])
    write_csv(RESULTS / "wallet_overlap_audit.csv", overlap_rows)

    # Activity/volume/degree confound audits on frozen ridge test predictions.
    ridge_results = {k: results[("ridge", k)] for k in ["M0", "M1", "M2_CORE"]}
    fit_panel = panel.loc[train_idx.append(dev_idx)]
    conf_rows: list[dict[str, Any]] = []
    conf_rows.extend(group_metric_rows(panel, ridge_results, train_idx.append(dev_idx), test_idx, fit_panel, "history_activity_strata", activity_bin(panel["history_event_count_30d"])))
    for col, name in [("native_inflow_30d", "native_inflow_quartile"), ("unique_counterparties_30d", "degree_quartile")]:
        vals = num(fit_panel, col).replace([np.inf, -np.inf], np.nan).fillna(0)
        qs = np.unique(np.nanquantile(vals, [0.25, 0.5, 0.75]))
        if len(qs) < 3:
            groups = pd.Series("all", index=panel.index)
        else:
            groups = pd.cut(num(panel, col).fillna(0), bins=[-np.inf, *qs.tolist(), np.inf], labels=["Q1", "Q2", "Q3", "Q4"], include_lowest=True).astype(str)
        conf_rows.extend(group_metric_rows(panel, ridge_results, train_idx.append(dev_idx), test_idx, fit_panel, name, groups))
    hist95 = float(np.nanquantile(num(fit_panel, "history_event_count_30d"), 0.95))
    tail_groups = pd.Series(np.where(num(panel, "history_event_count_30d") < hist95, "below_train_q95", "train_top5pct_or_equal"), index=panel.index)
    conf_rows.extend(group_metric_rows(panel, ridge_results, train_idx.append(dev_idx), test_idx, fit_panel, "remove_high_activity_tail", tail_groups))
    # Near-monotonicity audit: Spearman correlations on fitting rows only.
    base_cols = col_registry["M0"]
    struct_added = [c for c in col_registry["M2_CORE"] if c not in col_registry["M1"]]
    for c in struct_added:
        for b in ["log1p_history_event_count_30d", "log1p_event_count_30d", "log1p_unique_counterparties_30d", "log1p_event_count_7d"]:
            if c in bundle["M2_CORE"].columns and b in bundle["M2_CORE"].columns:
                x = bundle["M2_CORE"].loc[fit_panel.index, c].replace([np.inf, -np.inf], np.nan)
                z = bundle["M2_CORE"].loc[fit_panel.index, b].replace([np.inf, -np.inf], np.nan)
                valid = x.notna() & z.notna()
                rho = float(spearmanr(x[valid], z[valid]).statistic) if valid.sum() > 2 and x[valid].nunique() > 1 and z[valid].nunique() > 1 else float("nan")
                conf_rows.append({"audit": "structural_activity_monotonicity", "feature": c, "baseline_feature": b, "n_rows": int(valid.sum()), "spearman_rho": rho, "abs_spearman_rho": abs(rho) if np.isfinite(rho) else np.nan})
    write_csv(RESULTS / "confound_audit.csv", conf_rows)

    # Negative controls: permute incremental features within predeclared cutoff x activity bins.
    perm_bundle_m1 = dict(bundle)
    perm_bundle_m1["M1"] = permute_added(bundle, panel, "M1", col_registry["M0"], SEED + 11)
    perm_bundle_m1["M2_CORE"] = permute_added(bundle, panel, "M2_CORE", col_registry["M1"], SEED + 12)
    # M2 negative keeps M1 original, permutes only M2 additions.
    perm_results_m1 = fit_ridge_ladder("M1", perm_bundle_m1, y7, train_idx, dev_idx, test_idx)
    perm_results_m2 = fit_ridge_ladder("M2_CORE", perm_bundle_m1, y7, train_idx, dev_idx, test_idx)
    neg_rows: list[dict[str, Any]] = []
    m0 = results[("ridge", "M0")]
    for label, r, baseline_result in [("M1_permuted", perm_results_m1, m0), ("M2_added_permuted", perm_results_m2, results[("ridge", "M1")])]:
        base_loss = loss(baseline_result["test_true"], baseline_result["test_pred"])
        model_loss = loss(r["test_true"], r["test_pred"])
        diff, lo, hi = bootstrap_diff(baseline_result["test_true"], baseline_result["test_pred"], r["test_pred"], panel.loc[test_idx, "anchor_wallet"], SEED + 100 + len(neg_rows), 2000)
        neg_rows.append({"negative_control": label, "baseline": "M0" if label == "M1_permuted" else "M1", "n_test_rows": len(test_idx), "baseline_loss": base_loss, "negative_control_loss": model_loss, "improvement": base_loss - model_loss, "relative_improvement": (base_loss - model_loss) / base_loss if base_loss else np.nan, "ci_lower": lo, "ci_upper": hi, "seed": SEED + 100 + len(neg_rows)})
    write_csv(RESULTS / "negative_control_results.csv", neg_rows)

    # Machine-readable run manifest and frozen code/data hashes.
    run_manifest = {
        "experiment_id": "OW-010B",
        "run_timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": "PRIMARY_AND_SECONDARY_EXECUTED",
        "preregistration_sha256": sha_file(BASE / "preregistration" / "OW010B_PREREGISTRATION.md"),
        "feature_registry_sha256": sha_file(DATA / "FEATURE_SET_REGISTRY.json"),
        "target_spec_sha256": sha_file(DATA / "TARGET_SPECIFICATION.md"),
        "split_manifest_sha256": sha_file(DATA / "SPLIT_MANIFEST.json"),
        "score_sql_sha256": sha_file(BASE / "sql" / "score7_asof_composition.sql"),
        "input_manifest_sha256": sha_file(DATA / "BQ_INPUT_MANIFEST.json"),
        "runner_sha256": sha_file(Path(__file__)),
        "cutoffs": [TRAIN_CUTOFF, DEV_CUTOFF, TEST_CUTOFF],
        "counts": {"train": len(train_idx), "dev": len(dev_idx), "test": len(test_idx)},
        "qa": qa,
        "model_families": ["ridge", "hist_gradient_boosting"],
        "bootstrap_replicates": 2000,
        "external_label_source_accessed": False,
        "wash_label_accessed": False,
        "old_ow009_local_artifact_used": False,
        "primary_protocol_changed_after_test": False,
        "notes": ["August is one held-out temporal cutoff; July is development, not an independent test.", "No matching, GNN, or latent-strategy track was run."],
    }
    (RESULTS / "RUN_MANIFEST.json").write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    # Save a compact model-selection log without raw source event data.
    selection = []
    for (family, ladder), r in results.items():
        selection.append({"model_family": family, "ladder": ladder, "selected_alpha": r.get("selected_alpha"), "dev_tuning": r.get("dev_tuning"), "fit_row_count": r.get("fit_row_count")})
    (RESULTS / "model_selection_log.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "train": len(train_idx), "dev": len(dev_idx), "test": len(test_idx), "results": str(RESULTS)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
