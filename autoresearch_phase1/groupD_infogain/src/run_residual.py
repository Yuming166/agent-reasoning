"""Experiment 4 — Influence Residual Analysis (§10) and baseline comparison.

InfluenceResidual_i = IG_i - E[IG | Volume_i]
Checks whether low-volume/high-IG and high-volume/low-IG groups exist, and how
the IG ranking compares with volume, as-of degree/PageRank, static-prior
centrality (leaky baseline, comparison only), and existing ICF rankings.

Note: ICF v2 exists at snapshots 06/07/08 (not 09); the 2022-08-01 snapshot is
used for comparison with an explicit cutoff-mismatch caveat. ICF v1 local
ranking is snapshot-agnostic (Aug-era) and also comparison-only.

Outputs: results/residual_20220901.json, results/ig_vs_baselines_20220901.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, linregress

sys.path.insert(0, str(Path(__file__).parent))
import config as C

OUT_JSON = C.RESULTS / "residual_20220901.json"
OUT_CSV = C.RESULTS / "ig_vs_baselines_20220901.csv"


def load_ig(subset: pd.DataFrame) -> pd.DataFrame:
    wig = pd.read_csv(C.RESULTS / "wallet_ig_20220901.csv")
    wide = wig.pivot_table(index="target_address", columns=["target", "model"], values="ig_occ")
    wide.columns = [f"ig_{t}_{m}" for t, m in wide.columns]
    return subset[["target_address", "target_exgraph_node_id", "volume_usd",
                   "log_volume_usd", "asof_mm_undir_degree", "asof_mm_pagerank",
                   "in_mm_subgraph"]].merge(wide.reset_index(), on="target_address", how="left")


def add_external(d: pd.DataFrame) -> pd.DataFrame:
    # static prior (full-window, leaky baseline for comparison only)
    st = pd.read_csv(C.STATIC_PRIOR, usecols=["target_address", "degree", "w_degree", "pagerank"])
    d = d.merge(st, on="target_address", how="left")
    # ICF v1 (local ranking)
    icf1 = pd.read_csv(C.ICF_V1)[["target_address", "icf_score_p1", "p1_rank"]]
    icf1 = icf1.rename(columns={"icf_score_p1": "icf_v1_score", "p1_rank": "icf_v1_rank"})
    d = d.merge(icf1, on="target_address", how="left")
    # ICF v2 (BQ pull, snapshot 2022-08-01, cutoff-mismatch caveat)
    icf2 = pd.read_csv(C.RESULTS / "external" / "p1_wallet_icf_v2_20220801.csv")
    icf2 = icf2.rename(columns={"icf_score_p1": "icf_v2_score"})
    d = d.merge(icf2[["target_address", "icf_v2_score"]], on="target_address", how="left")
    return d


def rank_metrics(d: pd.DataFrame, ig_col: str) -> dict:
    base_cols = {
        "log_volume_usd": "log USD volume (as-of)",
        "volume_usd": "USD volume (as-of)",
        "asof_mm_undir_degree": "as-of undirected degree (mm subgraph)",
        "asof_mm_pagerank": "as-of PageRank (mm subgraph)",
        "degree": "static-prior degree (LEAKY baseline)",
        "pagerank": "static-prior PageRank (LEAKY baseline)",
        "icf_v1_score": "ICF v1 score (existing ranking, comparison)",
        "icf_v2_score": "ICF v2 score snapshot 08-01 (comparison, cutoff-mismatch)",
    }
    out = {}
    for col, label in base_cols.items():
        sub = d[[ig_col, col]].dropna()
        if len(sub) < 30 or sub[col].nunique() < 2:
            out[col] = {"label": label, "n": int(len(sub)), "spearman": None}
            continue
        rho, p = spearmanr(sub[ig_col], sub[col])
        out[col] = {"label": label, "n": int(len(sub)),
                    "spearman": float(rho), "p": float(p)}
    return out


def residualize(d: pd.DataFrame, ig_col: str) -> pd.DataFrame:
    sub = d[[ig_col, "log_volume_usd"]].dropna()
    lr = linregress(sub["log_volume_usd"], sub[ig_col])
    d = d.copy()
    d["ig_resid_logvol"] = np.nan
    mask = d[ig_col].notna() & d["log_volume_usd"].notna()
    d.loc[mask, "ig_resid_logvol"] = d.loc[mask, ig_col] - (
        lr.intercept + lr.slope * d.loc[mask, "log_volume_usd"])
    return d, lr


def group_checks(d: pd.DataFrame, ig_col: str, vol_col: str = "volume_usd") -> dict:
    sub = d[d[ig_col].notna()].copy()
    vq1, vq3 = sub[vol_col].quantile([0.25, 0.75])
    rq10, rq90 = sub["ig_resid_logvol"].quantile([0.10, 0.90])
    lo_vol_hi_ig = sub[(sub[vol_col] <= vq1) & (sub["ig_resid_logvol"] >= rq90)]
    hi_vol_lo_ig = sub[(sub[vol_col] >= vq3) & (sub["ig_resid_logvol"] <= rq10)]
    # centrality variants (as-of degree, mm subgraph only; static degree full coverage)
    deg = sub[sub["asof_mm_undir_degree"].notna()]
    if len(deg):
        dq9 = deg["asof_mm_undir_degree"].quantile(0.90)
        hi_cent_lo_ig = deg[(deg["asof_mm_undir_degree"] >= dq9) & (deg["ig_resid_logvol"] <= rq10)]
        lo_cent_hi_ig = deg[(deg["asof_mm_undir_degree"] <= deg["asof_mm_undir_degree"].quantile(0.10))
                            & (deg["ig_resid_logvol"] >= rq90)]
    else:
        hi_cent_lo_ig = lo_cent_hi_ig = pd.DataFrame()
    def fmt(g):
        return {"n": int(len(g)),
                "mean_ig": float(g[ig_col].mean()) if len(g) else None,
                "mean_ig_resid": float(g["ig_resid_logvol"].mean()) if len(g) else None,
                "mean_volume_usd": float(g["volume_usd"].mean()) if len(g) else None,
                "mean_asof_degree": float(g["asof_mm_undir_degree"].mean()) if len(g) else None,
                "examples": g["target_address"].head(8).tolist()}
    return {
        "low_volume_high_ig": fmt(lo_vol_hi_ig),
        "high_volume_low_ig": fmt(hi_vol_lo_ig),
        "high_centrality_low_ig": fmt(hi_cent_lo_ig),
        "low_centrality_high_ig": fmt(lo_cent_hi_ig),
        "thresholds": {"volume_q1": float(vq1), "volume_q3": float(vq3),
                       "ig_resid_p10": float(rq10), "ig_resid_p90": float(rq90)},
    }


def main() -> None:
    subset = pd.read_parquet(C.RESULTS / "dataset_subset_20220901.parquet")
    d = load_ig(subset)
    d = add_external(d)
    ig_col = "ig_y_cp_ge10_histgbm"  # primary ranking
    d, lr = residualize(d, ig_col)

    result = {
        "cutoff": C.CUTOFF,
        "primary_ig": ig_col,
        "n_wallets": int(len(d)),
        "residual_model": "IG ~ log1p(volume_usd), OLS (linregress)",
        "residual_slope": float(lr.slope),
        "residual_intercept": float(lr.intercept),
        "residual_r2": float(lr.rvalue ** 2),
        "rank_correlations": rank_metrics(d, ig_col),
        "groups": group_checks(d, ig_col),
        "leaky_static_prior_note": "static-prior degree/PageRank are full-window and may "
                                   "contain future-window structure; used ONLY as comparison baselines",
        "icf_cutoff_mismatch_note": "ICF v2 exists only at snapshots 06/07/08; "
                                    "08-01 used with explicit cutoff mismatch",
    }
    (C.RESULTS / "residual_20220901.json").write_text(json.dumps(result, indent=2, default=str))
    d.to_csv(OUT_CSV, index=False)
    print("[residual] rank correlations (primary IG = histgbm / y_cp_ge10):")
    for col, v in result["rank_correlations"].items():
        rho = "NA" if v["spearman"] is None else round(v["spearman"], 4)
        print(f"  {col:22s} n={v['n']:5d} spearman={rho}")
    print("[residual] groups:")
    for k, v in result["groups"].items():
        if k == "thresholds":
            continue
        print(f"  {k:26s} n={v['n']:3d} mean_ig={v['mean_ig'] if v['mean_ig'] is None else round(v['mean_ig'],3)} "
              f"mean_vol=${v['mean_volume_usd'] if v['mean_volume_usd'] is None else round(v['mean_volume_usd'],0):,}")
    print(f"[residual] done -> {OUT_JSON}")


if __name__ == "__main__":
    main()
