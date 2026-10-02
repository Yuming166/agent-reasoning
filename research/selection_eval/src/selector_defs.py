"""Selector registry for the budgeted wallet-selection benchmark.

Each selector maps (score_column, support) -> an ordering used to pick top-K.
All scores are computed ONLY from information available strictly before
cutoff 2022-09-01 (as-of features, frozen predictive/IG scores from Groups
B/D). Full-window static centrality is reported as a leaky-prior baseline
tier and is never used in headline claims.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Selector definitions
# ---------------------------------------------------------------------------
# key: machine name; label: human name; tier: §14 baseline tier
# score: column in the assembled frame (NaN = outside support)
# higher_is_better: direction of ranking
# support: which input file defines the support set
# scope: native scope used in the main table
# note: score definition / caveats
SELECTORS: dict[str, dict] = {
    # ---- Tier 1: full-support baselines (18,519) ----
    "random": {
        "label": "Random (seed=20220901)",
        "tier": "random", "score": "score_random", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "uniform random scores, fixed seed 20220901 (single draw; expectation K*mean also reported in frontier as random_expected).",
        "source": "in-house (deterministic seed)",
    },
    "volume": {
        "label": "Volume (evt_cnt_90d)",
        "tier": "size", "score": "evt_cnt_90d", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "90-day primary-event count as transaction-volume proxy (Group A feature matrix).",
        "source": "groupA feature_matrix_20220901.parquet",
    },
    "volume_usd": {
        "label": "Volume USD (native+token balance)",
        "tier": "size", "score": "vol_usd", "higher_is_better": True,
        "support": "usd", "scope": "usd",
        "note": "as-of USD-denominated capital proxy (native_usd+token_usd_priced) from Group A; balance-based, NOT flow. NaN (no priced row) => outside support.",
        "source": "groupA usd_capital_20220901.csv",
    },
    "eth_flow": {
        "label": "ETH flow (evt_native_90d)",
        "tier": "size", "score": "evt_native_90d", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "90-day native-ETH transfer event count as ETH-flow proxy (Group A feature matrix).",
        "source": "groupA feature_matrix_20220901.parquet",
    },
    "activity": {
        "label": "Activity (active_days_90d)",
        "tier": "temporal", "score": "active_days_90d", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "90-day active-day breadth (Group A feature matrix).",
        "source": "groupA feature_matrix_20220901.parquet",
    },
    "recency": {
        "label": "Recency (last_event_recency_days, inverted)",
        "tier": "temporal", "score": "score_recency", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "more recent last event = higher score; score = 90 - last_event_recency_days (Group A feature matrix).",
        "source": "groupA feature_matrix_20220901.parquet",
    },
    "persistence": {
        "label": "Persistence (active_span_days_90d)",
        "tier": "temporal", "score": "active_span_days_90d", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "90-day active span (Group A feature matrix).",
        "source": "groupA feature_matrix_20220901.parquet",
    },
    "behavioral": {
        "label": "Behavioral (cluster-internal volume rep)",
        "tier": "behavioral", "score": "behav_vol", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "Group A persona (full_asof__kmeans); within each cluster take the percentile rank of evt_cnt_90d so each persona contributes its volume-representatives.",
        "source": "groupA persona_assignments_20220901.csv + feature matrix",
    },
    "behavioral_act": {
        "label": "Behavioral (cluster-internal activity rep)",
        "tier": "behavioral", "score": "behav_act", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "same as behavioral but representative = cluster-internal percentile of active_days_90d.",
        "source": "groupA persona_assignments_20220901.csv + feature matrix",
    },
    "predictive_act": {
        "label": "Predictive (future activity level)",
        "tier": "predictive", "score": "pred_act", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "Group B frozen LightGBM level prediction for future activity (pred_act_level_LightGBM); model trained 06-01 / tuned 07-01 / frozen-test 08-01, applied at 09-01.",
        "source": "groupB holdout09_predictions.csv",
    },
    "predictive_new": {
        "label": "Predictive (future new counterparties)",
        "tier": "predictive", "score": "pred_new", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "Group B frozen LightGBM level prediction for future new counterparties (pred_new_level_LightGBM).",
        "source": "groupB holdout09_predictions.csv",
    },
    "hybrid_pred_vol": {
        "label": "Hybrid predictive+volume",
        "tier": "hybrid", "score": "hybrid_pred_vol", "higher_is_better": True,
        "support": "full", "scope": "full",
        "note": "rank-average of percentile ranks of pred_act_level and evt_cnt_90d.",
        "source": "groupB predictions + groupA feature matrix",
    },
    # ---- Tier 2: structural (7,929 matched-matched subgraph) ----
    "degree": {
        "label": "Degree (as-of undirected)",
        "tier": "structural", "score": "deg_und", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "as-of undirected degree on the matched-matched 7,929 subgraph built from events strictly before cutoff (Group C).",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "weighted_degree": {
        "label": "Weighted degree (as-of)",
        "tier": "structural", "score": "wdeg_und", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "as-of weighted undirected degree (Group C).",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "pagerank": {
        "label": "PageRank (as-of)",
        "tier": "structural", "score": "pagerank", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "as-of PageRank on matched-matched subgraph (Group C).",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "kcore": {
        "label": "k-core (as-of)",
        "tier": "structural", "score": "kcore", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "as-of k-core number (Group C).",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "betweenness": {
        "label": "Betweenness (as-of)",
        "tier": "structural", "score": "betweenness", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "as-of betweenness (Group C); extended structural baseline.",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "bridge_score": {
        "label": "Bridge score (as-of)",
        "tier": "structural", "score": "bridge_score", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "Group C community bridge score; extended structural baseline.",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "static_degree": {
        "label": "Static degree (full-window prior, LEAKY)",
        "tier": "structural_static_prior", "score": "static_degree", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "full-window static prior from ethereum_graph.gpickle; leaky prior baseline only (protocol: MUST NOT be used as as-of prediction feature). Reported separately.",
        "source": "groupC wallet_importance_20220901.csv",
    },
    "static_pagerank": {
        "label": "Static PageRank (full-window prior, LEAKY)",
        "tier": "structural_static_prior", "score": "static_pagerank", "higher_is_better": True,
        "support": "structural", "scope": "structural",
        "note": "full-window static PageRank prior; leaky prior baseline only.",
        "source": "groupC wallet_importance_20220901.csv",
    },
    # ---- Tier 3: information gain (2,999 subset) ----
    "ig_cp": {
        "label": "Info gain (fwd cp>=10)",
        "tier": "information", "score": "ig_cp", "higher_is_better": True,
        "support": "ig", "scope": "ig",
        "note": "wallet-level occurrence information gain for target fwd30_cp_distinct>=10, HistGBM, averaged over folds (Group D).",
        "source": "groupD ig_vs_baselines_20220901.csv",
    },
    "ig_active": {
        "label": "Info gain (fwd active)",
        "tier": "information", "score": "ig_active", "higher_is_better": True,
        "support": "ig", "scope": "ig",
        "note": "wallet-level occurrence IG for target fwd30_evt_cnt>0, HistGBM (Group D).",
        "source": "groupD ig_vs_baselines_20220901.csv",
    },
    "hybrid_pred_ig": {
        "label": "Hybrid predictive+IG",
        "tier": "hybrid", "score": "hybrid_pred_ig", "higher_is_better": True,
        "support": "ig", "scope": "ig",
        "note": "rank-average of percentile ranks of pred_act_level and ig_cp; restricted to the 2,999 IG subset.",
        "source": "groupB predictions + groupD IG",
    },
}


def add_random(base: pd.DataFrame, seed: int = 20220901) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = base.copy()
    base["score_random"] = rng.random(len(base))
    return base


def selector_keys() -> list[str]:
    return list(SELECTORS.keys())


def get_topk(base: pd.DataFrame, key: str, k: int) -> pd.DataFrame:
    """Return the top-K wallet rows for a selector (deterministic tie-break)."""
    spec = SELECTORS[key]
    col = spec["score"]
    df = base.dropna(subset=[col]).copy()
    if col == "score_recency":
        df["_score"] = 90.0 - df["last_event_recency_days"]
    elif col == "score_random":
        df["_score"] = df["score_random"]
    else:
        df["_score"] = df[col]
    if not spec["higher_is_better"]:
        df["_score"] = -df["_score"]
    df = df.sort_values(["_score", "target_address"], ascending=[False, True])
    return df.head(k)
