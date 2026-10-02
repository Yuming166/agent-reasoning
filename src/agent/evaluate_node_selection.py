#!/usr/bin/env python3
"""Evaluate the pre-deliberation important-node/event selector.

The unit of selection is a target wallet event at a frozen snapshot.  A
selected event receives the expensive full deliberation arm; an unselected
event keeps the cheap ranker result.  This script deliberately evaluates the
selector separately from the recursive reasoning design.

Protocol (default):
  2022-06-01 train -> 2022-07-01 validation/tuning -> 2022-08-01 frozen test
  2022-09-01 is an optional extra time-out check and is never used for tuning.

All selector features are available before an LLM call.  In particular, no
truth rank, realized LLM rank, parse outcome, mask sensitivity, or evaluation
weight is a model feature.  The measured full-arm failure policy is
conservative: an invalid full output falls back to the cheap RR, so its
operational gain is zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


ROOT = Path(__file__).resolve().parents[2]
EVENT_KEY = ["snapshot_date", "target_address", "target_sequence_index"]
BUDGETS = (0.05, 0.10, 0.20, 0.50, 0.75)
PRIMARY_BUDGET = 0.50

# This is intentionally the same pre-call feature family used by the v2
# router dataset.  Do not add stratum, pop_weight, truth_g_rank, or outcomes.
ROUTER_FEATURES = [
    "cp_type_repeat", "log_evt_cnt", "cp_entropy_90d", "cp_new_rate_30d",
    "log_pool_n", "cheap_top_score", "cheap_margin", "cheap_score_entropy",
    "frac_bridge", "frac_personal", "frac_tail", "frac_top2000",
    "log_n_bridge", "log_n_personal", "top1_is_personal", "top1_is_bridge",
]
LEAKAGE_COLUMNS = {
    "label", "counterparty_address", "truth_g_rank", "truth_in_pool",
    "full_rank", "full_rr", "full_parse_ok", "nocf_rank", "nocf_rr",
    "nocf_parse_ok", "mask_sensitive", "gain_full", "gain_nocf",
    "full_wins", "full_failed", "nocf_failed", "full_rr_raw", "nocf_rr_raw",
    "pop_weight", "stratum", "activity",
}
NONLEARNING = [
    "random", "degree", "pagerank", "activity", "volume", "repeat",
    "cheap_uncertainty", "cheap_margin", "cheap_topscore",
]


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _safe_float(series: pd.Series, default: float = 0.0) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan).fillna(default)


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    x = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    m = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not m.any():
        return float("nan")
    return float(np.sum(x[m] * w[m]) / np.sum(w[m]))


def weighted_fraction(mask: Sequence[bool], weights: Sequence[float], denom_mask=None) -> float:
    m = np.asarray(mask, dtype=bool)
    w = np.asarray(weights, dtype=float)
    valid = np.isfinite(w) & (w > 0)
    if denom_mask is None:
        denom_mask = valid
    else:
        denom_mask = np.asarray(denom_mask, dtype=bool) & valid
    num = np.sum(w[m & valid])
    den = np.sum(w[denom_mask])
    return float(num / den) if den > 0 else float("nan")


def rank_corr(x: Sequence[float], y: Sequence[float]) -> float:
    a = pd.Series(np.asarray(x, dtype=float)).rank(method="average").to_numpy()
    b = pd.Series(np.asarray(y, dtype=float)).rank(method="average").to_numpy()
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def deterministic_seed(*parts) -> int:
    raw = "|".join(map(str, parts)).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:4], "little")


def sort_order(df: pd.DataFrame, score_col: str) -> np.ndarray:
    # Candidate scores can tie.  The address/index tie-breaker is fixed and
    # independent of labels, making every policy reproducible.
    work = df[[score_col, "target_address", "target_sequence_index"]].copy()
    work[score_col] = _safe_float(work[score_col], default=-np.inf)
    work = work.sort_values(
        [score_col, "target_address", "target_sequence_index"],
        ascending=[False, True, True], kind="mergesort"
    )
    return work.index.to_numpy()


def load_scored(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    scored = pd.read_csv(path)
    required = set(EVENT_KEY + [
        "candidate_address", "cand_source", "g_rank", "g_cnt", "cheap_score",
        "cp_type", "pop_weight", "evt_cnt_90d", "cp_entropy_90d",
        "cp_new_rate_30d",
    ])
    missing = sorted(required - set(scored.columns))
    if missing:
        raise ValueError(f"scored panel missing columns: {missing}")
    if scored[EVENT_KEY].duplicated().any():
        # Candidate rows are allowed to repeat only by candidate address; the
        # event key alone must occur many times.  This check is intentionally
        # omitted; event uniqueness is checked after group aggregation.
        pass
    scored["g_rank"] = _safe_float(scored["g_rank"], default=99999)
    scored["g_cnt"] = _safe_float(scored["g_cnt"], default=0)
    scored["cheap_score"] = _safe_float(scored["cheap_score"], default=0)
    scored["evt_cnt_90d"] = _safe_float(scored["evt_cnt_90d"], default=0)
    scored["cp_entropy_90d"] = _safe_float(scored["cp_entropy_90d"], default=0)
    scored["cp_new_rate_30d"] = _safe_float(scored["cp_new_rate_30d"], default=0)

    rows = []
    for key, group in scored.groupby(EVENT_KEY, sort=False, dropna=False):
        g = group.sort_values(
            ["cheap_score", "candidate_address"], ascending=[False, True],
            kind="mergesort"
        ).reset_index(drop=True)
        scores = g["cheap_score"].to_numpy(float)
        p = np.clip(scores, 1e-9, 1 - 1e-9)
        source = g["cand_source"].astype(str)
        n = len(g)
        top1 = float(scores[0]) if n else 0.0
        top2 = float(scores[1]) if n > 1 else 0.0
        rows.append({
            "snapshot_date": key[0], "target_address": key[1],
            "target_sequence_index": int(key[2]),
            "cp_type_repeat": int(str(g["cp_type"].iloc[0]) == "repeat"),
            "evt_cnt_90d": float(g["evt_cnt_90d"].iloc[0]),
            "cp_entropy_90d": float(g["cp_entropy_90d"].iloc[0]),
            "cp_new_rate_30d": float(g["cp_new_rate_30d"].iloc[0]),
            "pool_n": n,
            "cheap_top_score": top1,
            "cheap_margin": top1 - top2,
            "cheap_score_entropy": float(
                -(p * np.log(p) + (1 - p) * np.log(1 - p)).mean()
            ) if n else 0.0,
            "frac_bridge": float((source == "new_bridge").mean()),
            "frac_personal": float((source == "repeat_personal").mean()),
            "frac_tail": float(source.isin(["new_tail", "repeat_tail"]).mean()),
            "frac_top2000": float(source.isin(["new_top2000", "repeat_top2000"]).mean()),
            "n_bridge": int((source == "new_bridge").sum()),
            "n_personal": int((source == "repeat_personal").sum()),
            "top1_is_personal": int(str(source.iloc[0]) == "repeat_personal"),
            "top1_is_bridge": int(str(source.iloc[0]) == "new_bridge"),
            # Evaluation weight is metadata, never a selector feature.
            "pop_weight": float(g["pop_weight"].iloc[0]),
            "stratum": str(g["stratum"].iloc[0]) if "stratum" in g else "unknown",
            "cp_type": str(g["cp_type"].iloc[0]),
            # As-of candidate-pool graph priors.  g_cnt is historical count;
            # g_rank is historical popularity rank in the snapshot window.
            "degree_score": float(np.log1p(g["g_cnt"].max())),
            "pagerank_score": float(-np.log(max(1.0, g["g_rank"].min()))),
            "volume_score": float(np.log1p(g["g_cnt"].sum())),
            "degree_mean_top5": float(np.log1p(g["g_cnt"].nlargest(5).mean())),
            "pagerank_mean_top5": float(
                (-np.log(g["g_rank"].clip(lower=1))).nlargest(5).mean()
            ),
        })
    events = pd.DataFrame(rows)
    if events.empty:
        raise ValueError("no events in scored panel")
    if events[EVENT_KEY].duplicated().any():
        raise ValueError("event feature table has duplicate event keys")
    return scored, events


def add_structural_sensitivity(scored: pd.DataFrame, events: pd.DataFrame,
                               structural_path: Path | None) -> Tuple[pd.DataFrame, dict]:
    """Add optional static EX-Graph PageRank/degree sensitivity scores.

    The released static structural artifact has limited candidate coverage and
    is not part of the primary leakage-safe protocol.  Missing candidates get
    score zero; coverage is recorded so this baseline cannot be mistaken for a
    complete as-of feature.
    """
    audit = {"enabled": bool(structural_path), "path": str(structural_path) if structural_path else None}
    if not structural_path:
        return events, audit
    structural = pd.read_csv(structural_path)
    required = {"ethereum_address", "degree", "pagerank"}
    missing = sorted(required - set(structural.columns))
    if missing:
        raise ValueError(f"structural file missing columns: {missing}")
    structural = structural[["ethereum_address", "degree", "pagerank"]].copy()
    structural["degree"] = _safe_float(structural["degree"], 0)
    structural["pagerank"] = _safe_float(structural["pagerank"], 0)
    joined = scored[EVENT_KEY + ["candidate_address"]].merge(
        structural, left_on="candidate_address", right_on="ethereum_address", how="left"
    )
    joined["has_structural"] = joined["pagerank"].notna()
    agg = joined.groupby(EVENT_KEY, sort=False).agg(
        static_pagerank=("pagerank", "max"),
        static_degree=("degree", "max"),
        static_structural_candidate_n=("has_structural", "sum"),
        static_structural_pool_n=("candidate_address", "size"),
    ).reset_index()
    agg["static_pagerank"] = _safe_float(agg["static_pagerank"], 0)
    agg["static_degree"] = _safe_float(agg["static_degree"], 0)
    agg["static_structural_coverage"] = (
        agg["static_structural_candidate_n"] / agg["static_structural_pool_n"].clip(lower=1)
    )
    out = events.merge(agg, on=EVENT_KEY, how="left", validate="one_to_one")
    audit.update({
        "candidate_row_coverage": float(joined["has_structural"].mean()),
        "event_any_candidate_coverage": float(
            joined.groupby(EVENT_KEY)["has_structural"].any().mean()
        ),
        "event_mean_candidate_coverage": float(agg["static_structural_coverage"].mean()),
    })
    return out, audit


def load_run(month: str, path: Path) -> Tuple[pd.DataFrame, dict]:
    run = pd.read_csv(path)
    required = set(EVENT_KEY + [
        "cheap_rr", "full_rr", "full_parse_ok", "nocf_rr", "nocf_parse_ok",
        "total_tokens", "latency_s", "truth_in_pool",
    ])
    missing = sorted(required - set(run.columns))
    if missing:
        raise ValueError(f"run {path} missing columns: {missing}")
    run = run[run["snapshot_date"].astype(str) == str(month)].copy()
    if run.empty:
        raise ValueError(f"run {path} has no rows for {month}")
    if run[EVENT_KEY].duplicated().any():
        dup = int(run[EVENT_KEY].duplicated().sum())
        raise ValueError(f"run {path} has {dup} duplicate event rows")

    run["cheap_rr"] = _safe_float(run["cheap_rr"], np.nan)
    full_raw = pd.to_numeric(run["full_rr"], errors="coerce")
    nocf_raw = pd.to_numeric(run["nocf_rr"], errors="coerce")
    full_ok = (_safe_float(run["full_parse_ok"], 0) >= 1) & full_raw.notna()
    nocf_ok = (_safe_float(run["nocf_parse_ok"], 0) >= 1) & nocf_raw.notna()
    run["full_failed"] = (~full_ok).astype(int)
    run["nocf_failed"] = (~nocf_ok).astype(int)
    # Operational arm: failure means no gain over cheap, not a dropped row.
    run["full_rr_raw_num"] = full_raw
    run["nocf_rr_raw_num"] = nocf_raw
    run["full_rr_operational"] = full_raw.where(full_ok, run["cheap_rr"])
    run["nocf_rr_operational"] = nocf_raw.where(nocf_ok, run["cheap_rr"])
    run["full_rr_operational"] = run["full_rr_operational"].fillna(run["cheap_rr"])
    run["nocf_rr_operational"] = run["nocf_rr_operational"].fillna(run["cheap_rr"])
    run["gain_full"] = run["full_rr_operational"] - run["cheap_rr"]
    run["gain_nocf"] = run["nocf_rr_operational"] - run["cheap_rr"]
    run["full_wins"] = (run["gain_full"] > 0).astype(int)
    run["total_tokens"] = _safe_float(run["total_tokens"], 0)
    run["latency_s"] = _safe_float(run["latency_s"], 0)
    run["truth_in_pool"] = _safe_float(run["truth_in_pool"], 0).astype(int)

    models = sorted(set(run["model"].dropna().astype(str))) if "model" in run else []
    stage_status = {}
    for col in sorted(c for c in run.columns if c.startswith("audit_step") and c.endswith("_status")):
        stage_status[col] = {str(k): int(v) for k, v in run[col].fillna("missing").value_counts().items()}
    client_error_cols = [c for c in run.columns if c.startswith("audit_step") and c.endswith("_client_error")]
    internal_fallback_cols = [c for c in run.columns if c.endswith("internal_fallback")]
    meta = {
        "month": month,
        "path": str(path),
        "rows": int(len(run)),
        "support_rows": int(run["truth_in_pool"].sum()),
        "support_rate": float(run["truth_in_pool"].mean()),
        "models": models,
        "full_parse_rate": float(full_ok.mean()),
        "nocf_parse_rate": float(nocf_ok.mean()),
        "full_fallback_rows": int(run["full_failed"].sum()),
        "nocf_fallback_rows": int(run["nocf_failed"].sum()),
        "stage_status_counts": stage_status,
        "stage_client_error_total": int(sum(run[c].fillna(0).sum() for c in client_error_cols)),
        "internal_fallback_total": int(sum(run[c].fillna(0).sum() for c in internal_fallback_cols)),
        "median_full_tokens": float(run["total_tokens"].median()),
        "median_latency_s": float(run["latency_s"].median()),
    }
    return run, meta


def augment_features(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["log_evt_cnt"] = np.log1p(out["evt_cnt_90d"].clip(lower=0))
    out["log_pool_n"] = np.log1p(out["pool_n"].clip(lower=0))
    out["log_n_bridge"] = np.log1p(out["n_bridge"].clip(lower=0))
    out["log_n_personal"] = np.log1p(out["n_personal"].clip(lower=0))
    return out


def check_feature_boundary(df: pd.DataFrame):
    bad = sorted(set(ROUTER_FEATURES) & LEAKAGE_COLUMNS)
    if bad:
        raise AssertionError(f"router feature list contains leakage columns: {bad}")
    missing = sorted(set(ROUTER_FEATURES) - set(df.columns))
    if missing:
        raise ValueError(f"event table missing router features: {missing}")
    values = df[ROUTER_FEATURES].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy(float)).all():
        raise ValueError("non-finite value in selector feature matrix")


def policy_outcome(df: pd.DataFrame, selected: np.ndarray) -> np.ndarray:
    return df["cheap_rr"].to_numpy(float) + selected.astype(float) * df["gain_full"].to_numpy(float)


def metric_row(df: pd.DataFrame, strategy: str, budget: float,
               selected: np.ndarray, score_col: str | None = None) -> dict:
    n = len(df)
    weights = df["eval_weight"].to_numpy(float)
    gain = df["gain_full"].to_numpy(float)
    tokens = df["total_tokens"].to_numpy(float)
    latency = df["latency_s"].to_numpy(float)
    out = policy_outcome(df, selected)
    selected_w = float(np.sum(weights[selected]))
    all_w = float(np.sum(weights))
    positive = gain > 0
    negative = gain < 0
    pos_w = float(np.sum(weights[positive]))
    selected_pos_w = float(np.sum(weights[selected & positive]))
    selected_neg_w = float(np.sum(weights[selected & negative]))
    positive_gain_total = float(np.sum(weights[positive] * gain[positive]))
    positive_gain_selected = float(np.sum(weights[selected & positive] * gain[selected & positive]))
    selected_token_weight = float(np.sum(weights[selected] * tokens[selected]))
    selected_latency_weight = float(np.sum(weights[selected] * latency[selected]))
    denom_tokens = selected_token_weight / all_w if all_w else float("nan")
    gain_w = weighted_mean(selected.astype(float) * gain, weights)
    return {
        "strategy": strategy,
        "budget": float(budget),
        "n_events": int(n),
        "n_selected": int(selected.sum()),
        "selected_rate": float(selected.mean()),
        "mrr_weighted": weighted_mean(out, weights),
        "mrr_unweighted": float(np.mean(out)) if n else float("nan"),
        "delta_mrr_vs_allcheap": gain_w,
        "positive_gain_precision": float(selected_pos_w / selected_w) if selected_w else float("nan"),
        "positive_gain_recall": float(selected_pos_w / pos_w) if pos_w else float("nan"),
        "useful_event_precision": float(selected_pos_w / selected_w) if selected_w else float("nan"),
        "useful_event_recall": float(selected_pos_w / pos_w) if pos_w else float("nan"),
        "positive_gain_capture": float(positive_gain_selected / positive_gain_total)
        if positive_gain_total > 0 else float("nan"),
        "harm_rate_selected": float(selected_neg_w / selected_w) if selected_w else float("nan"),
        "mean_gain_selected": float(np.mean(gain[selected])) if selected.any() else float("nan"),
        "weighted_gain_selected": weighted_mean(gain[selected], weights[selected]) if selected.any() else float("nan"),
        "selected_tokens_sum": float(tokens[selected].sum()),
        "selected_tokens_mean": float(tokens[selected].mean()) if selected.any() else float("nan"),
        "selected_token_share_all_full": float(tokens[selected].sum() / tokens.sum()) if tokens.sum() else float("nan"),
        "selected_latency_sum_s": float(latency[selected].sum()),
        "selected_latency_mean_s": float(latency[selected].mean()) if selected.any() else float("nan"),
        "weighted_tokens_per_event": denom_tokens,
        "mrr_gain_per_1k_selected_tokens": float(gain_w / (denom_tokens / 1000.0))
        if np.isfinite(denom_tokens) and denom_tokens > 0 else float("nan"),
        "score_col": score_col,
    }


def bootstrap_delta(df: pd.DataFrame, selected_a: np.ndarray,
                     selected_b: np.ndarray, n_boot: int, seed: int) -> dict:
    weights = df["eval_weight"].to_numpy(float)
    d = policy_outcome(df, selected_a) - policy_outcome(df, selected_b)
    valid = np.isfinite(d) & np.isfinite(weights) & (weights > 0)
    d, weights = d[valid], weights[valid]
    point = weighted_mean(d, weights)
    if len(d) < 2 or n_boot <= 0:
        return {"delta_mrr": point, "ci95": [float("nan"), float("nan")], "n": int(len(d))}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    wb = weights[idx]
    db = d[idx]
    vals = np.sum(wb * db, axis=1) / np.sum(wb, axis=1)
    return {
        "delta_mrr": float(point),
        "ci95": [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))],
        "n": int(len(d)),
    }


def select_top(df: pd.DataFrame, score_col: str, k: int) -> np.ndarray:
    k = max(0, min(int(k), len(df)))
    flag = np.zeros(len(df), dtype=bool)
    if k:
        ordered_index = sort_order(df, score_col)[:k]
        positions = df.index.get_indexer(ordered_index)
        if (positions < 0).any():
            raise ValueError("selector order contains an index outside the frame")
        flag[positions] = True
    return flag


def random_flags(df: pd.DataFrame, k: int, seed: int) -> np.ndarray:
    flag = np.zeros(len(df), dtype=bool)
    if k:
        flag[np.random.default_rng(seed).choice(len(df), k, replace=False)] = True
    return flag


def build_policy_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["degree"] = out["degree_score"]
    out["pagerank"] = out["pagerank_score"]
    out["activity"] = np.log1p(out["evt_cnt_90d"].clip(lower=0))
    out["volume"] = out["volume_score"]
    out["repeat"] = out["cp_type_repeat"].astype(float)
    out["cheap_uncertainty"] = out["cheap_score_entropy"]
    out["cheap_margin"] = -out["cheap_margin"]
    out["cheap_topscore"] = -out["cheap_top_score"]
    # Oracle is diagnostic only: it sorts by realized operational gain and
    # must never enter training or the deployable-baseline comparison.
    out["oracle_score"] = out["gain_full"]
    if "static_pagerank" in out:
        out["static_pagerank"] = _safe_float(out["static_pagerank"], 0)
        out["static_degree"] = _safe_float(out["static_degree"], 0)
    return out


def evaluate_curve(df: pd.DataFrame, split: str, scores: Mapping[str, str],
                    budgets: Sequence[float], random_draws: int,
                    seed: int) -> Tuple[pd.DataFrame, Dict[Tuple[str, float], np.ndarray], dict]:
    rows = []
    flags: Dict[Tuple[str, float], np.ndarray] = {}
    random_spread = []
    allcheap = metric_row(
        df, "all_cheap", 0.0, np.zeros(len(df), dtype=bool), None
    )
    allfull = metric_row(
        df, "all_full", 1.0, np.ones(len(df), dtype=bool), None
    )
    rows.extend([
        {"split": split, **allcheap},
        {"split": split, **allfull},
    ])
    for budget in budgets:
        k = max(1, int(round(float(budget) * len(df))))
        for name, col in scores.items():
            f = select_top(df, col, k)
            flags[(name, float(budget))] = f
            rows.append({"split": split, **metric_row(df, name, budget, f, col)})
        # Random is an expectation over fixed-budget draws, not one lucky seed.
        random_metrics = []
        for rep in range(random_draws):
            f = random_flags(df, k, deterministic_seed(seed, split, budget, rep))
            if rep == 0:
                flags[("random", float(budget))] = f
            random_metrics.append(metric_row(df, "random", budget, f, None))
        rnd = pd.DataFrame(random_metrics)
        aggregate = {"split": split, "strategy": "random", "budget": float(budget),
                     "n_events": len(df), "n_selected": k, "selected_rate": k / len(df),
                     "mrr_weighted": float(rnd.mrr_weighted.mean()),
                     "mrr_unweighted": float(rnd.mrr_unweighted.mean()),
                     "delta_mrr_vs_allcheap": float(rnd.delta_mrr_vs_allcheap.mean()),
                     "positive_gain_precision": float(rnd.positive_gain_precision.mean()),
                     "positive_gain_recall": float(rnd.positive_gain_recall.mean()),
                     "useful_event_precision": float(rnd.useful_event_precision.mean()),
                     "useful_event_recall": float(rnd.useful_event_recall.mean()),
                     "positive_gain_capture": float(rnd.positive_gain_capture.mean()),
                     "harm_rate_selected": float(rnd.harm_rate_selected.mean()),
                     "mean_gain_selected": float(rnd.mean_gain_selected.mean()),
                     "weighted_gain_selected": float(rnd.weighted_gain_selected.mean()),
                     "selected_tokens_sum": float(rnd.selected_tokens_sum.mean()),
                     "selected_tokens_mean": float(rnd.selected_tokens_mean.mean()),
                     "selected_token_share_all_full": float(rnd.selected_token_share_all_full.mean()),
                     "selected_latency_sum_s": float(rnd.selected_latency_sum_s.mean()),
                     "selected_latency_mean_s": float(rnd.selected_latency_mean_s.mean()),
                     "weighted_tokens_per_event": float(rnd.weighted_tokens_per_event.mean()),
                     "mrr_gain_per_1k_selected_tokens": float(rnd.mrr_gain_per_1k_selected_tokens.mean()),
                     "score_col": None,
                     "random_mrr_std": float(rnd.mrr_weighted.std(ddof=1)),
                     "random_draws": int(random_draws)}
        rows.append(aggregate)
        random_spread.append({"split": split, "budget": float(budget),
                              "mrr_mean": aggregate["mrr_weighted"],
                              "mrr_std": aggregate["random_mrr_std"],
                              "random_draws": random_draws})
    return pd.DataFrame(rows), flags, {"random_spread": random_spread}


def tune_model(train: pd.DataFrame, valid: pd.DataFrame, budgets: Sequence[float],
               seed: int) -> Tuple[dict, HistGradientBoostingRegressor, pd.DataFrame]:
    grid = []
    for max_iter in (50, 100, 200):
        for max_depth in (3, 6, None):
            grid.append((max_iter, max_depth))
    rows = []
    best = None
    xtr = train[ROUTER_FEATURES].to_numpy(float)
    ytr = train["gain_full"].to_numpy(float)
    for max_iter, max_depth in grid:
        model = HistGradientBoostingRegressor(
            max_iter=max_iter, max_depth=max_depth, learning_rate=0.05,
            l2_regularization=1.0, random_state=seed,
        )
        model.fit(xtr, ytr)
        pred = model.predict(valid[ROUTER_FEATURES].to_numpy(float))
        tmp = valid.copy()
        tmp["learned_score"] = pred
        mrrs = []
        for b in budgets:
            f = select_top(tmp, "learned_score", max(1, int(round(b * len(tmp)))))
            mrrs.append(weighted_mean(policy_outcome(tmp, f), tmp.eval_weight))
        mean_mrr = float(np.mean(mrrs))
        row = {"max_iter": max_iter, "max_depth": max_depth,
               "validation_mean_mrr": mean_mrr,
               **{f"validation_mrr_b{int(b*100):02d}": v for b, v in zip(budgets, mrrs)}}
        rows.append(row)
        # Deterministic tie-break: simpler model wins if utility is equal.
        key = (mean_mrr, -max_iter, -(max_depth if max_depth is not None else 999))
        if best is None or key > best[0]:
            best = (key, row)
    assert best is not None
    chosen = best[1]
    final_model = HistGradientBoostingRegressor(
        max_iter=int(chosen["max_iter"]), max_depth=chosen["max_depth"],
        learning_rate=0.05, l2_regularization=1.0, random_state=seed,
    )
    combined = pd.concat([train, valid], ignore_index=True)
    final_model.fit(combined[ROUTER_FEATURES].to_numpy(float), combined["gain_full"].to_numpy(float))
    return chosen, final_model, pd.DataFrame(rows).sort_values("validation_mean_mrr", ascending=False)


def parse_run_specs(specs: Sequence[str]) -> Dict[str, Path]:
    out = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"run must be MONTH=PATH, got {spec}")
        month, path = spec.split("=", 1)
        if month in out:
            raise ValueError(f"duplicate run month {month}")
        out[month] = Path(path)
    return out


def join_runs(events: pd.DataFrame, run_specs: Mapping[str, Path]) -> Tuple[pd.DataFrame, List[dict]]:
    frames = []
    metas = []
    for month, path in sorted(run_specs.items()):
        run, meta = load_run(month, path)
        metas.append(meta)
        frames.append(run)
    allrun = pd.concat(frames, ignore_index=True)
    out = events.merge(allrun, on=EVENT_KEY, how="inner", validate="one_to_one", suffixes=("", "_run"))
    if len(out) != len(allrun):
        raise ValueError(f"joined {len(out)} event rows but have {len(allrun)} run rows")
    if len(out) != len(events[events.snapshot_date.isin(run_specs)]):
        missing = len(events[events.snapshot_date.isin(run_specs)]) - len(out)
        raise ValueError(f"{missing} scored events lack a run row")
    out["eval_weight"] = _safe_float(out.get("pop_weight_run", out["pop_weight"]), 1.0)
    out["eval_weight"] = out["eval_weight"].clip(lower=1e-9)
    out["month"] = out["snapshot_date"].astype(str)
    # All rows used for effectiveness need a supported truth.
    # Keep unsupported rows for the audit, then filter in main.
    return out, metas


def calibration(df: pd.DataFrame, score_col: str = "learned_score") -> Tuple[pd.DataFrame, float]:
    d = df.copy()
    d["decile"] = pd.qcut(d[score_col], 10, labels=False, duplicates="drop")
    rows = []
    for decile, g in d.groupby("decile", observed=True):
        rows.append({
            "decile": int(decile), "n": int(len(g)),
            "predicted_score_mean": float(g[score_col].mean()),
            "realized_gain_mean": float(g["gain_full"].mean()),
            "positive_gain_rate": float((g["gain_full"] > 0).mean()),
            "harm_rate": float((g["gain_full"] < 0).mean()),
        })
    return pd.DataFrame(rows), rank_corr(d[score_col], d["gain_full"])


def write_report(outdir: Path, manifest: dict, curves: pd.DataFrame,
                 paired: pd.DataFrame, strata: pd.DataFrame,
                 calibration_df: pd.DataFrame, go_no_go: dict):
    test = curves[(curves["split"] == "test") & curves["budget"].between(0.049, 0.751)]
    primary = test[np.isclose(test["budget"], PRIMARY_BUDGET)]
    baseline_names = manifest.get("comparison_baselines", NONLEARNING)
    stage_issue_count = 0
    stage_client_errors = 0
    internal_fallbacks = 0
    for audit in manifest.get("run_audit", []):
        stage_client_errors += int(audit.get("stage_client_error_total", 0))
        internal_fallbacks += int(audit.get("internal_fallback_total", 0))
        for counts in audit.get("stage_status_counts", {}).values():
            stage_issue_count += sum(v for k, v in counts.items() if k != "ok")
    lines = [
        "# Node-selection v2 go/no-go report",
        "",
        "## Scope",
        "",
        "Primary selection unit: one target-wallet prediction event at a snapshot. A selected event receives the full deliberation arm; an unselected event keeps the cheap ranker. A separate event-to-wallet aggregation is exported for the next recursive-reasoning stage. This report does not evaluate recursive depth or higher-order operators.",
        "",
        "The operational full-arm gain is `full_rr_operational - cheap_rr`; parse failures fall back to cheap and therefore contribute zero gain.",
        "",
        "Baseline definitions: `degree` uses the maximum as-of candidate global count; `pagerank` is the corresponding as-of global-popularity-rank proxy, not the released static PageRank; `activity` uses target `evt_cnt_90d`; `volume` sums candidate global counts. `oracle` is reported only as a realized-gain upper bound.",
        "",
        "## Protocol and audit",
        "",
        f"- train: `{manifest['splits']['train']}`; validation/tuning: `{manifest['splits']['validation']}`; frozen test: `{manifest['splits']['test']}`; extra time-out: `{manifest['splits'].get('extra_test')}`",
        f"- budgets: {', '.join(f'{int(x*100)}%' for x in manifest['budgets'])}; primary budget: {int(PRIMARY_BUDGET*100)}%",
        f"- router features: {len(ROUTER_FEATURES)} pre-call features; leakage audit: `{manifest['feature_boundary']['status']}`",
        f"- run model sets: {manifest['run_models']}",
        f"- per-step audit: {stage_issue_count} non-`ok` stage statuses retained by deterministic fallback; client errors={stage_client_errors}; internal fallbacks={internal_fallbacks}",
        "",
        "## Frozen test curve",
        "",
        "| budget | learned MRR | best non-learning MRR | delta learned-best | learned positive precision | learned harm rate | learned tokens/event |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in manifest["budgets"]:
        r = test[np.isclose(test["budget"], b)]
        lr = r[r.strategy == "learned"].iloc[0]
        non = r[r.strategy.isin(baseline_names)]
        br = non.loc[non.mrr_weighted.idxmax()]
        lines.append(
            f"| {int(b*100)}% | {lr.mrr_weighted:.4f} | {br.mrr_weighted:.4f} ({br.strategy}) | {lr.mrr_weighted-br.mrr_weighted:+.4f} | {lr.positive_gain_precision:.3f} | {lr.harm_rate_selected:.3f} | {lr.weighted_tokens_per_event:.1f} |"
        )
    extra = curves[(curves["split"] == "extra_test") & curves["budget"].between(0.049, 0.751)]
    if not extra.empty:
        lines += ["", "## Extra time-out curve (not used for tuning)", "",
                  "| budget | learned MRR | best non-learning MRR | best baseline |", "|---:|---:|---:|---|"]
        for b in manifest["budgets"]:
            r = extra[np.isclose(extra["budget"], b)]
            lr = r[r.strategy == "learned"].iloc[0]
            non = r[r.strategy.isin(baseline_names)]
            br = non.loc[non.mrr_weighted.idxmax()]
            lines.append(f"| {int(b*100)}% | {lr.mrr_weighted:.4f} | {br.mrr_weighted:.4f} | {br.strategy} |")
    lines += ["", "## Primary paired bootstrap comparisons on frozen test", "",
              "| comparator | delta MRR (learned - comparator) | 95% CI |", "|---|---:|---:|"]
    p = paired[paired["budget"].eq(PRIMARY_BUDGET)]
    for _, r in p.iterrows():
        lines.append(f"| {r.comparator} | {r.delta_mrr:+.4f} | [{r.ci_low:+.4f}, {r.ci_high:+.4f}] |")
    lines += ["", "## Go/no-go", "", f"**Decision: `{go_no_go['decision']}`**", "", go_no_go["reason"], ""]
    lines += ["## Test strata at 50%", "", "| stratum | strategy | MRR | gain vs cheap | positive precision | harm rate | n selected |", "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in strata.sort_values(["stratum", "strategy"]).iterrows():
        lines.append(f"| {r.stratum} | {r.strategy} | {r.mrr_weighted:.4f} | {r.delta_mrr_vs_allcheap:+.4f} | {r.positive_gain_precision:.3f} | {r.harm_rate_selected:.3f} | {int(r.n_selected)} |")
    lines += ["", "## Learned-score calibration on frozen test", "", "| decile | n | predicted score | realized gain | positive rate | harm rate |", "|---:|---:|---:|---:|---:|---:|"]
    for _, r in calibration_df.iterrows():
        lines.append(f"| {int(r.decile)} | {int(r.n)} | {r.predicted_score_mean:+.4f} | {r.realized_gain_mean:+.4f} | {r.positive_gain_rate:.3f} | {r.harm_rate:.3f} |")
    lines += ["", "## Claim boundary", "", "A pass supports selecting events that are worth allocating the measured deliberation budget under this candidate pool and model protocol. It does not prove that a wallet is causally influential, that X activity caused a transaction, or that recursive reasoning will improve results. Those are separate experiments.", ""]
    (outdir / "node-selection-go-no-go.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", default="artifacts/llm_panel_v2/panel_scored_v2.csv.gz")
    ap.add_argument("--run", nargs="+", required=True, help="MONTH=RUN.csv")
    ap.add_argument("--outdir", default="artifacts/llm_panel_v2/node_selection_v2")
    ap.add_argument("--structural", default=None, help="optional static structural CSV for sensitivity only")
    ap.add_argument("--train", default="2022-06-01")
    ap.add_argument("--validation", default="2022-07-01")
    ap.add_argument("--test", default="2022-08-01")
    ap.add_argument("--extra-test", default="2022-09-01")
    ap.add_argument("--budgets", default="0.05,0.10,0.20,0.50,0.75")
    ap.add_argument("--random-draws", type=int, default=200)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260910)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    budgets = tuple(float(x) for x in args.budgets.split(",") if x.strip())
    if not budgets or any(x <= 0 or x > 1 for x in budgets):
        raise ValueError("budgets must be fractions in (0,1]")
    run_specs = parse_run_specs(args.run)

    scored, events = load_scored(Path(args.scored))
    events, structural_audit = add_structural_sensitivity(
        scored, events, Path(args.structural) if args.structural else None
    )
    joined, run_meta = join_runs(events, run_specs)
    support_before = int(len(joined))
    support = joined[joined["truth_in_pool"].astype(int) == 1].copy()
    if support.empty:
        raise ValueError("no supported events after truth_in_pool filter")
    support = augment_features(support)
    check_feature_boundary(support)
    if not np.isfinite(support["gain_full"].to_numpy(float)).all():
        raise ValueError("non-finite operational gain")

    available = set(support["snapshot_date"].astype(str))
    for required_month in (args.train, args.validation, args.test):
        if required_month not in available:
            raise ValueError(f"required split {required_month} absent from run inputs")
    train = support[support.snapshot_date.astype(str) == args.train].copy()
    valid = support[support.snapshot_date.astype(str) == args.validation].copy()
    test = support[support.snapshot_date.astype(str) == args.test].copy()
    extra = support[support.snapshot_date.astype(str) == args.extra_test].copy() if args.extra_test in available else None
    for name, frame in [("train", train), ("validation", valid), ("test", test)]:
        if frame.empty:
            raise ValueError(f"empty {name} split")

    chosen, model, tune_table = tune_model(train, valid, budgets, args.seed)
    def score_frame(frame):
        frame = frame.copy()
        frame["learned_score"] = model.predict(frame[ROUTER_FEATURES].to_numpy(float))
        return build_policy_scores(frame)
    train = score_frame(train)
    valid = score_frame(valid)
    test = score_frame(test)
    if extra is not None:
        extra = score_frame(extra)

    scores = {name: name for name in NONLEARNING if name != "random"}
    scores["learned"] = "learned_score"
    scores["oracle"] = "oracle_score"
    if "static_pagerank" in test.columns:
        scores["static_pagerank"] = "static_pagerank"
    if "static_degree" in test.columns:
        scores["static_degree"] = "static_degree"
    comparison_baselines = list(NONLEARNING)
    for optional_name in ("static_pagerank", "static_degree"):
        if optional_name in scores:
            comparison_baselines.append(optional_name)

    curve_parts = []
    flag_sets = {}
    random_spread = []
    for split_name, frame in [("train", train), ("validation", valid), ("test", test)] + ([ ("extra_test", extra) ] if extra is not None else []):
        curve, flags, aux = evaluate_curve(frame, split_name, scores, budgets, args.random_draws, args.seed)
        curve_parts.append(curve)
        random_spread.extend(aux["random_spread"])
        for key, flag in flags.items():
            flag_sets[(split_name, key[0], key[1])] = flag
    curves = pd.concat(curve_parts, ignore_index=True)

    # Paired bootstrap on frozen test at every requested budget.  Random uses
    # the first fixed draw; the curve itself reports the repeated expectation.
    paired_rows = []
    for b in budgets:
        learned_flag = flag_sets[("test", "learned", float(b))]
        comparators = list(comparison_baselines)
        for comp in comparators:
            comp_flag = flag_sets[("test", comp, float(b))]
            ci = bootstrap_delta(test, learned_flag, comp_flag, args.bootstrap,
                                 deterministic_seed(args.seed, "paired", b, comp))
            paired_rows.append({"budget": float(b), "comparator": comp,
                                "delta_mrr": ci["delta_mrr"],
                                "ci_low": ci["ci95"][0], "ci_high": ci["ci95"][1],
                                "n": ci["n"]})
    paired = pd.DataFrame(paired_rows)

    # Stratum audit at the primary budget, including learned and the strongest
    # non-learning baselines.  No stratum is used for model training.
    strata_rows = []
    k = max(1, int(round(PRIMARY_BUDGET * len(test))))
    strategies_for_strata = ["learned"] + comparison_baselines
    for stratum, sub in test.groupby("stratum", dropna=False, sort=True):
        # Use the global selection order then intersect; this is how a global
        # budget policy behaves, not an independently quota-balanced policy.
        parent_idx = test.index.get_indexer(sub.index)
        for strategy in strategies_for_strata:
            if strategy == "random":
                global_flag = flag_sets[("test", "random", PRIMARY_BUDGET)]
            else:
                global_flag = flag_sets[("test", strategy, PRIMARY_BUDGET)]
            local_flag = global_flag[parent_idx]
            row = metric_row(sub.reset_index(drop=True), strategy, PRIMARY_BUDGET, local_flag,
                             None if strategy == "random" else (strategy if strategy != "learned" else "learned_score"))
            strata_rows.append({"stratum": str(stratum), **row})
    strata = pd.DataFrame(strata_rows)

    cal_df, cal_spearman = calibration(test)
    test_primary = curves[(curves.split == "test") & np.isclose(curves.budget, PRIMARY_BUDGET)]
    non = test_primary[test_primary.strategy.isin(comparison_baselines)]
    best_non = non.loc[non.mrr_weighted.idxmax()]
    learned_primary = test_primary[test_primary.strategy == "learned"].iloc[0]
    best_comp = paired[(paired.budget == PRIMARY_BUDGET) & (paired.comparator == best_non.strategy)].iloc[0]
    budget_wins = []
    for b in budgets:
        rb = curves[(curves.split == "test") & np.isclose(curves.budget, b)]
        lr = rb[rb.strategy == "learned"].mrr_weighted.iloc[0]
        bn = rb[rb.strategy.isin(comparison_baselines)].mrr_weighted.max()
        budget_wins.append(bool(lr > bn))
    model_sets = sorted({m for meta in run_meta for m in meta["models"]})
    model_consistent = len(model_sets) <= 1
    if not model_consistent:
        decision = "CONDITIONAL_MIXED_MODEL"
        reason = (f"The learned selector {'beats' if learned_primary.mrr_weighted > best_non.mrr_weighted else 'does not beat'} the best non-learning baseline at 50% on the frozen test ({best_non.strategy}), but the supplied runs use mixed model identities {model_sets}. Re-run all temporal splits with one authorized model before claiming a clean primary result.")
    elif learned_primary.mrr_weighted > best_non.mrr_weighted and best_comp.ci_low > 0 and sum(budget_wins) >= 3 and cal_spearman > 0:
        decision = "GO_STAGE_2_RECURSIVE_REASONING"
        reason = (f"Learned selection beats the best non-learning baseline ({best_non.strategy}) at the primary 50% budget with a paired bootstrap CI excluding zero; it wins at {sum(budget_wins)}/{len(budget_wins)} budgets and has positive frozen-test score/gain rank correlation ({cal_spearman:.3f}).")
    else:
        decision = "NO_GO_REVISE_SELECTION"
        reason = (f"The frozen-test gate was not met: primary learned-vs-best delta={learned_primary.mrr_weighted-best_non.mrr_weighted:+.4f}, CI=[{best_comp.ci_low:+.4f},{best_comp.ci_high:+.4f}], budget wins={sum(budget_wins)}/{len(budget_wins)}, calibration rank correlation={cal_spearman:.3f}. Keep recursive reasoning frozen and revise the selector or data protocol.")
    go_no_go = {
        "decision": decision,
        "reason": reason,
        "primary_budget": PRIMARY_BUDGET,
        "learned_primary_mrr": float(learned_primary.mrr_weighted),
        "best_nonlearning": str(best_non.strategy),
        "best_nonlearning_mrr": float(best_non.mrr_weighted),
        "primary_delta": float(learned_primary.mrr_weighted - best_non.mrr_weighted),
        "primary_ci": [float(best_comp.ci_low), float(best_comp.ci_high)],
        "budget_wins": {str(b): bool(w) for b, w in zip(budgets, budget_wins)},
        "calibration_spearman": float(cal_spearman),
        "model_consistent": model_consistent,
    }

    feature_boundary = {
        "status": "PASS",
        "router_features": ROUTER_FEATURES,
        "excluded_columns": sorted(LEAKAGE_COLUMNS),
        "evaluation_weight_excluded": True,
        "static_sensitivity_not_in_router": True,
    }
    manifest = {
        "created_at": "2026-09-10",
        "protocol": "event-level deliberation selection; operational full-arm gain with fallback",
        "scored_panel": str(Path(args.scored)),
        "runs": {k: str(v) for k, v in sorted(run_specs.items())},
        "splits": {"train": args.train, "validation": args.validation, "test": args.test, "extra_test": args.extra_test if extra is not None else None},
        "budgets": list(budgets),
        "primary_budget": PRIMARY_BUDGET,
        "random_draws": args.random_draws,
        "bootstrap": args.bootstrap,
        "selector": {"model": "HistGradientBoostingRegressor", "features": ROUTER_FEATURES, "tuned_on": args.validation, "refit_on": [args.train, args.validation], "chosen": chosen},
        "feature_boundary": feature_boundary,
        "structural_sensitivity": structural_audit,
        "score_definitions": {
            "degree": "max log1p(as-of candidate g_cnt) over the event pool",
            "pagerank": "as-of global-popularity rank proxy: max -log(g_rank); not released static PageRank",
            "activity": "log1p(target wallet evt_cnt_90d)",
            "volume": "log1p(sum as-of candidate g_cnt over the event pool)",
            "repeat": "cp_type_repeat",
            "cheap_uncertainty": "candidate-pool mean Bernoulli entropy of cheap scores",
            "cheap_margin": "negative cheap top-1 minus top-2 margin",
            "cheap_topscore": "negative cheap top score",
            "learned": "HistGradientBoosting predicted operational full-arm gain",
            "oracle": "realized operational gain; upper bound only, never deployable",
        },
        "comparison_baselines": comparison_baselines,
        "run_models": {m["month"]: m["models"] for m in run_meta},
        "model_identity_set": model_sets,
        "support_before_filter": support_before,
        "support_after_filter": int(len(support)),
        "run_audit": run_meta,
        "downstream_freeze": {
            "event_input": "frozen_test_selector_input.csv",
            "node_input_b50": "frozen_test_important_nodes_b50.csv",
            "outcome_audit": "frozen_test_outcomes_for_audit.csv",
            "node_aggregation": "event_to_wallet_max_and_mean_learned_score; descriptive hand-off only",
        },
        "go_no_go": go_no_go,
    }

    # Persist auditable artifacts.
    curves.to_csv(outdir / "selection_curves.csv", index=False)
    paired.to_csv(outdir / "paired_bootstrap_test.csv", index=False)
    strata.to_csv(outdir / "strata_test_b50.csv", index=False)
    cal_df.to_csv(outdir / "calibration_test.csv", index=False)
    tune_table.to_csv(outdir / "validation_tuning_grid.csv", index=False)
    pd.DataFrame(random_spread).to_csv(outdir / "random_seed_spread.csv", index=False)
    # This file is the actual downstream hand-off: only pre-call features and
    # deployable policy scores.  Outcome columns stay in a separate audit file
    # so they cannot accidentally leak into recursive-reasoning input.
    deployable_score_cols = [c for name, c in scores.items()
                             if name != "oracle" and c in test.columns]
    freeze_cols = EVENT_KEY + ROUTER_FEATURES + deployable_score_cols
    freeze_cols = list(dict.fromkeys([c for c in freeze_cols if c in test.columns]))
    test[freeze_cols].sort_values(EVENT_KEY).to_csv(outdir / "frozen_test_selector_input.csv", index=False)
    outcome_cols = EVENT_KEY + ["stratum", "cp_type", "cheap_rr", "gain_full",
                                "full_rr_operational", "nocf_rr_operational",
                                "total_tokens", "latency_s", "truth_in_pool"]
    outcome_cols = list(dict.fromkeys([c for c in outcome_cols if c in test.columns]))
    test[outcome_cols].sort_values(EVENT_KEY).to_csv(
        outdir / "frozen_test_outcomes_for_audit.csv", index=False
    )
    # Event-to-wallet hand-off for downstream recursive reasoning.  This is a
    # pre-call aggregation only: it contains no realized gain, truth rank, or
    # post-call token/outcome field.  It is not the primary event-level metric.
    node_frame = test[["snapshot_date", "target_address", "learned_score"]].copy()
    node_frame["selected_event_b50"] = flag_sets[("test", "learned", PRIMARY_BUDGET)].astype(int)
    node = node_frame.groupby(["snapshot_date", "target_address"], sort=False).agg(
        event_count=("learned_score", "size"),
        selected_event_count=("selected_event_b50", "sum"),
        learned_score_max=("learned_score", "max"),
        learned_score_mean=("learned_score", "mean"),
    ).reset_index()
    node["selected_event_rate"] = node["selected_event_count"] / node["event_count"].clip(lower=1)
    node = node.sort_values(["learned_score_max", "learned_score_mean", "target_address"],
                            ascending=[False, False, True], kind="mergesort").reset_index(drop=True)
    node["node_rank"] = np.arange(1, len(node) + 1)
    node.to_csv(outdir / "frozen_test_important_nodes_b50.csv", index=False)

    with open(outdir / "learned_selector_frozen.pkl", "wb") as f:
        pickle.dump({"model": model, "features": ROUTER_FEATURES, "chosen": chosen,
                     "trained_on": [args.train, args.validation], "protocol": manifest["protocol"]}, f)
    (outdir / "manifest.json").write_text(json.dumps(_jsonable(manifest), indent=2), encoding="utf-8")
    (outdir / "go_no_go.json").write_text(json.dumps(_jsonable(go_no_go), indent=2), encoding="utf-8")
    write_report(outdir, manifest, curves, paired, strata, cal_df, go_no_go)

    print(json.dumps(_jsonable({
        "outdir": str(outdir), "decision": decision,
        "splits": manifest["splits"], "run_models": manifest["run_models"],
        "chosen": chosen, "primary": {
            "learned_mrr": learned_primary.mrr_weighted,
            "best_nonlearning": best_non.strategy,
            "best_nonlearning_mrr": best_non.mrr_weighted,
            "delta": learned_primary.mrr_weighted - best_non.mrr_weighted,
            "ci": [best_comp.ci_low, best_comp.ci_high],
        },
    }), indent=2))


if __name__ == "__main__":
    main()
