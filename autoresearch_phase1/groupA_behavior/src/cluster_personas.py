"""Z_i(t) -> P_i(t): cluster behavioral personas at cutoff 2022-09-01.

Compares representations and algorithms on the bounded 18,519-wallet sample:
  * representations: full as-of Z (all groups), trajectory-summary only,
    network-only (matched-matched subgraph wallets)
  * algorithms: K-means (K grid), GMM (component grid), HDBSCAN (min_cluster_size grid)
Evaluation here: silhouette + cluster sizes. Stability/bootstrap/persistence
and downstream utility are computed by evaluate_personas.py.

Outputs:
  results/persona_assignments_20220901.csv   wallet x model labels
  results/clustering_summary.json            per-config metrics
  results/cluster_profiles_20220901.csv      per cluster mean features + future labels
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

import hdbscan

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

SEED = 2022

ACTIVITY = ["evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
            "active_days_90d", "tx_cnt_90d", "active_span_days_90d",
            "events_per_active_day_90d", "active_days_90d_traj",
            "active_span_days_traj", "first_event_offset_days",
            "last_event_recency_days", "n_events_90d_traj",
            "direction_balance"]
CAPITAL = ["evt_native_90d", "evt_token_90d", "token_distinct_90d",
           "token_hhi_90d", "token_event_rate_90d", "native_usd",
           "token_usd_priced", "token_rows", "token_rows_priced",
           "native_90d", "token_90d"]
COUNTERPARTIES = ["cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d",
                  "cp_out_interact_90d", "cp_in_interact_90d", "cp_entropy_90d",
                  "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d",
                  "cp_reciprocity_90d", "self_tx_rate_90d",
                  "out_interact_90d", "in_interact_90d"]
NETWORK = ["asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree",
           "asof_mm_w_in_degree", "asof_mm_w_out_degree", "asof_mm_pagerank",
           "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors"]
TRAJECTORY = ["mean_gap_days", "median_gap_days", "max_gap_days", "std_gap_days",
              "n_gaps_gt7d", "n_gaps", "burstiness"]


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Derived behavior features (computed after the bounded pulls)."""
    df = df.copy()
    # wallets absent from the matched-matched subgraph get 0 network features
    net_cols = ["asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree",
                "asof_mm_w_in_degree", "asof_mm_w_out_degree", "asof_mm_pagerank",
                "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors"]
    df["in_mm_subgraph"] = df["in_mm_subgraph"].fillna(False).astype(bool)
    for c in net_cols:
        df[c] = df[c].fillna(0.0)
    # single-event wallets get zero gap features
    gap_cols = ["mean_gap_days", "median_gap_days", "max_gap_days", "std_gap_days"]
    for c in gap_cols:
        df[c] = df[c].fillna(0.0)
    df["n_gaps_gt7d"] = df["n_gaps_gt7d"].fillna(0).astype(int)
    df["n_gaps"] = df["n_gaps"].fillna(0).astype(int)
    out = df["out_interact_90d"].fillna(0.0)
    inn = df["in_interact_90d"].fillna(0.0)
    df["direction_balance"] = (out / (out + inn)).replace([np.inf, np.nan], 0.5)
    m = df["mean_gap_days"]; s = df["std_gap_days"]
    denom = (s + m).replace(0, np.nan)
    df["burstiness"] = ((s - m) / denom).fillna(0.0)
    df["single_event"] = (df["n_gaps"].fillna(0) == 0).astype(int)
    df["usd_missing"] = df["native_usd"].isna().astype(int)
    df["mm_absent"] = (1 - df["in_mm_subgraph"].astype(int))
    return df


def prepare_matrix(df: pd.DataFrame, groups: list[list[str]]) -> pd.DataFrame:
    """Transform + impute the requested feature groups into a model-ready matrix.

    Counts/gaps/USD -> log1p; ratios as-is; all filled (0 for missing counts,
    group means for missing ratio features); then StandardScaler.
    """
    cols = [c for g in groups for c in g]
    X = df[cols].copy()
    for c in cols:
        s = X[c]
        if s.dtype.kind not in "if":
            X[c] = pd.to_numeric(s, errors="coerce")
    # log-transform positive-skewed count/gap/usd-like features
    log_cols = [c for c in cols if c not in {
        "token_hhi_90d", "token_event_rate_90d", "cp_entropy_90d",
        "cp_new_rate_30d", "cp_reciprocity_90d", "self_tx_rate_90d",
        "asof_mm_clustering", "direction_balance", "burstiness",
        "single_event", "usd_missing", "mm_absent", "in_mm_subgraph"}]

    for c in log_cols:
        X[c] = np.log1p(X[c].clip(lower=0))
    # impute remaining NaN with column median
    X = X.apply(lambda col: col.fillna(col.median()))
    # winsorize at 99.5 / 0.5 percentile to tame extreme tails
    lo = X.quantile(0.005); hi = X.quantile(0.995)
    X = X.clip(lo, hi, axis=1)
    Xs = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns, index=X.index)
    return Xs


def silhouette_safe(labels: np.ndarray, X: np.ndarray) -> float:
    from sklearn.metrics import silhouette_score
    mask = labels != -1
    if mask.sum() < 2 or len(set(labels[mask])) < 2:
        return float("nan")
    return float(silhouette_score(X[mask], labels[mask]))


