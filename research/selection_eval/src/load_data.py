"""Load reusable 2022-09-01 artifacts into one wallet-level frame (read-only inputs).

All inputs are Group A/B/C/D 09-01 outputs already on disk; NO BigQuery is
queried here (labels were pulled by Group B from the frozen as-of table).
"""
from __future__ import annotations
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# research/selection_eval/src -> research/selection_eval -> research -> repo root
REPO = os.path.dirname(os.path.dirname(ROOT))

PATHS = {
    "labels": "research/groupB_predictive/results/data/labels_20220901_bq.csv",
    "feature_matrix": "research/groupA_behavior/results/data/feature_matrix_20220901.parquet",
    "persona": "research/groupA_behavior/results/persona_assignments_20220901.csv",
    "usd_capital": "research/groupA_behavior/results/data/usd_capital_20220901.csv",
    "predictions": "research/groupB_predictive/results/holdout09_predictions.csv",
    "structural": "research/groupC_temporal_graph/results/data/wallet_importance_20220901.csv",
    "ig": "research/groupD_infogain/results/wallet_ig_20220901.csv",
    "asof_monthly": "research/groupA_behavior/results/data/asof_monthly_2022.parquet",
}


def load_base() -> pd.DataFrame:
    """Canonical 18,519-wallet universe with fwd30 labels (cutoff 2022-09-01)."""
    lbl = pd.read_csv(PATHS["labels"])
    assert lbl.target_address.nunique() == len(lbl) == 18519
    assert set(lbl.snapshot_date.unique()) <= {"2022-09-01"}
    lbl = lbl.rename(columns={
        "fwd30_evt_cnt": "lbl_evt",
        "fwd30_cp_distinct": "lbl_cp",
        "fwd30_new_cp": "lbl_new",
    })
    return lbl[["target_address", "lbl_evt", "lbl_cp", "lbl_new"]].copy()


def load_all() -> dict[str, pd.DataFrame]:
    """Return every raw input as a DataFrame keyed by source name."""
    out = {}
    out["labels"] = load_base()
    out["feature_matrix"] = pd.read_parquet(PATHS["feature_matrix"])
    out["persona"] = pd.read_csv(PATHS["persona"])
    out["usd_capital"] = pd.read_csv(PATHS["usd_capital"])
    out["predictions"] = pd.read_csv(PATHS["predictions"])
    out["structural"] = pd.read_csv(PATHS["structural"])
    out["ig"] = pd.read_csv(PATHS["ig"])
    out["asof_monthly"] = pd.read_parquet(PATHS["asof_monthly"])
    return out


def assemble_scores(raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Merge selector scores onto the canonical universe.

    Returns (frame, meta) where frame has one row per wallet in the 18,519
    universe plus selector-score columns (NaN where a wallet is outside a
    selector's support), and meta records per-selector support sizes.
    """
    base = raw["labels"].copy()

    fm = raw["feature_matrix"][["target_address", "evt_cnt_90d", "evt_native_90d",
                                "active_days_90d", "last_event_recency_days",
                                "active_span_days_90d", "cp_new_rate_30d",
                                "events_per_active_day_90d"]]
    base = base.merge(fm, on="target_address", how="left")

    pr = raw["predictions"][["target_address", "pred_act_level_LightGBM",
                             "pred_new_level_LightGBM"]]
    base = base.merge(pr.rename(columns={
        "pred_act_level_LightGBM": "pred_act",
        "pred_new_level_LightGBM": "pred_new"}), on="target_address", how="left")

    pa = raw["persona"][["target_address", "full_asof__kmeans", "trajectory__kmeans"]]
    base = base.merge(pa, on="target_address", how="left")

    uc = raw["usd_capital"][["target_address", "native_usd", "token_usd_priced"]]
    base = base.merge(uc, on="target_address", how="left")
    has_usd = base["native_usd"].notna() | base["token_usd_priced"].notna()
    base["vol_usd"] = np.nan
    base.loc[has_usd, "vol_usd"] = (base["native_usd"].fillna(0.0) + base["token_usd_priced"].fillna(0.0))[has_usd]

    st = raw["structural"][["target_address", "deg_und", "wdeg_und", "pagerank", "kcore",
                            "betweenness", "bridge_score", "static_degree",
                            "static_pagerank"]]
    base = base.merge(st, on="target_address", how="left")

    ig = raw["ig"].copy()
    ig_cp = ig[(ig["target"] == "y_cp_ge10") & (ig["model"] == "histgbm")].set_index("target_address")["ig_occ"]
    ig_act = ig[(ig["target"] == "y_active30") & (ig["model"] == "histgbm")].set_index("target_address")["ig_occ"]
    base["ig_cp"] = base["target_address"].map(ig_cp)
    base["ig_active"] = base["target_address"].map(ig_act)

    # ---- derived scores ----
    # behavioral: within-cluster percentile of volume / activity (cluster reps)
    base["behav_vol"] = np.nan
    base["behav_act"] = np.nan
    for cl in sorted(base["full_asof__kmeans"].dropna().unique()):
        m = base["full_asof__kmeans"] == cl
        base.loc[m, "behav_vol"] = base.loc[m, "evt_cnt_90d"].rank(pct=True)
        base.loc[m, "behav_act"] = base.loc[m, "active_days_90d"].rank(pct=True)

    # hybrid: mean of percentile ranks of components
    base["pct_pred_act"] = base["pred_act"].rank(pct=True)
    base["pct_vol"] = base["evt_cnt_90d"].rank(pct=True)
    base["pct_ig_cp"] = base["ig_cp"].rank(pct=True)
    base["score_recency"] = 90.0 - base["last_event_recency_days"]
    base["hybrid_pred_vol"] = (base["pct_pred_act"] + base["pct_vol"]) / 2.0
    base["hybrid_pred_ig"] = (base["pct_pred_act"] + base["pct_ig_cp"]) / 2.0

    meta = {
        "labels": {"n": 18519, "source": "groupB labels_20220901_bq.csv (frozen wallet_asof_features_20220901)"},
        "feature_matrix": {"n": int(base["evt_cnt_90d"].notna().sum()), "source": "groupA feature_matrix_20220901.parquet"},
        "usd_capital": {"n": int(base["vol_usd"].notna().sum()), "source": "groupA usd_capital_20220901.csv"},
        "predictions": {"n": int(base["pred_act"].notna().sum()), "source": "groupB holdout09_predictions.csv"},
        "persona": {"n": int(base["full_asof__kmeans"].notna().sum()), "source": "groupA persona_assignments_20220901.csv"},
        "structural": {"n": int(base["deg_und"].notna().sum()), "source": "groupC wallet_importance_20220901.csv"},
        "ig": {"n": int(base["ig_cp"].notna().sum()), "source": "groupD wallet_ig_20220901.csv, ig_occ aggregated by target+model (2,999 subset)"},
    }
    return base, meta


def load_0801() -> pd.DataFrame:
    """08-01 snapshot features+labels from Group A asof_monthly (descriptive check)."""
    df = pd.read_parquet(PATHS["asof_monthly"])
    df = df[df["snapshot_date"].astype(str) == "2022-08-01"].copy()
    df = df.rename(columns={
        "fwd30_evt_cnt": "lbl_evt", "fwd30_cp_distinct": "lbl_cp",
        "fwd30_new_cp": "lbl_new"})
    return df
