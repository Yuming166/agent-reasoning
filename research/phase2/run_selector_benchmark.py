#!/usr/bin/env python3
"""Run the Phase II-A selector tournament, matched-budget statistics, audits, and figures.

This script is intentionally self-contained and CPU-only. It reads the frozen Phase-I/Phase-II
artifacts and writes only below research/phase2/. It never calls an LLM endpoint.

Temporal protocol:
  June 2022: selector training/development
  July 2022: tuning (hybrid weights only; K=100 was frozen as the primary tuning budget)
  August 2022: frozen primary test
  September 2022: independent holdout, using exactly the selector frozen after July

Important boundary:
  ``dyn_influence_*`` in the event table is future-derived and is never used as an input.
  A dynamic-influence selector is a pre-reasoning prediction of I_new_hist trained on prior
  cutoff rows from dynamic_influence_dataset.parquet. The full-window EX-Graph structural
  table is a context-only/leaky static prior baseline, never a primary as-of feature.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from scipy.stats import spearmanr, pearsonr

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[2]))
P2 = ROOT / "research" / "phase2"
OUTDIR = P2 / "selector_results"
FIGDIR = P2 / "figures"
OUTDIR.mkdir(parents=True, exist_ok=True)
FIGDIR.mkdir(parents=True, exist_ok=True)

SEED = 42
BOOTSTRAPS = 2000
K_VALUES = [10, 25, 50, 100, 250, 500, 1000]
TRAIN_DATE = pd.Timestamp("2022-06-01").date()
TUNE_DATE = pd.Timestamp("2022-07-01").date()
TEST_DATE = pd.Timestamp("2022-08-01").date()
HOLDOUT_DATE = pd.Timestamp("2022-09-01").date()
DATE_ORDER = [TRAIN_DATE, TUNE_DATE, TEST_DATE, HOLDOUT_DATE]
DATE_LABEL = {
    TRAIN_DATE: "train_dev_jun",
    TUNE_DATE: "tune_jul",
    TEST_DATE: "test_aug",
    HOLDOUT_DATE: "holdout_sep",
}
EVENT_KEY = ["snapshot_date", "target_address", "target_sequence_index"]
ID_COLS = set(EVENT_KEY + ["event_id", "wallet_id", "target_exgraph_node_id", "model", "split"])

# The event-level panel contains both pre-call information and evaluation-only fields. The
# forbidden list is deliberately conservative: anything whose name or source can contain the
# future target, an LLM answer, or a legacy gain is not offered to a primary selector.
FORBIDDEN_EXACT = {
    "truth_in_pool", "cheap_rr", "full_rr", "nocf_rr", "cheap_rank", "obs_rank", "mask_rank",
    "full_rank", "cheap_correct", "fullcf_correct", "fullcf_prediction", "fullcf_score",
    "full_pick_matches_truth_proxy", "rv_mrr", "rv_nocf", "rv_ll", "rv_ll_available",
    "reasoning_gain", "reasoning_gain_type", "z0", "z1", "rv_cost_lambda1", "rv_cost_tokens_only",
    "future_target", "truth_cheap_score", "truth_cand_source", "counterparty_days_since",
    "counterparty_g_rank", "counterparty_truth_g_rank", "future_spillover_new_cp_30d",
    "future_spillover_evt_cnt_30d", "future_spillover_cp_distinct_30d", "future_spillover_horizon_days",
    "dyn_influence_new_cp_histgbm", "dyn_influence_new_cp_logistic", "dyn_influence_evt_hist_histgbm",
    "dyn_influence_evt_histgbm", "dyn_influence_mean", "dyn_resid_new_histgbm", "dyn_resid_new_logistic",
    "dyn_resid_evt_histgbm", "dyn_influence_uses_future", "legacy_gain_full_router", "legacy_gain_nocf_router",
    "legacy_full_wins_router", "target_is_x_matched", "importance_proxy_p3", "in_mm_subgraph",
    "regime_change_score", "full_parse_ok", "nocf_parse_ok", "parse_success", "fallback_used",
    "reasoning_tokens", "reasoning_latency", "total_tokens", "nocf_total_tokens", "latency_s",
    # These fields are present in the joined panel but are not legal pre-reasoning inputs.
    "nocf_rank", "llm_calls", "prompt_tokens", "completion_tokens", "mask_sensitive",
    "counterparty_novelty", "counterparty_recency", "cheap_score",
}
FORBIDDEN_PREFIXES = (
    "audit_", "future_", "fwd30", "dyn_", "legacy_", "fullcf_", "rv_", "z0", "z1",
)
FORBIDDEN_SUBSTRINGS = ("truth", "counterparty_truth", "future_target")

# These are available before the expensive Full-CF call according to the Phase-I router contract.
# cp_type_repeat is retained because it is explicitly in router_dataset_v2's pre-call schema;
# the duplicate truth-side counterparty_novelty is excluded by the conservative filter.
ROUTER_PRECALL = {
    "cp_type_repeat", "evt_cnt_90d", "cp_entropy_90d", "cp_new_rate_30d", "pool_n",
    "cheap_top_score", "cheap_margin", "cheap_score_entropy", "frac_bridge", "frac_personal",
    "frac_tail", "frac_top2000", "n_bridge", "n_personal", "top1_is_personal", "top1_is_bridge",
    "pop_weight", "log_evt_cnt", "log_pool_n", "log_n_bridge", "log_n_personal", "cheap_pred_score",
    "cheap_pred_days_since", "cheap_pred_g_rank",
}

BEHAVIOR_FEATURES = [
    "wallet_activity", "wallet_volume", "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
    "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d", "active_span_days_90d",
    "cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d", "cp_out_interact_90d",
    "cp_in_interact_90d", "token_distinct_90d", "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d",
    "cp_both_dir_90d", "cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d", "token_hhi_90d",
    "events_per_active_day_90d", "behavioral_surprise",
]
GRAPH_FEATURES = [
    c for c in [
        "asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree", "asof_mm_w_in_degree",
        "asof_mm_w_out_degree", "asof_mm_pagerank", "asof_mm_kcore", "asof_mm_clustering",
        "asof_mm_hub_neighbors", "degree_asof", "weighted_degree_asof", "pagerank_asof", "kcore_asof",
        "comm_community_size", "comm_within_comm_wdeg", "comm_cross_comm_wdeg", "comm_cross_comm_share",
        "comm_within_comm_deg", "comm_cross_comm_deg", "comm_bridge_score", "comm_hub_score",
        "comm_betweenness",
    ]
]
NOVELTY_FEATURES = [
    "cp_type_repeat", "cheap_pred_days_since", "cheap_pred_g_rank", "cp_new_rate_30d", "cp_new_30d",
    "frac_tail", "frac_bridge", "n_bridge", "n_personal", "top1_is_bridge", "top1_is_personal",
]
UNCERTAINTY_FEATURES = [
    "cheap_top_score", "cheap_margin", "cheap_score_entropy", "pool_n", "log_pool_n", "cheap_pred_score",
]

# Dynamic influence model features are limited to strictly as-of wallet/network/trajectory fields.
DI_BASE_FEATURES = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d", "evt_native_90d", "evt_token_90d",
    "active_days_90d", "tx_cnt_90d", "active_span_days_90d", "cp_distinct_90d", "cp_out_distinct_90d",
    "cp_in_distinct_90d", "cp_out_interact_90d", "cp_in_interact_90d", "token_distinct_90d",
    "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d", "cp_reciprocity_90d",
    "self_tx_rate_90d", "token_event_rate_90d", "token_hhi_90d", "events_per_active_day_90d",
    "n_events_90d_traj", "active_days_90d_traj", "active_span_days_90d_traj", "first_event_offset_days",
    "last_event_recency_days", "mean_gap_days", "median_gap_days", "max_gap_days", "std_gap_days",
    "n_gaps_gt7d", "n_gaps", "out_interact_90d", "in_interact_90d", "native_90d", "token_90d",
    "native_usd", "token_usd_priced", "token_rows", "token_rows_priced", "asof_mm_in_degree",
    "asof_mm_out_degree", "asof_mm_undir_degree", "asof_mm_w_in_degree", "asof_mm_w_out_degree",
    "asof_mm_pagerank", "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors", "log_vol",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, (pd.Series,)):
        return obj.to_dict()
    if isinstance(obj, (pd.DataFrame,)):
        return obj.to_dict(orient="records")
    if isinstance(obj, (Path,)):
        return str(obj)
    raise TypeError(type(obj).__name__)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=json_default) + "\n")


def valid_numeric_columns(df: pd.DataFrame, candidates: Sequence[str], train: pd.DataFrame | None = None) -> List[str]:
    out = []
    for c in candidates:
        if c not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if c in ID_COLS or c in FORBIDDEN_EXACT:
            continue
        cl = c.lower()
        if any(cl.startswith(p) for p in FORBIDDEN_PREFIXES):
            continue
        if any(s in cl for s in FORBIDDEN_SUBSTRINGS):
            continue
        if train is not None and not pd.to_numeric(train[c], errors="coerce").notna().any():
            continue
        out.append(c)
    return out


def is_forbidden(c: str) -> bool:
    cl = c.lower()
    return c in ID_COLS or c in FORBIDDEN_EXACT or any(cl.startswith(p) for p in FORBIDDEN_PREFIXES) or any(s in cl for s in FORBIDDEN_SUBSTRINGS)


def load_inputs() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rg = pd.read_parquet(P2 / "reasoning_gain_dataset.parquet")
    di = pd.read_parquet(P2 / "dynamic_influence_dataset.parquet")
    rg["snapshot_date"] = pd.to_datetime(rg["snapshot_date"]).dt.date
    di["snapshot_date"] = pd.to_datetime(di["snapshot_date"]).dt.date
    static = pd.read_csv(ROOT / "artifacts/exgraph_structural_features.csv")
    static = static.rename(columns={"ethereum_address": "target_address", "degree": "static_prior_degree",
                                    "w_degree": "static_prior_w_degree", "pagerank": "static_prior_pagerank"})
    static = static[["target_address", "static_prior_degree", "static_prior_w_degree", "static_prior_pagerank"]]
    rg = rg.merge(static, on="target_address", how="left", validate="many_to_one")
    rg["rv_mrr"] = pd.to_numeric(rg["rv_mrr"], errors="coerce")
    rg["wallet_volume"] = pd.to_numeric(rg["wallet_volume"], errors="coerce")
    rg["wallet_activity"] = pd.to_numeric(rg["wallet_activity"], errors="coerce")
    if rg["rv_mrr"].isna().any():
        raise RuntimeError("reasoning_gain_dataset contains NaN rv_mrr")
    return rg, di, static


def make_model(kind: str = "histgb"):
    if kind == "ridge":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ])
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.05, max_leaf_nodes=15,
            min_samples_leaf=30, l2_regularization=1.0, random_state=SEED,
        )),
    ])


def fit_predict(train: pd.DataFrame, score_df: pd.DataFrame, features: Sequence[str], target: str,
                model_kind: str = "histgb") -> Tuple[np.ndarray, object, List[str]]:
    features = valid_numeric_columns(train, features, train=train)
    if not features:
        return np.zeros(len(score_df), dtype=float), None, []
    xtr = train[features].replace([np.inf, -np.inf], np.nan)
    ytr = pd.to_numeric(train[target], errors="coerce")
    ok = ytr.notna()
    xtr, ytr = xtr.loc[ok], ytr.loc[ok]
    if len(xtr) < 20:
        return np.zeros(len(score_df), dtype=float), None, features
    model = make_model(model_kind)
    model.fit(xtr, ytr)
    xs = score_df[features].replace([np.inf, -np.inf], np.nan)
    pred = np.asarray(model.predict(xs), dtype=float)
    pred[~np.isfinite(pred)] = float(np.nanmedian(pred[np.isfinite(pred)]) if np.isfinite(pred).any() else 0.0)
    return pred, model, features


def rank_pct(s: pd.Series, ascending: bool = True) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    r = x.rank(method="average", ascending=ascending, na_option="bottom", pct=True)
    return r.fillna(0.0).astype(float)


def normalize_component(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    return x.groupby(pd.Series(np.zeros(len(x)), index=x.index)).transform(lambda z: rank_pct(z))


def per_cutoff_rank(df: pd.DataFrame, col: str, ascending: bool = True) -> pd.Series:
    return df.groupby("snapshot_date", group_keys=False)[col].apply(lambda s: rank_pct(s, ascending=ascending)).reset_index(level=0, drop=True).reindex(df.index)


def ndcg_at_k(relevance: np.ndarray, score: np.ndarray, k: int) -> float:
    rel = np.maximum(np.asarray(relevance, dtype=float), 0.0)
    n = len(rel)
    k = min(k, n)
    if k <= 0:
        return 0.0
    order = np.lexsort((np.arange(n), -np.asarray(score, dtype=float)))
    ideal = np.lexsort((np.arange(n), -rel))
    gains = (2.0 ** rel - 1.0)
    disc = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(gains[order[:k]] * disc))
    idcg = float(np.sum(gains[ideal[:k]] * disc))
    return dcg / idcg if idcg > 0 else 0.0


def top_k_mask(score: pd.Series, k: int, event_ids: pd.Series) -> np.ndarray:
    n = len(score)
    if k <= 0:
        return np.zeros(n, dtype=bool)
    x = pd.DataFrame({"score": pd.to_numeric(score, errors="coerce").fillna(-np.inf).to_numpy(),
                      "event_id": event_ids.astype(str).to_numpy(),
                      "row": np.arange(n)})
    x = x.sort_values(["score", "event_id"], ascending=[False, True], kind="mergesort")
    m = np.zeros(n, dtype=bool)
    m[x.head(min(k, n))["row"].to_numpy()] = True
    return m


def tune_hybrid_weights(tune: pd.DataFrame, components: Sequence[str], k: int = 100) -> Tuple[Dict[str, float], pd.DataFrame]:
    # Grid on simplex with 0.25 increments. This is the only score tuning operation and is
    # performed on July only, before the August and September frozen evaluations.
    comps = list(components)
    rows = []
    best = None
    n = len(comps)
    for vals in itertools.product([0.0, 0.25, 0.5, 0.75, 1.0], repeat=n):
        if abs(sum(vals) - 1.0) > 1e-9:
            continue
        score = sum(v * pd.to_numeric(tune[c], errors="coerce").fillna(0.0) for c, v in zip(comps, vals))
        mask = top_k_mask(score, k, tune["event_id"])
        rv = tune.loc[mask, "rv_mrr"].mean() if mask.any() else 0.0
        inc = float(tune.loc[mask, "rv_mrr"].sum()) / len(tune)
        npos = float(tune.loc[mask, "z0"].mean()) if mask.any() else 0.0
        row = {**{f"w_{c}": v for c, v in zip(comps, vals)}, "k": k,
               "selected_rv_mean": float(rv), "incremental_mrr": inc, "positive_rate": npos}
        rows.append(row)
        key = (inc, rv, -sum(v > 0 for v in vals), tuple(-v for v in vals))
        if best is None or key > best[0]:
            best = (key, dict(zip(comps, vals)))
    grid = pd.DataFrame(rows).sort_values(["incremental_mrr", "selected_rv_mean"], ascending=False).reset_index(drop=True)
    return best[1], grid


def build_scores(rg: pd.DataFrame, di: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object], Dict[str, object]]:
    df = rg.copy().sort_values(EVENT_KEY).reset_index(drop=True)
    df["event_id"] = df["event_id"].astype(str)
    # Primary as-of feature contract. Do not infer this from every numeric column in the
    # joined panel: the panel intentionally contains post-call ranks, LLM usage counters,
    # truth-side metadata, and evaluation labels. The direct RV predictor is restricted to
    # the explicitly audited as-of/pre-call groups below.
    primary_candidates = []
    for group in [BEHAVIOR_FEATURES, GRAPH_FEATURES, NOVELTY_FEATURES,
                  UNCERTAINTY_FEATURES, sorted(ROUTER_PRECALL)]:
        for c in group:
            if c not in primary_candidates:
                primary_candidates.append(c)
    all_safe = [c for c in primary_candidates
                if c in df.columns and pd.api.types.is_numeric_dtype(df[c]) and not is_forbidden(c)]
    group_features = {
        "behavior": [c for c in BEHAVIOR_FEATURES if c in all_safe],
        "graph": [c for c in GRAPH_FEATURES if c in all_safe],
        "novelty_model": [c for c in NOVELTY_FEATURES if c in all_safe],
        "uncertainty_model": [c for c in UNCERTAINTY_FEATURES if c in all_safe],
        "hybrid_model": all_safe,
    }
    # A subset of safe pre-call columns is retained in the manifest for auditability.
    group_features["router_precall"] = [c for c in ROUTER_PRECALL if c in all_safe]

    scores = df[EVENT_KEY + ["event_id", "wallet_id", "stratum", "rv_mrr", "cheap_rr", "full_rr", "z0", "z1",
                             "total_tokens", "latency_s", "wallet_volume", "wallet_activity",
                             "static_prior_degree", "static_prior_w_degree", "static_prior_pagerank"]].copy()
    # Baselines with an explicit direction (high score = spend reasoning).
    scores["volume"] = np.log1p(pd.to_numeric(df["wallet_volume"], errors="coerce"))
    scores["activity"] = np.log1p(pd.to_numeric(df["wallet_activity"], errors="coerce"))
    scores["repeat"] = pd.to_numeric(df["cp_type_repeat"], errors="coerce")
    scores["novelty"] = 1.0 - scores["repeat"].fillna(0.0)
    scores["cheap_uncertainty"] = rank_pct(df["cheap_score_entropy"]) + rank_pct(df["cheap_margin"], ascending=False)
    scores["dynamic_degree"] = pd.to_numeric(df.get("asof_mm_undir_degree", np.nan), errors="coerce")
    scores["dynamic_wdegree"] = pd.to_numeric(df.get("weighted_degree_asof", np.nan), errors="coerce")
    scores["static_degree"] = scores["static_prior_degree"]
    scores["static_w_degree"] = scores["static_prior_w_degree"]
    scores["static_pagerank"] = scores["static_prior_pagerank"]
    scores["random_expected"] = 0.0

    # July scores from June training; final frozen scores from June+July. The same final model
    # is applied to both August and September (no August refit).
    june = df[df["snapshot_date"] == TRAIN_DATE]
    july = df[df["snapshot_date"] == TUNE_DATE]
    pre_final = df[df["snapshot_date"].isin([TRAIN_DATE, TUNE_DATE])]
    tune_idx = df.index[df["snapshot_date"] == TUNE_DATE]
    eval_idx = df.index[df["snapshot_date"].isin([TEST_DATE, HOLDOUT_DATE])]
    model_meta = {"groups": {k: list(v) for k, v in group_features.items()}, "model_kind": "histgb"}

    # Component RV predictors.
    component_names = ["rv_pred", "di_pred", "behavior_pred", "uncertainty_pred", "novelty_pred"]
    # July: models fit on June only.
    for name, feats in [("behavior_pred", group_features["behavior"]),
                        ("uncertainty_pred", group_features["uncertainty_model"]),
                        ("novelty_pred", group_features["novelty_model"]),
                        ("rv_pred", group_features["hybrid_model"])]:
        pred, model, used = fit_predict(june, july, feats, "rv_mrr")
        scores.loc[tune_idx, name] = pred
        model_meta[f"july_{name}"] = {"features": used, "n_train": len(june), "model": "histgb"}
    # Dynamic-influence predictor: train only on prior DI cutoffs (June for July).
    di_feats = [c for c in DI_BASE_FEATURES if c in di.columns and c in df.columns]
    di_june = di[di["snapshot_date"] < TUNE_DATE].copy()
    di_july_events = df[df["snapshot_date"] == TUNE_DATE].merge(
        di[["snapshot_date", "target_address"] + [c for c in di_feats if c in di.columns]],
        on=["snapshot_date", "target_address"], how="left")
    # The event table already contains most DI features. When a feature is only present in the
    # wallet-cutoff table, the merge above supplies it; keep the frame safe for the shared fitter.
    for c in di_feats:
        if c not in di_july_events.columns and c in df.columns:
            di_july_events[c] = df.loc[df["snapshot_date"] == TUNE_DATE, c].to_numpy()
    # Use the DI table's feature rows to train; apply by merge to event rows.
    di_train = di[di["snapshot_date"] < TUNE_DATE].copy()
    di_score = di_july_events.copy()
    if len(di_train) and "I_new_hist" in di_train:
        di_pred, di_model, used_di = fit_predict(di_train, di_score, di_feats, "I_new_hist")
    else:
        di_pred, di_model, used_di = np.zeros(len(di_score)), None, di_feats
    scores.loc[tune_idx, "di_pred"] = di_pred
    model_meta["july_di_pred"] = {"features": used_di, "n_train": len(di_train), "target": "I_new_hist", "model": "histgb"}

    # Convert component predictions to within-cutoff percentile scores before tuning.
    for c in component_names:
        scores[c] = scores[c].astype(float)
        m = scores.index.isin(tune_idx)
        scores.loc[m, c] = rank_pct(scores.loc[m, c])
    # Use a separate per-cutoff rank for hand-built uncertainty/novelty components.
    scores.loc[tune_idx, "uncertainty_pred"] = rank_pct(scores.loc[tune_idx, "uncertainty_pred"])
    scores.loc[tune_idx, "novelty_pred"] = rank_pct(scores.loc[tune_idx, "novelty_pred"])
    hybrid_components = ["rv_pred", "di_pred", "behavior_pred", "uncertainty_pred", "novelty_pred"]
    w, grid = tune_hybrid_weights(scores.loc[tune_idx].copy(), hybrid_components, k=100)
    grid.insert(0, "experiment_id", "SEL_BENCH_001")
    grid.to_csv(OUTDIR / "hybrid_tuning_grid.csv", index=False)
    scores.loc[tune_idx, "hybrid"] = sum(w[c] * scores.loc[tune_idx, c].fillna(0.0) for c in hybrid_components)
    scores.loc[tune_idx, "reasoning_value"] = scores.loc[tune_idx, "rv_pred"]
    scores.loc[tune_idx, "dynamic_influence"] = scores.loc[tune_idx, "di_pred"]
    scores.loc[tune_idx, "behavior"] = scores.loc[tune_idx, "behavior_pred"]
    scores.loc[tune_idx, "uncertainty"] = scores.loc[tune_idx, "uncertainty_pred"]

    # Final frozen models fit on June+July and applied to both August and September.
    for name, feats in [("behavior_pred", group_features["behavior"]),
                        ("uncertainty_pred", group_features["uncertainty_model"]),
                        ("novelty_pred", group_features["novelty_model"]),
                        ("rv_pred", group_features["hybrid_model"])]:
        pred, model, used = fit_predict(pre_final, df.loc[eval_idx], feats, "rv_mrr")
        scores.loc[eval_idx, name] = pred
        model_meta[f"frozen_{name}"] = {"features": used, "n_train": len(pre_final), "model": "histgb",
                                          "train_dates": [str(TRAIN_DATE), str(TUNE_DATE)]}
    di_train_final = di[di["snapshot_date"].isin([TRAIN_DATE, TUNE_DATE])].copy()
    # Apply to RG eval rows through the event->wallet/cutoff join.
    eval_events = df.loc[eval_idx, EVENT_KEY].copy()
    di_eval = eval_events.merge(di[["snapshot_date", "target_address"] + [c for c in di_feats if c in di.columns]],
                                on=["snapshot_date", "target_address"], how="left")
    for c in di_feats:
        if c not in di_eval.columns and c in df.columns:
            di_eval[c] = df.loc[df.index.isin(eval_idx), c].to_numpy()
    di_pred_final, di_model_final, used_di_final = fit_predict(di_train_final, di_eval, di_feats, "I_new_hist")
    scores.loc[eval_idx, "di_pred"] = di_pred_final
    model_meta["frozen_di_pred"] = {"features": used_di_final, "n_train": len(di_train_final), "target": "I_new_hist",
                                     "model": "histgb", "train_dates": [str(TRAIN_DATE), str(TUNE_DATE)]}
    for c in component_names:
        # Percentile within each evaluation cutoff, as frozen scoring transformation.
        for d in [TEST_DATE, HOLDOUT_DATE]:
            idx = scores.index[scores["snapshot_date"] == d]
            scores.loc[idx, c] = rank_pct(scores.loc[idx, c])
    for d in [TEST_DATE, HOLDOUT_DATE]:
        idx = scores.index[scores["snapshot_date"] == d]
        scores.loc[idx, "uncertainty_pred"] = rank_pct(scores.loc[idx, "uncertainty_pred"])
        scores.loc[idx, "novelty_pred"] = rank_pct(scores.loc[idx, "novelty_pred"])
        scores.loc[idx, "hybrid"] = sum(w[c] * scores.loc[idx, c].fillna(0.0) for c in hybrid_components)
        scores.loc[idx, "reasoning_value"] = scores.loc[idx, "rv_pred"]
        scores.loc[idx, "dynamic_influence"] = scores.loc[idx, "di_pred"]
        scores.loc[idx, "behavior"] = scores.loc[idx, "behavior_pred"]
        scores.loc[idx, "uncertainty"] = scores.loc[idx, "uncertainty_pred"]

    # All rows need baseline rank scores for the benchmark. Rank each score within cutoff.
    baseline_names = ["random_expected", "volume", "activity", "repeat", "novelty", "cheap_uncertainty",
                      "dynamic_degree", "dynamic_wdegree", "static_degree", "static_w_degree", "static_pagerank"]
    for c in baseline_names:
        # Cast hand-built integer components (e.g. repeat) before percentile assignment.
        scores[c] = pd.to_numeric(scores[c], errors="coerce").astype(float)
        for d in DATE_ORDER:
            idx = scores.index[scores["snapshot_date"] == d]
            if c == "random_expected":
                scores.loc[idx, c] = 0.0
            else:
                scores.loc[idx, c] = rank_pct(scores.loc[idx, c])
    scores["no_selection"] = 0.0
    # The oracle is explicitly evaluation-only.
    scores["oracle"] = scores["rv_mrr"]
    scores["all_full"] = 1.0
    scores["split"] = scores["snapshot_date"].map(DATE_LABEL)
    model_meta["hybrid_weights"] = w
    model_meta["primary_tuning_budget_k"] = 100
    model_meta["frozen_train_dates"] = [str(TRAIN_DATE), str(TUNE_DATE)]
    model_meta["static_prior_note"] = "static_prior_* comes from full-window EX-Graph graph and is context-only/leaky, never primary as-of feature"
    model_meta["feature_contract"] = (
        "explicit union of audited as-of behavior/graph/novelty/uncertainty/router-precall "
        "features; excludes post-call LLM/evaluation/truth/cost fields and full-window priors"
    )
    model_meta["primary_feature_candidates"] = all_safe
    model_meta["experiment_id"] = "SEL_BENCH_001"
    scores_export = scores.copy()
    scores_export.insert(0, "experiment_id", "SEL_BENCH_001")
    scores_export.to_parquet(OUTDIR / "selector_scores.parquet", index=False)
    write_json(OUTDIR / "selector_model_manifest.json", model_meta)
    return df, scores, model_meta


def selector_names() -> List[str]:
    return ["no_selection", "random", "volume", "activity", "repeat", "novelty", "cheap_uncertainty",
            "dynamic_degree", "dynamic_wdegree", "static_degree", "static_w_degree", "static_pagerank",
            "behavior", "dynamic_influence", "reasoning_value", "hybrid", "oracle", "all_full"]


def evaluate_selector_table(df: pd.DataFrame, scores: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[Tuple[str, object, int], np.ndarray]]:
    rows = []
    masks: Dict[Tuple[str, object, int], np.ndarray] = {}
    n_by_date = df.groupby("snapshot_date").size().to_dict()
    for d in [TUNE_DATE, TEST_DATE, HOLDOUT_DATE]:
        base = scores[scores["snapshot_date"] == d].copy().reset_index(drop=True)
        n = len(base)
        if n == 0:
            continue
        for selector in selector_names():
            for k in K_VALUES:
                if selector == "no_selection":
                    mask = np.zeros(n, dtype=bool)
                elif selector == "random":
                    # Expected uniform random allocation. A separate seed-spread file below checks
                    # the finite-random-draw variation; this point is exact for the random policy.
                    mask = np.zeros(n, dtype=bool)
                elif selector == "all_full":
                    # All-Full-CF is a separate upper-cost reference, not an exact-K
                    # selector. Keep it fully selected at every displayed K so its utility
                    # and measured total cost are reported honestly; do not use it in the
                    # matched-K primary comparisons.
                    mask = np.ones(n, dtype=bool)
                else:
                    mask = top_k_mask(base[selector], k, base["event_id"])
                masks[(selector, d, k)] = mask
                rv = base["rv_mrr"].to_numpy(float)
                cheap = base["cheap_rr"].to_numpy(float) if "cheap_rr" in base else (df.loc[df["snapshot_date"] == d, "cheap_rr"].to_numpy(float))
                full = base["full_rr"].to_numpy(float) if "full_rr" in base else (df.loc[df["snapshot_date"] == d, "full_rr"].to_numpy(float))
                tok = base["total_tokens"].to_numpy(float)
                lat = base["latency_s"].to_numpy(float)
                if selector == "random":
                    sel_frac = min(k, n) / n
                    inc_sum = float(rv.sum() * sel_frac)
                    selected_rv_mean = float(rv.mean())
                    selected_z0 = float(base["z0"].mean())
                    selected_z1 = float(base["z1"].mean())
                    budget_tokens = float(tok.mean() * min(k, n))
                    budget_lat = float(lat.mean() * min(k, n))
                    ndcg = ndcg_at_k(rv, np.zeros(n), k)  # expected random NDCG is descriptive only
                    recall = float(min(k, n) / n)
                    selected_vol = float(pd.to_numeric(base["wallet_volume"], errors="coerce").mean())
                    selected_act = float(pd.to_numeric(base["wallet_activity"], errors="coerce").mean())
                    selected_count = min(k, n)
                elif selector == "no_selection":
                    inc_sum = 0.0
                    selected_rv_mean = float("nan")
                    selected_z0 = float("nan")
                    selected_z1 = float("nan")
                    budget_tokens = 0.0
                    budget_lat = 0.0
                    ndcg = 0.0
                    recall = 0.0
                    selected_vol = float("nan")
                    selected_act = float("nan")
                    selected_count = 0
                else:
                    inc_sum = float(rv[mask].sum())
                    selected_rv_mean = float(rv[mask].mean()) if mask.any() else float("nan")
                    selected_z0 = float(base.loc[mask, "z0"].mean()) if mask.any() else float("nan")
                    selected_z1 = float(base.loc[mask, "z1"].mean()) if mask.any() else float("nan")
                    budget_tokens = float(tok[mask].sum())
                    budget_lat = float(lat[mask].sum())
                    ndcg = ndcg_at_k(rv, base[selector].to_numpy(float), k) if selector not in {"no_selection"} else 0.0
                    oracle_mask = top_k_mask(base["rv_mrr"], min(k, n), base["event_id"])
                    recall = float(np.logical_and(mask, oracle_mask).sum() / max(1, oracle_mask.sum())) if mask.any() else 0.0
                    selected_vol = float(pd.to_numeric(base.loc[mask, "wallet_volume"], errors="coerce").mean()) if mask.any() else float("nan")
                    selected_act = float(pd.to_numeric(base.loc[mask, "wallet_activity"], errors="coerce").mean()) if mask.any() else float("nan")
                    selected_count = int(mask.sum())
                cheap_mean = float(np.nanmean(cheap))
                full_mean = float(np.nanmean(full))
                utility = cheap_mean + inc_sum / n
                cost_rate = inc_sum / budget_tokens * 1000.0 if budget_tokens > 0 else float("nan")
                sec_rate = inc_sum / budget_lat if budget_lat > 0 else float("nan")
                score = base[selector].to_numpy(float) if selector in base else np.zeros(n)
                sv = pd.to_numeric(base["wallet_volume"], errors="coerce").to_numpy(float)
                ok = np.isfinite(score) & np.isfinite(sv)
                score_unique = np.unique(score[ok]).size if ok.any() else 0
                vol_unique = np.unique(sv[ok]).size if ok.any() else 0
                corr = float(spearmanr(score[ok], sv[ok]).statistic) if ok.sum() >= 3 and score_unique > 1 and vol_unique > 1 else float("nan")
                rows.append({
                    "experiment_id": "SEL_BENCH_001", "selector": selector, "date": str(d),
                    "split": DATE_LABEL[d], "K": int(k), "n_events": int(n), "selected_n": int(selected_count),
                    "coverage": float(selected_count / n), "cheap_mrr": cheap_mean, "full_mrr_all": full_mean,
                    "utility_mrr": utility, "incremental_mrr": inc_sum / n, "incremental_sum_mrr": inc_sum,
                    "selected_rv_mean": selected_rv_mean, "selected_z0_rate": selected_z0, "selected_z1_rate": selected_z1,
                    "ndcg_at_k": float(ndcg), "oracle_recall_at_k": recall, "budget_tokens": budget_tokens,
                    "budget_latency_s": budget_lat, "incremental_per_1k_tokens": cost_rate,
                    "incremental_per_second": sec_rate, "selected_volume_mean": selected_vol,
                    "selected_activity_mean": selected_act, "score_volume_spearman": corr,
                    "measured_full_tokens_mean": float(tok.mean()), "measured_full_latency_mean": float(lat.mean()),
                })
    bench = pd.DataFrame(rows)
    bench.to_csv(P2 / "selector_benchmark.csv", index=False)
    bench.to_csv(OUTDIR / "selector_benchmark_long.csv", index=False)
    return bench, masks



def evaluate_strata(df: pd.DataFrame, scores: pd.DataFrame,
                    masks: Mapping[Tuple[str, object, int], np.ndarray]) -> pd.DataFrame:
    """Category-wise audit at the preregistered K=100 budget.

    Selection is still global within each cutoff; stratum labels are used only after selection
    to diagnose where the fixed-budget gain comes from. The labels are never features.
    """
    rows = []
    selectors = ["random", "volume", "activity", "dynamic_influence", "reasoning_value", "hybrid", "oracle"]
    for d in [TEST_DATE, HOLDOUT_DATE]:
        base = scores[scores["snapshot_date"] == d].reset_index(drop=True)
        n = len(base)
        if n == 0:
            continue
        for selector in selectors:
            k = 100
            rv = base["rv_mrr"].to_numpy(float)
            if selector == "random":
                m = np.zeros(n, dtype=bool)
                random_expected = True
            else:
                m = top_k_mask(base[selector], k, base["event_id"])
                random_expected = False
            for stratum, g in base.groupby("stratum", dropna=False, sort=True):
                ix = g.index.to_numpy()
                if random_expected:
                    expected_n = float(k * len(ix) / n)
                    selected_rv = float(g["rv_mrr"].mean())
                    selected_z0 = float(g["z0"].mean())
                    selected_z1 = float(g["z1"].mean())
                    gain_sum = float(k / n * g["rv_mrr"].sum())
                    selected_volume = float(g["wallet_volume"].mean())
                else:
                    gm = m[ix]
                    expected_n = float(gm.sum())
                    selected_rv = float(g.loc[gm, "rv_mrr"].mean()) if gm.any() else float("nan")
                    selected_z0 = float(g.loc[gm, "z0"].mean()) if gm.any() else float("nan")
                    selected_z1 = float(g.loc[gm, "z1"].mean()) if gm.any() else float("nan")
                    gain_sum = float(g.loc[gm, "rv_mrr"].sum())
                    selected_volume = float(g.loc[gm, "wallet_volume"].mean()) if gm.any() else float("nan")
                rows.append({
                    "experiment_id": "SEL_BENCH_001", "date": str(d), "split": DATE_LABEL[d],
                    "selector": selector, "K": k, "stratum": str(stratum), "stratum_n": int(len(ix)),
                    "selected_n": expected_n, "selected_share_of_stratum": expected_n / len(ix),
                    "selected_rv_mean": selected_rv, "selected_z0_rate": selected_z0,
                    "selected_z1_rate": selected_z1, "incremental_sum_mrr": gain_sum,
                    "incremental_mrr_over_all_events": gain_sum / n, "selected_volume_mean": selected_volume,
                    "selection_is_expected_random": random_expected,
                })
    out = pd.DataFrame(rows)
    out.to_csv(OUTDIR / "strata_selector_results.csv", index=False)
    return out


def random_seed_spread(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d in [TUNE_DATE, TEST_DATE, HOLDOUT_DATE]:
        base = scores[scores["snapshot_date"] == d].reset_index(drop=True)
        n = len(base)
        rv = base["rv_mrr"].to_numpy(float)
        for k in K_VALUES:
            for seed in range(100):
                rng = np.random.default_rng(SEED + seed)
                mask = np.zeros(n, dtype=bool)
                mask[rng.choice(n, size=min(k, n), replace=False)] = True
                rows.append({"date": str(d), "split": DATE_LABEL[d], "K": k, "seed": seed,
                             "incremental_mrr": float(rv[mask].sum() / n),
                             "selected_rv_mean": float(rv[mask].mean()),
                             "utility_mrr": float(base["cheap_rr"].mean() + rv[mask].sum() / n)})
    out = pd.DataFrame(rows)
    out.insert(0, "experiment_id", "SEL_BENCH_001")
    out.to_csv(OUTDIR / "random_seed_spread.csv", index=False)
    return out


def bootstrap_counts(cluster: np.ndarray, B: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    uniq, inv = np.unique(cluster.astype(str), return_inverse=True)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(len(uniq), np.ones(len(uniq)) / len(uniq), size=B)
    return counts, inv


def bootstrap_comparisons(bench: pd.DataFrame, scores: pd.DataFrame, masks: Mapping[Tuple[str, object, int], np.ndarray]) -> pd.DataFrame:
    primary = ["hybrid", "reasoning_value", "dynamic_influence"]
    controls = ["random", "volume", "activity", "static_pagerank", "no_selection"]
    rows = []
    for eval_label, dates in [("test_aug", [TEST_DATE]), ("holdout_sep", [HOLDOUT_DATE]), ("aug_sep_joint", [TEST_DATE, HOLDOUT_DATE])]:
        sub = scores[scores["snapshot_date"].isin(dates)].reset_index(drop=True)
        if len(sub) == 0:
            continue
        cluster = sub["wallet_id"].astype(str).to_numpy()
        counts, inv = bootstrap_counts(cluster, BOOTSTRAPS, SEED)
        wallet_count = counts.shape[1]
        cluster_event_counts = np.bincount(inv, minlength=wallet_count).astype(float)
        # Every selector's mask is represented in the joint event order; random/no-selection are handled analytically.
        for k in K_VALUES:
            rv = sub["rv_mrr"].to_numpy(float)
            cheap = sub["cheap_rr"].to_numpy(float)
            n = len(sub)
            # Build each selector's per-event incremental utility contribution.
            contrib = {}
            for sel in primary + [c for c in controls if c not in {"random", "no_selection"}]:
                mlist = []
                for d in dates:
                    b = scores[scores["snapshot_date"] == d].reset_index(drop=True)
                    mlist.append(masks[(sel, d, k)])
                m = np.concatenate(mlist) if len(mlist) > 1 else mlist[0]
                contrib[sel] = m.astype(float) * rv
            contrib["random"] = np.full(n, min(k, n / len(dates)) / n if len(dates) > 1 else k / n) * rv
            # For joint two-cutoff evaluation, exact random fraction is K per cutoff, not K over joint n.
            if len(dates) > 1:
                contrib["random"] = np.concatenate([np.full(len(scores[scores["snapshot_date"] == d]), k / len(scores[scores["snapshot_date"] == d])) *
                                                       scores[scores["snapshot_date"] == d]["rv_mrr"].to_numpy(float) for d in dates])
            contrib["no_selection"] = np.zeros(n)
            # Cluster-weighted means: each bootstrap draw resamples wallets, preserving all events within a wallet.
            boot_means = {}
            for sel, arr in contrib.items():
                sums_by_cluster = np.bincount(inv, weights=arr, minlength=wallet_count)
                # Unequal numbers of events per wallet require a resampled event-count denominator.
                boot_denominator = counts @ cluster_event_counts
                boot_means[sel] = (counts @ sums_by_cluster) / np.maximum(boot_denominator, 1.0)
            for a in primary:
                for b in controls:
                    diffs = boot_means[a] - boot_means[b]
                    point = float(np.mean(contrib[a] - contrib[b]))
                    lo, hi = np.quantile(diffs, [0.025, 0.975])
                    # Add-one correction avoids reporting an impossible exact p=0 with finite B.
                    p_left = (float(np.sum(diffs <= 0)) + 1.0) / (BOOTSTRAPS + 1.0)
                    p_right = (float(np.sum(diffs >= 0)) + 1.0) / (BOOTSTRAPS + 1.0)
                    p = float(2 * min(p_left, p_right))
                    base_point = float(np.mean(contrib[b]))
                    rows.append({"experiment_id": "SEL_STATS_001", "eval": eval_label, "K": k,
                                 "selector": a, "baseline": b, "n_events": n,
                                 "n_wallet_clusters": int(len(np.unique(cluster))), "bootstrap_B": BOOTSTRAPS,
                                 "point_incremental_diff": point, "ci95_low": float(lo), "ci95_high": float(hi),
                                 "p_two_sided": min(1.0, p),
                                 "relative_improvement_vs_baseline": point / abs(base_point) if abs(base_point) > 1e-12 else float("nan")})
    out = pd.DataFrame(rows)
    if len(out):
        # Holm correction over all registered primary comparisons, reported transparently.
        order = np.argsort(out["p_two_sided"].fillna(1.0).to_numpy())
        adj = np.ones(len(out))
        m = len(out)
        for rank, idx in enumerate(order):
            adj[idx] = min(1.0, (m - rank) * float(out.iloc[idx]["p_two_sided"]))
        # enforce monotonicity in sorted order
        running = 0.0
        for rank, idx in enumerate(order):
            running = max(running, adj[idx])
            adj[idx] = running
        out["holm_p_all_registered_comparisons"] = adj
        # Predeclared primary family: the July-tuned hybrid selector at K=100 against the
        # five registered controls across August, September, and their joint summary. The
        # direct reasoning-value predictor is retained as a secondary comparator. Other K
        # values remain exploratory.
        primary_mask = (
            (out["K"] == 100)
            & (out["selector"] == "hybrid")
            & out["eval"].isin(["test_aug", "holdout_sep", "aug_sep_joint"])
        )
        primary_idx = np.flatnonzero(primary_mask.to_numpy())
        primary_adj = np.full(len(out), np.nan)
        if len(primary_idx):
            pvals = out.iloc[primary_idx]["p_two_sided"].to_numpy(float)
            order2 = np.argsort(pvals)
            vals = np.empty(len(primary_idx), dtype=float)
            running2 = 0.0
            m2 = len(primary_idx)
            for rank2, pos2 in enumerate(order2):
                vals[pos2] = min(1.0, (m2 - rank2) * pvals[pos2])
            for rank2, pos2 in enumerate(order2):
                running2 = max(running2, vals[pos2])
                vals[pos2] = running2
            primary_adj[primary_idx] = vals
        out["holm_p_primary_K100_family"] = primary_adj
    out.to_csv(OUTDIR / "bootstrap_comparisons.csv", index=False)
    return out


def load_glm_panels() -> pd.DataFrame:
    paths = {
        pd.Timestamp("2022-07-01").date(): ROOT / "artifacts/llm_panel_v2/runs/jul_gonogo_glm53_v2_floatfix.csv",
        pd.Timestamp("2022-08-01").date(): ROOT / "artifacts/llm_panel_v2/runs/aug_gonogo_glm53_v2_floatfix.csv",
        pd.Timestamp("2022-09-01").date(): ROOT / "artifacts/llm_panel_20220901/runs/sept_gonogo_glm53_v2_floatfix.csv",
    }
    parts = []
    for d, p in paths.items():
        x = pd.read_csv(p)
        x["snapshot_date"] = pd.to_datetime(x["snapshot_date"]).dt.date
        x = x[(x["snapshot_date"] == d) & (x["full_parse_ok"] == 1) & (x["nocf_parse_ok"] == 1)].copy()
        x["glm_rv"] = x["full_rr"] - x["cheap_rr"]
        x["glm_z0"] = (x["glm_rv"] > 0).astype(int)
        x["glm_z1"] = (x["glm_rv"] > 0.1).astype(int)
        x["glm_total_tokens"] = pd.to_numeric(x["total_tokens"], errors="coerce")
        parts.append(x[EVENT_KEY + ["glm_rv", "glm_z0", "glm_z1", "glm_total_tokens", "latency_s", "full_parse_ok", "nocf_parse_ok", "model"]])
    out = pd.concat(parts, ignore_index=True)
    out["event_id"] = out["snapshot_date"].astype(str) + "|" + out["target_address"].astype(str) + "|" + out["target_sequence_index"].astype(str)
    return out


def cross_model_robustness(df: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    glm = load_glm_panels()
    q = df[EVENT_KEY + ["event_id", "rv_mrr", "cheap_rr", "z0", "z1", "wallet_id"]].copy()
    q["event_id"] = q["event_id"].astype(str)
    joined = q.merge(glm, on=EVENT_KEY, how="inner", suffixes=("_qwen", "_glm"))
    rows = []
    for d in [TUNE_DATE, TEST_DATE, HOLDOUT_DATE]:
        x = joined[joined["snapshot_date"] == d]
        if len(x) < 10:
            continue
        for metric, a, b in [("rv", "rv_mrr", "glm_rv"), ("z0", "z0", "glm_z0"), ("z1", "z1", "glm_z1")]:
            if metric == "rv":
                aa, bb = x[a].to_numpy(float), x[b].to_numpy(float)
                spr = float(spearmanr(aa, bb).statistic) if np.std(aa) and np.std(bb) else float("nan")
                per = float(pearsonr(aa, bb).statistic) if np.std(aa) and np.std(bb) else float("nan")
                agree = float(((aa > 0) == (bb > 0)).mean())
                rows.append({"experiment_id": "ROBUST_GLM_001", "direction": "panel_agreement", "date": str(d),
                             "metric": metric, "n_valid": len(x), "spearman": spr, "pearson": per,
                             "sign_or_label_agreement": agree})
            else:
                agree = float((x[a].to_numpy(int) == x[b].to_numpy(int)).mean())
                rows.append({"experiment_id": "ROBUST_GLM_001", "direction": "panel_agreement", "date": str(d),
                             "metric": metric, "n_valid": len(x), "spearman": float("nan"), "pearson": float("nan"),
                             "sign_or_label_agreement": agree})
    # Qwen-trained frozen hybrid assignment transferred to GLM labels.
    score_cols = ["hybrid", "reasoning_value", "dynamic_influence", "volume", "random_expected"]
    score_part = scores[EVENT_KEY + ["event_id", "wallet_id", "cheap_rr"] + score_cols].copy()
    j = score_part.merge(glm, on=EVENT_KEY, how="inner")
    for d in [TUNE_DATE, TEST_DATE, HOLDOUT_DATE]:
        x = j[j["snapshot_date"] == d].reset_index(drop=True)
        if len(x) < 10:
            continue
        for sel in score_cols:
            for k in K_VALUES:
                if sel == "random_expected":
                    # expected random selection
                    inc = float(x["glm_rv"].mean() * k / len(x))
                    selected_n = k
                else:
                    m = top_k_mask(x[sel], k, x["event_id"] if "event_id" in x else pd.Series(np.arange(len(x))))
                    inc = float(x.loc[m, "glm_rv"].sum() / len(x))
                    selected_n = int(m.sum())
                rows.append({"experiment_id": "ROBUST_GLM_001", "direction": "qwen_score_to_glm_label",
                             "date": str(d), "selector": sel, "K": k, "n_valid": len(x),
                             "selected_n": selected_n, "glm_incremental_mrr": inc,
                             "glm_utility_mrr": float(x["cheap_rr"].mean() + inc)})
    # GLM-trained direct RV predictor -> Qwen labels. No June GLM anomaly is used.
    feat_cols = list(dict.fromkeys(c for c in (BEHAVIOR_FEATURES + GRAPH_FEATURES + NOVELTY_FEATURES + UNCERTAINTY_FEATURES)
                                 if c in df.columns and not is_forbidden(c)))
    joined_rg = df.merge(glm[[*EVENT_KEY, "glm_rv"]], on=EVENT_KEY, how="left")
    glm_train = joined_rg[(joined_rg["snapshot_date"] == TUNE_DATE) & joined_rg["glm_rv"].notna()].copy()
    eval_rg = joined_rg[joined_rg["snapshot_date"].isin([TEST_DATE, HOLDOUT_DATE])].copy()
    pred, model, used = fit_predict(glm_train, eval_rg, feat_cols, "glm_rv")
    eval_rg["glm_trained_score"] = pred
    for d in [TEST_DATE, HOLDOUT_DATE]:
        x = eval_rg[eval_rg["snapshot_date"] == d].reset_index(drop=True)
        for k in K_VALUES:
            m = top_k_mask(x["glm_trained_score"], k, x["event_id"])
            inc = float(x.loc[m, "rv_mrr"].sum() / len(x))
            rows.append({"experiment_id": "ROBUST_GLM_001", "direction": "glm_score_to_qwen_label",
                         "date": str(d), "selector": "glm_trained_rv", "K": k, "n_valid": len(x),
                         "selected_n": int(m.sum()), "qwen_incremental_mrr": inc,
                         "qwen_utility_mrr": float(x["cheap_rr"].mean() + inc)})
    out = pd.DataFrame(rows)
    out.to_csv(OUTDIR / "cross_model_robustness.csv", index=False)
    write_json(OUTDIR / "cross_model_manifest.json", {
        "experiment_id": "ROBUST_GLM_001", "glm_sources": [
            "artifacts/llm_panel_v2/runs/jul_gonogo_glm53_v2_floatfix.csv",
            "artifacts/llm_panel_v2/runs/aug_gonogo_glm53_v2_floatfix.csv",
            "artifacts/llm_panel_20220901/runs/sept_gonogo_glm53_v2_floatfix.csv",
        ], "excluded": "June GLM v2 float-fix due audited parse anomaly; no new calls",
        "valid_rows_by_date": {str(d): int((glm["snapshot_date"] == d).sum()) for d in [TUNE_DATE, TEST_DATE, HOLDOUT_DATE]},
        "glm_to_qwen_features": used, "note": "transfer is panel-control evidence, not proof of model-independent superiority"
    })
    return out


def volume_residual(train: pd.DataFrame, eval_df: pd.DataFrame, y_col: str = "rv_mrr") -> np.ndarray:
    x = np.log1p(pd.to_numeric(train["wallet_volume"], errors="coerce").fillna(train["wallet_volume"].median()).to_numpy(float))
    y = pd.to_numeric(train[y_col], errors="coerce").to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 5:
        return np.zeros(len(eval_df))
    X = np.column_stack([np.ones(ok.sum()), x[ok]])
    beta = np.linalg.lstsq(X, y[ok], rcond=None)[0]
    xe = np.log1p(pd.to_numeric(eval_df["wallet_volume"], errors="coerce").fillna(train["wallet_volume"].median()).to_numpy(float))
    return pd.to_numeric(eval_df[y_col], errors="coerce").to_numpy(float) - np.column_stack([np.ones(len(eval_df)), xe]) @ beta


def adversarial_audit(df: pd.DataFrame, scores: pd.DataFrame, bench: pd.DataFrame, masks: Mapping[Tuple[str, object, int], np.ndarray]) -> Tuple[pd.DataFrame, Dict]:
    rows = []
    forbidden_used = []
    manifest = json.loads((OUTDIR / "selector_model_manifest.json").read_text())
    for group, cols in manifest.get("groups", {}).items():
        bad = [c for c in cols if is_forbidden(c)]
        forbidden_used.extend([(group, c) for c in bad])
    rows.append({"audit": "forbidden_primary_feature_scan", "split": "all", "selector": "primary_feature_contract",
                 "K": 100, "value": float(len(forbidden_used)), "status": "PASS" if not forbidden_used else "FAIL",
                 "detail": json.dumps(forbidden_used)})
    # Static global graph prior is deliberately an audit/context arm, not a valid temporal feature.
    rows.append({"audit": "static_full_window_prior", "split": "all", "selector": "static_degree/static_pagerank",
                 "K": 100, "value": 1.0, "status": "CONTEXT_ONLY_LEAKY_PRIOR",
                 "detail": "artifacts/exgraph_structural_features.csv is full-window aggregate; excluded from primary learned features"})
    # Feature-volume associations and volume-residualized selected gain.
    primary = ["hybrid", "reasoning_value", "dynamic_influence", "volume", "static_pagerank"]
    for d in [TEST_DATE, HOLDOUT_DATE]:
        base = scores[scores["snapshot_date"] == d].reset_index(drop=True)
        train = scores[scores["snapshot_date"].isin([TRAIN_DATE, TUNE_DATE])].copy()
        residual = volume_residual(train, base)
        base["rv_volume_resid"] = residual
        for sel in primary:
            ok = np.isfinite(base[sel]) & np.isfinite(base["wallet_volume"])
            corr = float(spearmanr(base.loc[ok, sel], base.loc[ok, "wallet_volume"]).statistic) if ok.sum() > 5 else float("nan")
            m = top_k_mask(base[sel], 100, base["event_id"])
            rows.append({"audit": "score_volume_spearman", "split": DATE_LABEL[d], "selector": sel, "K": 100,
                         "value": corr, "status": "DESCRIPTIVE", "detail": "score vs as-of wallet_volume"})
            rows.append({"audit": "volume_residual_selected_gain", "split": DATE_LABEL[d], "selector": sel, "K": 100,
                         "value": float(base.loc[m, "rv_volume_resid"].mean()), "status": "DESCRIPTIVE",
                         "detail": "rv residual after train-only OLS on log1p(wallet_volume)"})
            rows.append({"audit": "volume_selected_mean", "split": DATE_LABEL[d], "selector": sel, "K": 100,
                         "value": float(base.loc[m, "wallet_volume"].mean()), "status": "DESCRIPTIVE",
                         "detail": "selected mean as-of volume"})
        # low-volume/high-influence quadrant coverage using future influence only for audit, never selection.
        di = pd.read_parquet(P2 / "dynamic_influence_dataset.parquet", columns=["snapshot_date", "target_address", "I_new_hist", "log_vol"])
        di["snapshot_date"] = pd.to_datetime(di["snapshot_date"]).dt.date
        q = base.merge(di, on=["snapshot_date", "target_address"], how="left")
        q["low_volume"] = q["log_vol"] <= q["log_vol"].median()
        q["high_influence"] = q["I_new_hist"] >= q["I_new_hist"].median()
        q["lowvol_highinf"] = q["low_volume"] & q["high_influence"]
        for sel in primary:
            m = top_k_mask(q[sel], 100, q["event_id"])
            denom = int(q["lowvol_highinf"].sum())
            rows.append({"audit": "low_volume_high_influence_share_selected", "split": DATE_LABEL[d], "selector": sel,
                         "K": 100, "value": float(q.loc[m, "lowvol_highinf"].mean()), "status": "SUPERVISION_AUDIT",
                         "detail": f"selected share; future I_new_hist used only for audit; quadrant_n={denom}"})
            rows.append({"audit": "low_volume_high_influence_recall", "split": DATE_LABEL[d], "selector": sel,
                         "K": 100, "value": float(q.loc[m, "lowvol_highinf"].sum() / max(1, denom)), "status": "SUPERVISION_AUDIT",
                         "detail": "recall among low-volume/high-influence wallets"})
    # Wallet identity and duplicate checks.
    counts = df.groupby("wallet_id").size()
    rows.append({"audit": "wallet_reuse_across_4000_events", "split": "all", "selector": "none", "K": 0,
                 "value": float((counts > 1).mean()), "status": "DESCRIPTIVE",
                 "detail": f"{int((counts > 1).sum())} wallets repeat; wallet/address identity not a model feature"})
    # Label-permutation placebo: direct RV predictor fit on June+July permuted targets, applied to Aug/Sep.
    safe_features = manifest["groups"]["hybrid_model"]
    train = df[df["snapshot_date"].isin([TRAIN_DATE, TUNE_DATE])].copy()
    eval_df = df[df["snapshot_date"].isin([TEST_DATE, HOLDOUT_DATE])].copy()
    rng = np.random.default_rng(SEED)
    placebo_train = train.copy()
    placebo_train["rv_mrr"] = rng.permutation(placebo_train["rv_mrr"].to_numpy())
    pred, _, used = fit_predict(placebo_train, eval_df, safe_features, "rv_mrr")
    eval_df["placebo_score"] = pred
    for d in [TEST_DATE, HOLDOUT_DATE]:
        x = eval_df[eval_df["snapshot_date"] == d].reset_index(drop=True)
        for k in [100]:
            m = top_k_mask(x["placebo_score"], k, x["event_id"])
            nd = ndcg_at_k(x["rv_mrr"].to_numpy(float), x["placebo_score"].to_numpy(float), k)
            rows.append({"audit": "permuted_label_placebo_ndcg", "split": DATE_LABEL[d], "selector": "rv_pred_placebo",
                         "K": k, "value": float(nd), "status": "NEGATIVE_CONTROL",
                         "detail": "June+July RV labels permuted before fitting; no future columns"})
    audit = pd.DataFrame(rows)
    audit.insert(0, "experiment_id", "AUDIT_ADV_001")
    audit.to_csv(OUTDIR / "adversarial_audit.csv", index=False)
    audit_payload = {
        "experiment_id": "AUDIT_ADV_001", "forbidden_features_used": forbidden_used,
        "static_prior_is_context_only": True, "static_prior_source": "artifacts/exgraph_structural_features.csv",
        "primary_feature_groups": manifest.get("groups", {}),
        "placebo_features_used": used, "rows": rows,
        "interpretation_boundary": "volume residuals and quadrant coverage are audit evidence, not causal effects",
    }
    write_json(OUTDIR / "adversarial_audit.json", audit_payload)
    return audit, audit_payload


def make_figures(df: pd.DataFrame, scores: pd.DataFrame, bench: pd.DataFrame, audit: pd.DataFrame) -> Dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 7,
                          "pdf.fonttype": 42, "ps.fonttype": 42})
    paths = {}
    # 1. Distribution by frozen stratum.
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    order = ["new_tail", "new_popular", "repeat_easy", "repeat_hard"]
    vals = [pd.to_numeric(df.loc[df["stratum"] == s, "rv_mrr"], errors="coerce").dropna().to_numpy() for s in order]
    vp = ax.violinplot(vals, positions=np.arange(1, len(order) + 1), showmeans=False, showmedians=True, showextrema=False)
    for body in vp["bodies"]:
        body.set_facecolor("#4c78a8"); body.set_edgecolor("#2f4f6f"); body.set_alpha(0.75)
    ax.set_xticks(np.arange(1, len(order) + 1), order)
    ax.axhline(0, color="black", lw=.7)
    ax.set_xlabel("Event stratum"); ax.set_ylabel("Reasoning gain (Full-CF − Cheap MRR)")
    ax.set_title("Reasoning gain is heterogeneous across event strata")
    fig.tight_layout(); p = FIGDIR / "reasoning_gain_distribution.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)

    # 2. Selector NDCG curves.
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    sels = ["random", "volume", "activity", "dynamic_influence", "reasoning_value", "hybrid", "oracle"]
    colors = {"random": "#888888", "volume": "#c77c2b", "activity": "#8c564b", "dynamic_influence": "#1f77b4",
              "reasoning_value": "#2ca02c", "hybrid": "#d62728", "oracle": "#000000"}
    for split in ["test_aug", "holdout_sep"]:
        for sel in sels:
            x = bench[(bench["split"] == split) & (bench["selector"] == sel)]
            if len(x):
                ax.plot(x["K"], x["ndcg_at_k"], marker="o", ms=3, lw=1.2, color=colors[sel], alpha=.55 if split == "test_aug" else 1.0,
                        label=f"{sel} ({'Aug' if split == 'test_aug' else 'Sep'})")
    ax.set_xscale("log"); ax.set_xticks(K_VALUES); ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Expensive-reasoning budget K"); ax.set_ylabel("NDCG@K for positive reasoning gain")
    ax.set_title("Selector quality for high-gain events")
    ax.legend(ncol=2, frameon=True, loc="best"); fig.tight_layout()
    p = FIGDIR / "selector_ndcg.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)

    # 3. Budget utility curve.
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    sels = ["no_selection", "random", "volume", "dynamic_influence", "reasoning_value", "hybrid", "oracle", "all_full"]
    for split, ls in [("test_aug", "-"), ("holdout_sep", "--")]:
        for sel in sels:
            x = bench[(bench["split"] == split) & (bench["selector"] == sel)]
            if len(x):
                ax.plot(x["K"], x["utility_mrr"], marker="o", ms=3, lw=1.1, ls=ls, label=f"{sel} ({'Aug' if split == 'test_aug' else 'Sep'})")
    ax.set_xscale("log"); ax.set_xticks(K_VALUES); ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Number of Full-CF calls (matched count budget)"); ax.set_ylabel("Per-event predictive utility (MRR)")
    ax.set_title("Matched-budget utility: selected events receive Full-CF")
    ax.legend(ncol=2, fontsize=6.5, loc="best"); fig.tight_layout()
    p = FIGDIR / "budget_utility_curve.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)

    # 4. Influence vs volume.
    di = pd.read_parquet(P2 / "dynamic_influence_dataset.parquet", columns=["snapshot_date", "target_address", "I_new_hist", "log_vol"])
    di["snapshot_date"] = pd.to_datetime(di["snapshot_date"]).dt.date
    z = di[di["snapshot_date"].isin([TEST_DATE, HOLDOUT_DATE])].dropna(subset=["I_new_hist", "log_vol"]).copy()
    if len(z) > 20000:
        z = z.sample(20000, random_state=SEED)
    z["quadrant"] = "other"
    z.loc[(z["log_vol"] <= z["log_vol"].median()) & (z["I_new_hist"] >= z["I_new_hist"].median()), "quadrant"] = "low-volume / high-influence"
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    for qname, color, label in [("other", "#bbbbbb", "other"), ("low-volume / high-influence", "#d62728", "low-volume / high-influence")]:
        qz = z[z["quadrant"] == qname]
        ax.scatter(qz["log_vol"], qz["I_new_hist"], s=8, alpha=.35, linewidths=0, color=color, label=label)
    ax.set_xlabel("log(1 + 90-day event volume)"); ax.set_ylabel("Dynamic predictive influence I_new_hist")
    ax.set_title("Dynamic predictive influence is not synonymous with volume")
    ax.legend(title="Audit quadrant", loc="best"); fig.tight_layout()
    p = FIGDIR / "influence_vs_volume.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)

    # 5. Temporal generalization.
    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    sels = ["random", "volume", "dynamic_influence", "reasoning_value", "hybrid", "oracle"]
    for sel in sels:
        x = bench[(bench["selector"] == sel) & (bench["K"] == 100) & (bench["split"].isin(["tune_jul", "test_aug", "holdout_sep"]))]
        if len(x):
            xx = ["July\ntune", "August\ntest", "September\nholdout"]
            vals = [x[x["split"] == s]["incremental_mrr"].iloc[0] if len(x[x["split"] == s]) else np.nan for s in ["tune_jul", "test_aug", "holdout_sep"]]
            ax.plot(xx, vals, marker="o", lw=1.3, label=sel)
    ax.axhline(0, color="black", lw=.7); ax.set_ylabel("Incremental MRR at K=100"); ax.set_title("Temporal generalization at the preregistered K=100 budget")
    ax.legend(ncol=2, loc="best"); fig.tight_layout()
    p = FIGDIR / "temporal_generalization.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)

    # 6. Efficiency frontier.
    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    for split, marker in [("test_aug", "o"), ("holdout_sep", "s")]:
        x = bench[(bench["split"] == split) & (bench["selector"].isin(["random", "volume", "dynamic_influence", "reasoning_value", "hybrid", "oracle"])) & (bench["K"].isin([25, 50, 100, 250, 500]))]
        for sel, g in x.groupby("selector"):
            ax.plot(g["budget_tokens"] / 1000.0, g["incremental_mrr"], marker=marker, ms=3, lw=1.0, label=f"{sel} ({'Aug' if split == 'test_aug' else 'Sep'})")
    ax.axhline(0, color="black", lw=.7); ax.set_xlabel("Measured Full-CF tokens (thousands)"); ax.set_ylabel("Incremental MRR per event")
    ax.set_title("Efficiency frontier under measured panel cost")
    ax.legend(ncol=2, fontsize=6.5, loc="best"); fig.tight_layout()
    p = FIGDIR / "efficiency_frontier.pdf"; fig.savefig(p); plt.close(fig); paths[p.name] = str(p)
    write_json(OUTDIR / "figure_manifest.json", {"experiment_id": "FIG_PHASE2_001", "figures": paths,
                                                  "source_tables": ["selector_benchmark.csv", "selector_scores.parquet", "adversarial_audit.csv"]})
    return paths


def summarize(bench: pd.DataFrame, boot: pd.DataFrame, cross: pd.DataFrame, audit: pd.DataFrame, model_meta: Dict, strata: pd.DataFrame | None = None) -> Dict:
    def row(split, sel, k=100):
        x = bench[(bench["split"] == split) & (bench["selector"] == sel) & (bench["K"] == k)]
        return x.iloc[0].to_dict() if len(x) else {}
    summary = {
        "experiment_ids": ["SEL_BENCH_001", "SEL_STATS_001", "ROBUST_GLM_001", "AUDIT_ADV_001", "FIG_PHASE2_001"],
        "protocol": {"train": str(TRAIN_DATE), "tune": str(TUNE_DATE), "test": str(TEST_DATE), "holdout": str(HOLDOUT_DATE),
                     "K_values": K_VALUES, "primary_tuning_K": 100, "bootstrap_B": BOOTSTRAPS},
        "hybrid_weights": model_meta.get("hybrid_weights", {}),
        "k100": {split: {sel: row(split, sel) for sel in ["random", "volume", "activity", "dynamic_influence", "reasoning_value", "hybrid", "oracle", "no_selection"]}
                 for split in ["tune_jul", "test_aug", "holdout_sep"]},
        "bootstrap_rows": int(len(boot)), "cross_model_rows": int(len(cross)), "audit_rows": int(len(audit)),
        "strata_rows": int(len(strata)) if strata is not None else 0,
        "files": {
            "selector_benchmark": str(P2 / "selector_benchmark.csv"),
            "bootstrap": str(OUTDIR / "bootstrap_comparisons.csv"),
            "cross_model": str(OUTDIR / "cross_model_robustness.csv"),
            "audit": str(OUTDIR / "adversarial_audit.csv"),
            "strata": str(OUTDIR / "strata_selector_results.csv"),
        },
    }
    write_json(OUTDIR / "phase2_selector_summary.json", summary)
    return summary


def update_registry(script_hash: str, summary: Dict, status: str = "COMPLETE") -> None:
    # Replace only the registered Phase-II entries appended by this run. This stays inside
    # research/phase2 and leaves all frozen artifacts untouched.
    p = P2 / "EXPERIMENT_REGISTRY.yaml"
    text = p.read_text()
    text = text.replace("pending-run_selector_benchmark.py-sha256", f"run_selector_benchmark.py sha256={script_hash[:16]}")
    for eid in ["SEL_BENCH_001", "SEL_STATS_001", "ROBUST_GLM_001", "AUDIT_ADV_001", "FIG_PHASE2_001"]:
        # scope to the entry block
        start = text.find(f"- experiment_id: {eid}")
        if start < 0:
            continue
        next_start = text.find("\n- experiment_id:", start + 2)
        end = len(text) if next_start < 0 else next_start
        block = text[start:end]
        block = block.replace("status: REGISTERED", f"status: {status}")
        text = text[:start] + block + text[end:]
    # Insert concise generated result references in each block before status.
    replacements = {
        "SEL_BENCH_001": "result: generated selector tournament tables; see selector_benchmark.csv and selector_results/phase2_selector_summary.json",
        "SEL_STATS_001": "result: generated paired wallet-cluster bootstrap comparisons with Holm-adjusted p-values",
        "ROBUST_GLM_001": "result: generated read-only cross-model control using valid GLM v2 float-fix rows; June excluded",
        "AUDIT_ADV_001": "result: generated feature/leakage/volume/placebo/quadrant audit",
        "FIG_PHASE2_001": "result: generated six PDF figures from registered tables",
    }
    text = p.read_text().replace("pending-run_selector_benchmark.py-sha256", f"run_selector_benchmark.py sha256={script_hash[:16]}")
    for eid, result in replacements.items():
        start = text.find(f"- experiment_id: {eid}")
        if start < 0:
            continue
        next_start = text.find("\n- experiment_id:", start + 2)
        end = len(text) if next_start < 0 else next_start
        block = text[start:end]
        block = block.replace("  result: pending", f"  {result}")
        block = block.replace("  status: REGISTERED", f"  status: {status}")
        text = text[:start] + block + text[end:]
    p.write_text(text)


def main() -> None:
    random.seed(SEED); np.random.seed(SEED)
    script_hash = sha256_file(Path(__file__))
    print("loading inputs")
    rg, di, static = load_inputs()
    print("rows", len(rg), "DI rows", len(di))
    df, scores, model_meta = build_scores(rg, di)
    print("scores built; hybrid weights", model_meta["hybrid_weights"])
    bench, masks = evaluate_selector_table(df, scores)
    print("benchmark rows", len(bench))
    strata = evaluate_strata(df, scores, masks)
    print("strata rows", len(strata))
    random_seed_spread(scores)
    boot = bootstrap_comparisons(bench, scores, masks)
    print("bootstrap rows", len(boot))
    cross = cross_model_robustness(df, scores)
    print("cross-model rows", len(cross))
    audit, audit_payload = adversarial_audit(df, scores, bench, masks)
    print("audit rows", len(audit))
    figures = make_figures(df, scores, bench, audit)
    summary = summarize(bench, boot, cross, audit, model_meta, strata)
    run_manifest = {
        "script": str(Path(__file__).relative_to(ROOT)), "script_sha256": script_hash,
        "run_date": "2026-09-12", "seed": SEED, "bootstrap_B": BOOTSTRAPS,
        "external_api_calls": 0, "llm_calls": 0, "gpu_requested": False,
        "input_sha256_prefix": {
            "reasoning_gain_dataset.parquet": sha256_file(P2 / "reasoning_gain_dataset.parquet")[:16],
            "dynamic_influence_dataset.parquet": sha256_file(P2 / "dynamic_influence_dataset.parquet")[:16],
            "exgraph_structural_features.csv": sha256_file(ROOT / "artifacts/exgraph_structural_features.csv")[:16],
        },
        "figures": figures, "summary": summary,
        "notes": [
            "No raw event-level data was sent to an external API; this run is local deterministic CPU analysis.",
            "Static full-window graph prior is context-only/leaky and excluded from primary learned features.",
            "Dynamic influence labels are supervision-only; selector input uses a prior-cutoff predicted influence score.",
            "September uses the selector frozen after July; no August refit or September tuning.",
        ],
    }
    write_json(OUTDIR / "run_manifest.json", run_manifest)
    update_registry(script_hash, summary, status="COMPLETE")
    print("complete")


if __name__ == "__main__":
    main()
