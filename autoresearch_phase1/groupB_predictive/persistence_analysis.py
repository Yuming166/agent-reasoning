#!/usr/bin/env python3
"""Group B — persistence / regime / community specificity of predictive influence.

All numbers are descriptive; none imply causality ("predictive influence
!= causal influence"). Uses only as-of features (<= cutoff) and future labels
([t, t+30d)); no future information leaks into features.

Checks:
 1. PERSISTENCE  : do "important" wallets (high future activity / high
                   predicted score) stay important month to month?
                   - Spearman rank corr of future activity across snapshots
                   - top-10% Jaccard overlap across snapshots
                   - predicted-score persistence for a model trained on 06-01
 2. REGIME       : is predictive performance stable between frozen Aug (within
                   dev) and final Sep holdout? (loads predictive_results json)
                   - top-10% actual churn Aug vs Sep
 3. COMMUNITY    : does predictive importance / predictability concentrate in
                   specific Group-A personas (full_asof__kmeans, 09-01)?
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "groupB_predictive"
GROUP_A = ROOT / "research" / "groupA_behavior" / "results" / "data"
OUTDIR = HERE / "results"

BASE_FEATURES = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d", "evt_native_90d",
    "evt_token_90d", "active_days_90d", "tx_cnt_90d", "active_span_days_90d",
    "cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d",
    "cp_out_interact_90d", "cp_in_interact_90d", "token_distinct_90d",
    "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d",
    "cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d",
    "token_hhi_90d", "events_per_active_day_90d",
]


def topk_jaccard(s1: set, s2: set, k: int) -> float:
    return len(s1.intersection(s2)) / k


def main() -> None:
    out: dict = {}
    monthly = pd.read_parquet(GROUP_A / "asof_monthly_2022.parquet")
    fm09 = pd.read_parquet(GROUP_A / "feature_matrix_20220901.parquet")
    lab09 = pd.read_csv(OUTDIR / "data" / "labels_20220901_bq.csv")
    fm09 = fm09.drop(columns=[c for c in ["snapshot_date", "fwd30_evt_cnt",
                                          "fwd30_cp_distinct", "fwd30_cp_out_distinct",
                                          "fwd30_new_cp", "importance_proxy_p3"]
                              if c in fm09.columns])
    fm09 = fm09.merge(lab09, on="target_address", how="left")
    month = pd.concat([monthly, fm09[["snapshot_date", "target_address",
                                      "fwd30_evt_cnt", "fwd30_new_cp"] +
                                     BASE_FEATURES]], ignore_index=True)
    month["snapshot_date"] = month["snapshot_date"].astype(str).str[:10]
    snap_order = ["2022-05-01", "2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]

    # ------------------------------------------------------------------
    # 1. Persistence of future activity + historical activity across snapshots
    # ------------------------------------------------------------------
    pers = {}
    for a, b in zip(snap_order[:-1], snap_order[1:]):
        A = month[month.snapshot_date == a].set_index("target_address")
        B = month[month.snapshot_date == b].set_index("target_address")
        common = A.index.intersection(B.index)
        n = len(common)
        k = max(1, int(round(n * 0.10)))
        sp_fut = float(spearmanr(A.loc[common, "fwd30_evt_cnt"],
                                 B.loc[common, "fwd30_evt_cnt"]).statistic)
        sp_hist = float(spearmanr(A.loc[common, "evt_cnt_90d"],
                                  B.loc[common, "evt_cnt_90d"]).statistic)
        topA = set(A.loc[common, "fwd30_evt_cnt"].nlargest(k).index)
        topB = set(B.loc[common, "fwd30_evt_cnt"].nlargest(k).index)
        pers[f"{a}_to_{b}"] = {
            "n_common": n, "k_top10pct": k,
            "spearman_future_activity": sp_fut,
            "spearman_historical_activity": sp_hist,
            "top10pct_jaccard_future_activity": topk_jaccard(topA, topB, k),
        }
    out["persistence"] = pers

    # ------------------------------------------------------------------
    # 2. Regime: Aug (frozen, in-dev) vs Sep (final holdout)
    # ------------------------------------------------------------------
    pred = json.loads((OUTDIR / "predictive_results_20220901.json").read_text())
    regime = {"note": "model trained on 2022-06-01 only; metrics are OOS"}
    for tkey in ["act_level", "new_level", "act_bin", "new_bin"]:
        row = {"test08": {}, "holdout09": {}}
        for ev in ["test08", "holdout09"]:
            met = pred["targets"][tkey]["models"]["LightGBM"][ev]
            keep = {k: v for k, v in met.items()
                    if k in ("rmse", "r2", "spearman", "auc", "pr_auc", "brier",
                             "logloss", "ece", "recall_at_k", "mrr")}
            row[ev] = keep
        regime[tkey] = row
    # top-10% churn between Aug and Sep actual future activity
    aug = month[month.snapshot_date == "2022-08-01"].set_index("target_address")
    sep = month[month.snapshot_date == "2022-09-01"].set_index("target_address")
    common = aug.index.intersection(sep.index)
    k = max(1, int(round(len(common) * 0.10)))
    topA = set(aug.loc[common, "fwd30_evt_cnt"].nlargest(k).index)
    topB = set(sep.loc[common, "fwd30_evt_cnt"].nlargest(k).index)
    regime["aug_sep_top10pct_churn"] = {
        "n_common": int(len(common)), "k": k,
        "jaccard": topk_jaccard(topA, topB, k),
        "pct_new_in_sep_top10": float(len(topB - topA) / k),
    }
    out["regime"] = regime

    # ------------------------------------------------------------------
    # 3. Community specificity (Group A full_asof__kmeans personas at 09-01)
    # ------------------------------------------------------------------
    hp = pd.read_csv(OUTDIR / "holdout09_predictions.csv")
    pa = pd.read_csv(ROOT / "research/groupA_behavior/results/persona_assignments_20220901.csv")[
        ["target_address", "full_asof__kmeans"]]
    comm = hp.merge(pa, on="target_address", how="inner")
    comm["fwd30_evt_cnt_raw"] = np.expm1(comm["fwd30_evt_cnt"])
    comm["fwd30_new_cp_raw"] = np.expm1(comm["fwd30_new_cp"])
    n_all = len(comm)
    top10 = set(comm.nlargest(int(round(n_all * 0.10)),
                                  "pred_act_level_LightGBM")["target_address"])
    rows = []
    for g, df in comm.groupby("full_asof__kmeans"):
        y = (df["fwd30_evt_cnt_raw"] > 0).astype(int)
        p = df["pred_act_bin_LightGBM"]
        auc = float(roc_auc_score(y, p)) if y.nunique() > 1 else float("nan")
        rows.append({
            "community": int(g), "n": int(len(df)),
            "share_population": float(len(df) / n_all),
            "mean_future_activity": float(df["fwd30_evt_cnt_raw"].mean()),
            "mean_future_new_cp": float(df["fwd30_new_cp_raw"].mean()),
            "share_of_pred_top10pct": float(len(set(df["target_address"]) & top10) / len(top10)),
            "auc_future_active": auc,
        })
    comm_df = pd.DataFrame(rows).sort_values("mean_future_activity", ascending=False)
    out["community"] = {
        "model": "full_asof__kmeans (Group A personas, 09-01)",
        "n_wallets": int(n_all),
        "per_community": comm_df.to_dict(orient="records"),
    }
    # concentration: share of predicted-top-10% held by top-3 communities
    top3 = comm_df.sort_values("mean_future_activity", ascending=False).head(3)
    out["community"]["pred_top10pct_share_top3_by_activity"] = float(top3["share_of_pred_top10pct"].sum())

    out_path = OUTDIR / "persistence_regime_community_20220901.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {out_path}")
    print("\n== persistence ==")
    for k, v in out["persistence"].items():
        print(f"  {k}: n={v['n_common']} sp_fut={v['spearman_future_activity']:.4f} "
              f"sp_hist={v['spearman_historical_activity']:.4f} top10jacc={v['top10pct_jaccard_future_activity']:.4f}")
    print("\n== regime ==")
    for tkey in ["act_level", "new_level", "act_bin", "new_bin"]:
        t08, t09 = regime[tkey]["test08"], regime[tkey]["holdout09"]
        key = "r2" if "r2" in t08 else "auc"
        print(f"  {tkey}: test08 {key}={t08[key]:.4f} holdout09 {key}={t09[key]:.4f}")
    print("  aug_sep_top10_churn jaccard=", regime["aug_sep_top10pct_churn"]["jaccard"],
          "new_in_sep=", regime["aug_sep_top10pct_churn"]["pct_new_in_sep_top10"])
    print("\n== community (top by future activity) ==")
    print(comm_df.head(6).to_string(index=False))


if __name__ == "__main__":
    main()
