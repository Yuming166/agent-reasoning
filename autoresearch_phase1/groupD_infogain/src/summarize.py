"""Consolidated digest of Group D results (for README / report).
Writes results/SUMMARY.json and prints a compact digest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config as C


def main() -> None:
    wm = json.load(open(C.RESULTS / "wallet_masking_20220901.json"))
    fm = json.load(open(C.RESULTS / "feature_masking_20220901.json"))
    cm = json.load(open(C.RESULTS / "community_masking_20220901.json"))
    rs = json.load(open(C.RESULTS / "residual_20220901.json"))
    rc = json.load(open(C.RESULTS / "ranking_compare_20220901.json"))

    dig = {
        "cutoff": "2022-09-01",
        "subset_n": wm["subset"],
        "wallet_masking": wm["summary"],
        "wallet_masking_topK": wm["subset_masking"]["histgbm__y_cp_ge10"],
        "retraining_diagnostic": wm["retraining_diagnostic"],
        "feature_blocks": fm["blocks"]["histgbm"],
        "single_feature_top10": fm["single_feature_ablation"]["top10_by_dnll"],
        "community_top": cm["summary"],
        "residual": rs,
        "ranking": rc,
    }
    (C.RESULTS / "SUMMARY.json").write_text(json.dumps(dig, indent=2, default=str))

    print("=" * 78)
    print("GROUP D DIGEST (predictive information gain, cutoff 2022-09-01, subset=%d)" % wm["subset"])
    print("=" * 78)
    print("\n[1] Wallet masking (5-fold CV occlusion; IG_i = dNLL(mask-features -> median))")
    for k, v in wm["summary"].items():
        print(f"  {k:28s} nll_full={v['nll_full']:.4f} nll_mask={v['nll_mask_all']:.4f} "
              f"dNLL={v['delta_nll_all']:+.4f} AUC={v['auc_full']:.4f}->{v['auc_mask_all']:.4f} "
              f"IG_mean={v['ig_occ_mean']:+.4f}")
    print("  subset-mask top-K IG (histgbm/y_cp_ge10):", {
        k: round(v["delta_nll"], 3) for k, v in wm["subset_masking"]["histgbm__y_cp_ge10"].items()})

    print("\n[2] Feature block masking (histgbm / y_cp_ge10)")
    for b, v in fm["blocks"]["histgbm"].items():
        if b == "full":
            continue
        print(f"  {b:10s} dNLL={v['delta_nll']:+.4f} dAUC={v['delta_auc']:+.4f} dBrier={v['delta_brier']:+.4f}")

    print("\n[3] Residual / §10 groups")
    for k, v in rs["groups"].items():
        if k == "thresholds":
            continue
        print(f"  {k:26s} n={v['n']:3d} mean_ig={v['mean_ig'] if v['mean_ig'] is None else round(v['mean_ig'],3)} "
              f"mean_vol=${v['mean_volume_usd'] if v['mean_volume_usd'] is None else round(v['mean_volume_usd'],0):,}")

    print("\n[4] Rank correlations (IG primary vs baselines)")
    for col, v in rs["rank_correlations"].items():
        rho = "NA" if v["spearman"] is None else round(v["spearman"], 3)
        print(f"  {col:22s} rho={rho}")

    print("\n[5] Top-K Jaccard overlap IG vs baselines")
    for K, row in rc["topk_overlap"].items():
        print(f"  K={K:>3}: " + " ".join(f"{k.split('_',1)[-1]}={v}" for k, v in row.items()))

    print("\n[6] Model consistency (same target):")
    for k, v in rc["consistency_spearman"].items():
        if "y_cp_ge10_histgbm vs y_cp_ge10_logistic" in k or "y_active30_histgbm vs y_active30_logistic" in k:
            print(f"  {k}: {v}")

    print("\nsaved -> results/SUMMARY.json")


if __name__ == "__main__":
    main()
