#!/usr/bin/env python3
"""Group B — exploratory 09-01 extended-feature ablation (WITHIN-SNAPSHOT OOS).

WHY THIS IS NOT THE PRIMARY EXPERIMENT:
  The temporal protocol only allows chronological splits for the frozen result.
  Base-feature temporal model = research/groupB_predictive/run_predictive.py
  (train 06-01 / val 07-01 / test 08-01 / untouched holdout 09-01).

  Here we test whether the 09-01-only extended feature groups (trajectory /
  as-of network / USD capital) add predictive value AT ALL. Because those
  features exist only at the 09-01 snapshot, we cannot train them on an
  earlier snapshot; we therefore use a DETERMINISTIC address-hash wallet split
  (train/val/test on unseen wallets). This is OUT-OF-SAMPLE on unseen wallets
  but NOT chronological; it is clearly labeled EXPLORATORY / POST-HOC and must
  not be presented as the frozen OOS result.

All features are still strictly <= 2022-09-01. No future labels in features.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
from scipy.stats import spearmanr
from sklearn.metrics import mean_squared_error, r2_score
from lightgbm import LGBMClassifier, LGBMRegressor

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "groupB_predictive"
GROUP_A = ROOT / "research" / "groupA_behavior" / "results" / "data"
OUTDIR = HERE / "results"
RNG = 2022
N_EARLY = 50

BASE_FEATURES = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d", "evt_native_90d",
    "evt_token_90d", "active_days_90d", "tx_cnt_90d", "active_span_days_90d",
    "cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d",
    "cp_out_interact_90d", "cp_in_interact_90d", "token_distinct_90d",
    "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d",
    "cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d",
    "token_hhi_90d", "events_per_active_day_90d",
]
TRAJ_FEATURES = [
    "n_events_90d_traj", "active_days_90d_traj", "active_span_days_traj",
    "first_event_offset_days", "last_event_recency_days", "mean_gap_days",
    "median_gap_days", "max_gap_days", "std_gap_days", "n_gaps_gt7d", "n_gaps",
    "out_interact_90d", "in_interact_90d", "native_90d", "token_90d",
]
NET_FEATURES = [
    "asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree",
    "asof_mm_w_in_degree", "asof_mm_w_out_degree", "asof_mm_pagerank",
    "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors",
]
USD_FEATURES = ["native_usd", "token_usd_priced", "token_rows", "token_rows_priced"]

FEAT_SETS = {
    "base": BASE_FEATURES,
    "base+traj": BASE_FEATURES + TRAJ_FEATURES,
    "base+net": BASE_FEATURES + NET_FEATURES + ["in_mm_subgraph"],
    "base+usd": BASE_FEATURES + USD_FEATURES,
    "all": BASE_FEATURES + TRAJ_FEATURES + NET_FEATURES + ["in_mm_subgraph"] + USD_FEATURES,
}
DROP = ["snapshot_date", "target_address", "target_exgraph_node_id",
        "target_is_x_matched", "fwd30_evt_cnt", "fwd30_cp_distinct",
        "fwd30_cp_out_distinct", "fwd30_new_cp", "importance_proxy_p3"]


def fold_of(addr: str, n: int = 10) -> int:
    return int(hashlib.sha256(addr.encode()).hexdigest()[:8], 16) % n


def main() -> None:
    fm = pd.read_parquet(GROUP_A / "feature_matrix_20220901.parquet")
    lab = pd.read_csv(OUTDIR / "data" / "labels_20220901_bq.csv")
    fm = fm.drop(columns=[c for c in DROP if c in fm.columns and c != "target_address"])
    fm = fm.merge(lab, on="target_address", how="left")
    # static pagerank baseline (leaky prior, baseline only)
    static = pd.read_csv(GROUP_A / "static_prior_20220901.csv")[
        ["target_address", "pagerank"]]
    fm = fm.merge(static, on="target_address", how="left")
    fm["pagerank"] = fm["pagerank"].fillna(0.0)

    fold = fm["target_address"].map(fold_of).to_numpy()
    tr = fold < 6
    va = (fold >= 6) & (fold < 8)
    te = fold >= 8
    print(f"train/val/test = {tr.sum()}/{va.sum()}/{te.sum()}")

    y = {
        "act_bin": (fm["fwd30_evt_cnt"] > 0).astype(int).to_numpy(),
        "new_bin": (fm["fwd30_new_cp"] > 0).astype(int).to_numpy(),
        "act_level": np.log1p(fm["fwd30_evt_cnt"]).to_numpy(float),
        "new_level": np.log1p(fm["fwd30_new_cp"]).to_numpy(float),
    }

    results = {"note": "within-snapshot deterministic address-hash split; EXPLORATORY/POST-HOC, not the frozen temporal OOS result",
               "split": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum())},
               "targets": {}}

    for tkey, tname in [("act_bin", "future_active"), ("new_bin", "future_new_edge"),
                        ("act_level", "future_activity_level"),
                        ("new_level", "future_new_edges_level")]:
        results["targets"][tkey] = {"name": tname, "feature_sets": {}}
        for fset_name, feats in FEAT_SETS.items():
            X = fm[feats].copy()
            if "in_mm_subgraph" in X.columns:
                X["in_mm_subgraph"] = X["in_mm_subgraph"].fillna(False).astype(int)
            X = X.fillna(X.median(numeric_only=True)).replace([np.inf, -np.inf], 0.0)
            Xa = X.to_numpy(float)
            if tkey.endswith("bin"):
                m = LGBMClassifier(n_estimators=300, learning_rate=0.05,
                                   num_leaves=31, random_state=RNG, verbose=-1, n_jobs=4)
                m.fit(Xa[tr], y[tkey][tr], eval_set=[(Xa[va], y[tkey][va])],
                      callbacks=[__import__("lightgbm").early_stopping(N_EARLY, verbose=False)])
                p = m.predict_proba(Xa[te])[:, 1]
                met = {
                    "auc": float(roc_auc_score(y[tkey][te], p)),
                    "pr_auc": float(average_precision_score(y[tkey][te], p)),
                    "brier": float(brier_score_loss(y[tkey][te], p)),
                    "logloss": float(log_loss(y[tkey][te], p)),
                }
            else:
                m = LGBMRegressor(n_estimators=300, learning_rate=0.05,
                                  num_leaves=31, random_state=RNG, verbose=-1, n_jobs=4)
                m.fit(Xa[tr], y[tkey][tr], eval_set=[(Xa[va], y[tkey][va])],
                      callbacks=[__import__("lightgbm").early_stopping(N_EARLY, verbose=False)])
                p = m.predict(Xa[te])
                met = {
                    "rmse": float(np.sqrt(mean_squared_error(y[tkey][te], p))),
                    "r2": float(r2_score(y[tkey][te], p)),
                    "spearman": float(spearmanr(y[tkey][te], p).statistic),
                }
            results["targets"][tkey]["feature_sets"][fset_name] = met
            key = "auc" if "auc" in met else "r2"
            print(f"  {tkey:10s} {fset_name:12s} {key}={met[key]:.4f}")

    # static-pagerank ranking baseline (exploratory only, leaky prior)
    pr = np.log1p(fm["pagerank"].to_numpy(float))
    for tkey in ["act_level", "new_level"]:
        met = {"spearman": float(spearmanr(y[tkey][te], pr[te]).statistic),
               "r2": float(r2_score(y[tkey][te], pr[te]))}
        results["targets"][tkey]["static_pagerank_baseline"] = met
        print(f"  {tkey:10s} static_pagerank_baseline r2={met['r2']:.4f} sp={met['spearman']:.4f}")

    out = OUTDIR / "predictive_extended09_ablation.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
