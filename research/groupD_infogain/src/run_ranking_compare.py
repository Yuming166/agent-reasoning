"""Ranking comparison: IG vs volume/degree/PageRank/ICF (top-K Jaccard overlap),
model & target consistency of the IG ranking, and example wallet profiles.
Outputs: results/ranking_compare_20220901.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).parent))
import config as C

OUT_JSON = C.RESULTS / "ranking_compare_20220901.json"


def main() -> None:
    df = pd.read_parquet(C.RESULTS / "dataset_subset_20220901.parquet")
    wig = pd.read_csv(C.RESULTS / "wallet_ig_20220901.csv")
    wide = wig.pivot_table(index="target_address", columns=["target", "model"], values="ig_occ")
    wide.columns = [f"ig_{t}_{m}" for t, m in wide.columns]
    d = df[["target_address", "volume_usd", "asof_mm_undir_degree", "asof_mm_pagerank"]].merge(
        wide.reset_index(), on="target_address", how="left")
    st = pd.read_csv(C.STATIC_PRIOR, usecols=["target_address", "degree", "pagerank"])
    d = d.merge(st, on="target_address", how="left")
    icf1 = pd.read_csv(C.ICF_V1)[["target_address", "p1_rank"]]
    icf2 = pd.read_csv(C.RESULTS / "external" / "p1_wallet_icf_v2_20220801.csv")[["target_address", "icf_score_p1"]]
    d = d.merge(icf1, on="target_address", how="left").merge(icf2, on="target_address", how="left")

    ig_col = "ig_y_cp_ge10_histgbm"
    res = {}

    # consistency across models/targets
    cols = ["ig_y_cp_ge10_histgbm", "ig_y_cp_ge10_logistic", "ig_y_active30_histgbm", "ig_y_active30_logistic"]
    cons = {}
    for a in cols:
        for b in cols:
            if a < b:
                s = d[[a, b]].dropna()
                cons[f"{a} vs {b}"] = round(float(spearmanr(s[a], s[b]).statistic), 4)
    res["consistency_spearman"] = cons

    # top-K Jaccard overlap
    def topk_index(series, k):
        return set(series.dropna().sort_values(ascending=False).head(k).index)
    ig_s = d.set_index("target_address")[ig_col]
    vol_s = d.set_index("target_address")["volume_usd"]
    deg_s = d.set_index("target_address")["asof_mm_undir_degree"]
    pr_s = d.set_index("target_address")["pagerank"]
    icf1_s = d.set_index("target_address")["p1_rank"]  # lower=better
    icf2_s = d.set_index("target_address")["icf_score_p1"]
    res["topk_overlap"] = {}
    for K in [50, 100, 250, 500]:
        igk = topk_index(ig_s, K)
        row = {"n": K}
        for name, s in [("volume", vol_s), ("asof_degree", deg_s), ("static_pagerank", pr_s),
                        ("icf_v1_rank", icf1_s), ("icf_v2_score", icf2_s)]:
            asc = name in ("icf_v1_rank",)
            sk = set(s.sort_values(ascending=asc).head(K).index)
            row[f"jaccard_{name}"] = round(len(igk & sk) / len(igk), 4)
        # expected overlap of two random size-K sets among n=2999
        n = len(d)
        row["jaccard_random_expected"] = round(K / n, 4)
        res["topk_overlap"][str(K)] = row

    # example profiles
    prof_cols = ["target_address", "volume_usd", "asof_mm_undir_degree", "asof_mm_pagerank",
                 "degree", ig_col]
    top10 = d.nlargest(10, ig_col)[prof_cols]
    res["top10_ig"] = top10.round(4).to_dict("records")

    r = pd.read_csv(C.RESULTS / "ig_vs_baselines_20220901.csv")
    lvhi = r[(r["ig_resid_logvol"] >= r["ig_resid_logvol"].quantile(0.90)) &
             (r["volume_usd"] <= r["volume_usd"].quantile(0.25))]
    res["low_volume_high_ig_examples"] = lvhi[prof_cols + ["ig_resid_logvol"]].round(4).to_dict("records")

    (C.RESULTS / "ranking_compare_20220901.json").write_text(json.dumps(res, indent=2, default=str))
    print("=== consistency (spearman) ===")
    for k, v in cons.items():
        print(f"  {k}: {v}")
    print("=== top-K Jaccard overlap (IG vs baselines) ===")
    for K, row in res["topk_overlap"].items():
        print(f"  K={K}: " + " ".join(f"{k}={v}" for k, v in row.items()))
    print("\n=== top-10 IG wallets ===")
    for rec in res["top10_ig"]:
        print(f"  {rec['target_address']} vol=${rec['volume_usd']:,.0f} "
              f"asof_deg={rec['asof_mm_undir_degree']} pr={rec['asof_mm_pagerank']} "
              f"static_deg={rec['degree']} ig={rec[ig_col]:.3f}")
    print("\n=== low-volume / high-IG examples ===")
    for rec in res["low_volume_high_ig_examples"][:10]:
        print(f"  {rec['target_address']} vol=${rec['volume_usd']:,.0f} "
              f"asof_deg={rec['asof_mm_undir_degree']} ig={rec[ig_col]:.3f} resid={rec['ig_resid_logvol']:.3f}")
    print(f"\ndone -> {OUT_JSON}")


if __name__ == "__main__":
    main()
