"""Stratified representative sampling for the Group E pilot.

Selection uses ONLY as-of (pre-cutoff) information: activity tier (terciles of
evt_cnt_90d), trajectory cluster (Group A trajectory__kmeans, 5 clusters) and
network coverage (in_mm_subgraph). Future labels (fwd30_*) and the
same-snapshot P3 proxy are deliberately NOT used for selection so the sample
itself cannot be chosen on the validation labels.

Output: results/sample_wallets_20220901.csv  (target_address, node_id, strata)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def build_strata(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # activity tier on as-of 90-day event count (terciles of the full bounded sample)
    q33, q67 = df["evt_cnt_90d"].quantile([1 / 3, 2 / 3])
    def tier(x):
        if x <= q33:
            return "low"
        if x <= q67:
            return "mid"
        return "high"
    df["activity_tier"] = df["evt_cnt_90d"].map(tier)
    # trajectory cluster from Group A (integer label; -1 noise bucket)
    pa = pd.read_csv(config.PERSONA)[["target_address", config.STRAT_TRAJ_CLUSTER]]
    pa = pa.rename(columns={config.STRAT_TRAJ_CLUSTER: "traj_cluster"})
    df = df.merge(pa, on="target_address", how="left")
    df["traj_cluster"] = df["traj_cluster"].fillna(-1).astype(int)
    # network coverage (as-of matched-matched subgraph membership)
    df["net_cov"] = df["in_mm_subgraph"].fillna(False).astype(bool).map({True: "mm", False: "no_mm"})
    df["stratum"] = df["activity_tier"] + "|" + df["traj_cluster"].astype(str) + "|" + df["net_cov"]
    return df


def main() -> None:
    df = pd.read_parquet(config.FEATURE_MATRIX)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    df = build_strata(df)
    rng = np.random.default_rng(config.SAMPLE_SEED)

    cell_n = df.groupby("stratum")["target_address"].count()
    # per-stratum quota ~ sqrt(size), min 1, so small rare strata stay represented
    weights = np.sqrt(cell_n.clip(lower=1))
    raw = (config.SAMPLE_N * weights / weights.sum()).round().clip(lower=1).astype(int)
    raw = raw.clip(upper=cell_n)
    # trim to exact target by dropping from largest strata
    quota = raw.to_dict()
    total = int(sum(quota.values()))
    if total > config.SAMPLE_N:
        strata_sorted = sorted(quota, key=lambda s: (-quota[s], s))
        for s in strata_sorted:
            if total <= config.SAMPLE_N:
                break
            quota[s] -= 1
            total -= 1
    # deterministic draw within each stratum
    picked = []
    for s, k in quota.items():
        pool = df[df["stratum"] == s]
        picked.append(pool.sample(n=int(k), random_state=rng).copy())
    out = pd.concat(picked).reset_index(drop=True)
    out = out[["target_address", "target_exgraph_node_id", "activity_tier",
               "traj_cluster", "net_cov", "stratum", "evt_cnt_90d"]]
    out.to_csv(config.SAMPLE_CSV, index=False)

    meta = {
        "cutoff": config.CUTOFF,
        "n_target": config.SAMPLE_N,
        "n_picked": int(len(out)),
        "seed": config.SAMPLE_SEED,
        "strata_used": len(quota),
        "selection_features": "as-of only: evt_cnt_90d tercile, trajectory__kmeans cluster, in_mm_subgraph",
        "future_labels_in_selection": False,
        "tier_counts": out["activity_tier"].value_counts().to_dict(),
        "traj_cluster_counts": out["traj_cluster"].value_counts().sort_index().to_dict(),
        "net_cov_counts": out["net_cov"].value_counts().to_dict(),
    }
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    (config.RESULTS / "sample_meta_20220901.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"[ok] wrote {config.SAMPLE_CSV}")


if __name__ == "__main__":
    main()