def main() -> None:
    results = config.RESULTS
    data_dir = results / "data"
    df = pd.read_parquet(data_dir / "feature_matrix_20220901.parquet")
    df = add_derived(df)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")

    reps = {
        "full_asof": ACTIVITY + CAPITAL + COUNTERPARTIES + NETWORK + TRAJECTORY,
        "trajectory": TRAJECTORY,
    }
    # network-only representation on matched-matched wallets
    mm = df[df["in_mm_subgraph"].astype(bool)].copy()

    assignments = df[["target_address", "target_exgraph_node_id"]].copy()
    summary = []
    profiles = []

    def run_model(name: str, X_sil: np.ndarray, labels: np.ndarray,
                  n_clusters: int | None, extra: dict,
                  assign_index: pd.Index | None = None) -> None:
        """labels aligned to assign_index (default: full df); X_sil used for silhouette."""
        nonlocal assignments
        if assign_index is None:
            assign_index = df.index
        lab = pd.Series(labels, index=assign_index).astype(int)
        assignments[name] = lab.reindex(df.index).fillna(-1).astype(int).to_numpy()
        sil = silhouette_safe(labels, X_sil)
        sizes = pd.Series(labels).value_counts().sort_index()
        summary.append({
            "rep": name.split("__")[0], "model": name.split("__")[1],
            "n_clusters": n_clusters, "noise_frac": float((labels == -1).mean()),
            "silhouette": sil, **extra,
            "min_size": int(sizes.min()), "max_size": int(sizes.max()),
        })
        # cluster profile on key descriptive features + future labels
        prof = df.assign(_label=lab.reindex(df.index).fillna(-1).astype(int).to_numpy()).groupby("_label").agg(
            n=("target_address", "size"),
            mean_evt_cnt=("evt_cnt_90d", "mean"),
            mean_active_days=("active_days_90d", "mean"),
            mean_cp_distinct=("cp_distinct_90d", "mean"),
            mean_entropy=("cp_entropy_90d", "mean"),
            mean_fwd30_evt=("fwd30_evt_cnt", "mean"),
            mean_fwd30_new_cp=("fwd30_new_cp", "mean"),
        ).reset_index()
        prof["model"] = name
        profiles.append(prof)

    # ---------- full as-of representation ----------
    X_full = prepare_matrix(df, [ACTIVITY, CAPITAL, COUNTERPARTIES, NETWORK, TRAJECTORY])
    X_full_np = X_full.to_numpy()
    for k in [3, 4, 5, 6, 8, 10]:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X_full_np)
        run_model("full_asof__kmeans", X_full_np, km.labels_, k, {"k": k})
    for nc in [3, 4, 5, 6, 8, 10]:
        gm = GaussianMixture(n_components=nc, covariance_type="diag",
                             n_init=5, random_state=SEED).fit(X_full_np)
        lab = gm.predict(X_full_np)
        run_model("full_asof__gmm", X_full_np, lab, nc, {"n_components": nc})
    # HDBSCAN on PCA-20 for density stability
    pca20 = PCA(n_components=min(20, X_full_np.shape[1]), random_state=SEED).fit_transform(X_full_np)
    for mcs in [30, 60, 120]:
        hdb = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=5,
                              metric="euclidean", gen_min_span_tree=False).fit(pca20)
        run_model("full_asof__hdbscan", X_full_np, hdb.labels_, None,
                  {"min_cluster_size": mcs, "n_clusters_eff": int((hdb.labels_ >= 0).sum() > 0
                                                                 and hdb.labels_.max() + 1 or 0)})

    # ---------- trajectory-only representation ----------
    X_traj = prepare_matrix(df, [TRAJECTORY])
    X_traj_np = X_traj.to_numpy()
    km5 = KMeans(n_clusters=5, n_init=10, random_state=SEED).fit(X_traj_np)
    run_model("trajectory__kmeans", X_traj_np, km5.labels_, 5, {"k": 5})
    gm5 = GaussianMixture(n_components=5, covariance_type="diag",
                          n_init=5, random_state=SEED).fit(X_traj_np)
    run_model("trajectory__gmm", X_traj_np, gm5.predict(X_traj_np), 5, {"n_components": 5})

    # ---------- network-only representation (matched-matched wallets) ----------
    X_net = prepare_matrix(mm, [NETWORK])
    X_net_np = X_net.to_numpy()
    km_net = KMeans(n_clusters=5, n_init=10, random_state=SEED).fit(X_net_np)
    run_model("network__kmeans", X_net_np, km_net.labels_, 5,
              {"k": 5, "subset": "mm_only"}, assign_index=mm.index)

    assignments.to_csv(results / "persona_assignments_20220901.csv", index=False)
    pd.concat(profiles).to_csv(results / "cluster_profiles_20220901.csv", index=False)
    (results / "clustering_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))

    s = pd.DataFrame(summary)
    print("\n=== clustering summary (cutoff=2022-09-01, n=18,519) ===")
    print(s[["rep", "model", "n_clusters", "silhouette", "noise_frac"]].to_string(index=False))
    print("\n[ok] wrote persona_assignments_20220901.csv, clustering_summary.json, cluster_profiles_20220901.csv")


if __name__ == "__main__":
    main()
