"""Evaluate Group A personas: stability, bootstrap consistency, temporal
persistence, and descriptive downstream utility.

Scope: cutoff 2022-09-01, n=18,519 wallets (bounded sample). All numbers are
preliminary descriptive diagnostics, NOT effectiveness/superiority claims.

Stability
  * subsampling: 5x 80% subsample -> refit -> ARI vs full-sample labels
  * perturbation: add N(0, 0.1*col_std) noise -> refit -> ARI vs full labels
Bootstrap consistency: 10x bootstrap resample -> refit -> ARI vs full labels
  (mean + 95% interval)
Temporal persistence
  * monthly snapshots May-Aug (wallet_asof_features_v1) + Sep (20220901),
    K-means K=4 on the common as-of feature subset, ARI between adjacent
    months and vs Sep; per-feature Spearman rank correlation May vs Sep;
    persona transition matrix Aug -> Sep (overlapping wallets)
Downstream utility (descriptive, in-sample)
  * per-persona future 30d means (fwd30_evt_cnt, fwd30_new_cp)
  * OLS R2: log1p(fwd30_evt_cnt) ~ persona one-hot vs ~ continuous features
    vs combined; delta is descriptive, not a predictive validation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler

import hdbscan

sys.path.insert(0, str(Path(__file__).parent))
import cluster_personas as cp  # noqa: E402
import config  # noqa: E402

SEED = 2022
rng = np.random.default_rng(SEED)

# focused configs for stability/bootstrap (runtime-bounded)
STAB_CONFIGS = [
    ("full_asof__kmeans", lambda X: KMeans(n_clusters=4, n_init=10, random_state=SEED).fit(X).labels_),
    ("full_asof__gmm", lambda X: __import__("sklearn.mixture", fromlist=["GaussianMixture"]).GaussianMixture(
        n_components=4, covariance_type="diag", n_init=5, random_state=SEED).fit(X).predict(X)),
    ("trajectory__kmeans", lambda X: KMeans(n_clusters=5, n_init=10, random_state=SEED).fit(X).labels_),
]
HDBSCAN_CONFIG = ("full_asof__hdbscan_mcs30",
                  lambda X: hdbscan.HDBSCAN(min_cluster_size=30, min_samples=5,
                                            metric="euclidean").fit(X).labels_)

MONTHLY_COMMON = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
    "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d",
    "active_span_days_90d", "cp_distinct_90d", "cp_out_distinct_90d",
    "cp_in_distinct_90d", "cp_out_interact_90d", "cp_in_interact_90d",
    "token_distinct_90d", "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d",
    "cp_both_dir_90d", "cp_reciprocity_90d", "self_tx_rate_90d",
    "token_event_rate_90d", "token_hhi_90d", "events_per_active_day_90d",
]


def prepare_monthly(df: pd.DataFrame) -> pd.DataFrame:
    X = df[MONTHLY_COMMON].copy()
    log_cols = [c for c in MONTHLY_COMMON if c not in {
        "cp_entropy_90d", "cp_new_rate_30d", "cp_reciprocity_90d",
        "self_tx_rate_90d", "token_event_rate_90d", "token_hhi_90d",
        "events_per_active_day_90d"}]
    for c in log_cols:
        X[c] = np.log1p(X[c].clip(lower=0))
    X = X.apply(lambda col: col.fillna(col.median()))
    lo = X.quantile(0.005); hi = X.quantile(0.995)
    X = X.clip(lo, hi, axis=1)
    return pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns, index=X.index)


def aris_for(name: str, fitter, X: np.ndarray, full_labels: np.ndarray,
             draws: int, mode: str) -> dict:
    aris = []
    for i in range(draws):
        if mode == "subsample":
            idx = rng.choice(len(X), size=int(0.8 * len(X)), replace=False)
            lab = fitter(X[idx])
            full_side = full_labels[idx]
        elif mode == "bootstrap":
            idx = rng.choice(len(X), size=len(X), replace=True)
            lab = fitter(X[idx])
            full_side = full_labels[idx]
        elif mode == "perturb":
            noise = rng.normal(0, 0.1, size=X.shape)
            lab = fitter(X + noise)
            full_side = full_labels
        aris.append(adjusted_rand_score(full_side, lab))
    aris = np.array(aris)
    return {
        "model": name, "mode": mode, "n_draws": draws,
        "ari_mean": float(aris.mean()), "ari_std": float(aris.std()),
        "ari_min": float(aris.min()), "ari_max": float(aris.max()),
        "ari_95ci": [float(np.percentile(aris, 2.5)), float(np.percentile(aris, 97.5))],
    }


def main() -> None:
    results = config.RESULTS
    data_dir = results / "data"
    df = pd.read_parquet(data_dir / "feature_matrix_20220901.parquet")
    df = cp.add_derived(df)
    assign = pd.read_csv(results / "persona_assignments_20220901.csv")
    assign = assign.set_index("target_address")

    X_full = cp.prepare_matrix(df, [cp.ACTIVITY, cp.CAPITAL, cp.COUNTERPARTIES,
                                    cp.NETWORK, cp.TRAJECTORY]).to_numpy()
    X_traj = cp.prepare_matrix(df, [cp.TRAJECTORY]).to_numpy()
    X_map = {"full_asof__kmeans": X_full, "full_asof__gmm": X_full,
             "trajectory__kmeans": X_traj}

    report = {"cutoff": config.CUTOFF, "sample_scope": f"{len(df)} wallets (wallet_asof_features_20220901 partition 2022-09-01)"}

    # ---------- 1) stability + bootstrap ----------
    stability = []
    for name, fitter in STAB_CONFIGS:
        full_labels = assign[name].to_numpy()
        stability.append(aris_for(name, fitter, X_map[name], full_labels, 5, "subsample"))
        stability.append(aris_for(name, fitter, X_map[name], full_labels, 5, "perturb"))
        stability.append(aris_for(name, fitter, X_map[name], full_labels, 10, "bootstrap"))
    report["stability_bootstrap"] = stability

    # ---------- 2) temporal persistence (monthly K-means K=4) ----------
    monthly = pd.read_parquet(data_dir / "asof_monthly_2022.parquet")
    monthly["target_address"] = monthly["target_address"].str.lower()
    sep = df[["target_address"] + MONTHLY_COMMON].copy()
    sep["snapshot_date"] = config.CUTOFF
    allm = pd.concat([monthly, sep], ignore_index=True)
    allm = allm.drop_duplicates(subset=["snapshot_date", "target_address"])

    K = 4
    month_labels = {}
    for snap, g in allm.groupby("snapshot_date"):
        g = g.sort_values("target_address").reset_index(drop=True)
        Xm = prepare_monthly(g)
        km = KMeans(n_clusters=K, n_init=10, random_state=SEED).fit(Xm)
        month_labels[str(snap)] = (g[["target_address"] + MONTHLY_COMMON].copy(), km.labels_)
    snaps = sorted(month_labels.keys())
    ari_adj = {}
    for a, b in zip(snaps, snaps[1:]):
        dfa = month_labels[a][0].reset_index(); dfb = month_labels[b][0].reset_index()
        m = dfa.merge(dfb, on="target_address", how="inner")
        if len(m) == 0:
            continue
        la_full = np.array([month_labels[a][1][getattr(row, "index_x")] for row in m.itertuples(index=False)])
        lb_full = np.array([month_labels[b][1][getattr(row, "index_y")] for row in m.itertuples(index=False)])
        ari_adj[f"{a}->{b}"] = {
            "ari": float(adjusted_rand_score(la_full, lb_full)),
            "n_overlap": int(len(m)),
        }
    # feature-level persistence: Spearman rank correlation May vs Sep (common features)
    m_may = month_labels["2022-05-01"][0].merge(month_labels["2022-09-01"][0], on="target_address",
                                                how="inner", suffixes=("_may", "_sep"))
    feat_persist = {}
    for c in MONTHLY_COMMON:
        cm, cs = f"{c}_may", f"{c}_sep"
        if cm in m_may.columns and cs in m_may.columns:
            rho, pval = sps.spearmanr(m_may[cm], m_may[cs], nan_policy="omit")
            feat_persist[c] = {"spearman_rho": float(rho), "p": float(pval),
                               "n_overlap": int(len(m_may))}
    # persona transition matrix Aug -> Sep (K=4, common features)
    tr = {}
    aug = month_labels["2022-08-01"][0].copy(); aug["lab"] = month_labels["2022-08-01"][1]
    sep_l = month_labels["2022-09-01"][0].copy(); sep_l["lab"] = month_labels["2022-09-01"][1]
    tr_df = aug.merge(sep_l, on="target_address", how="inner", suffixes=("_aug", "_sep"))
    tr_df = tr_df.groupby(["lab_aug", "lab_sep"]).size().reset_index(name="n")
    tr_df["prob"] = tr_df["n"] / tr_df.groupby("lab_aug")["n"].transform("sum")
    tr = tr_df.to_dict("records")
    report["temporal_persistence"] = {
        "kmeans_k": K,
        "common_feature_subset": MONTHLY_COMMON,
        "adjacent_month_ari": ari_adj,
        "feature_spearman_may_vs_sep": feat_persist,
        "transition_matrix_aug_to_sep": tr,
    }

    # ---------- 3) downstream utility (descriptive, in-sample) ----------
    labels = df[["target_address", "fwd30_evt_cnt", "fwd30_cp_distinct",
                 "fwd30_new_cp"]].set_index("target_address")
    y = np.log1p(labels["fwd30_evt_cnt"].clip(lower=0).to_numpy())
    utility = {}
    for name in ["full_asof__kmeans", "full_asof__gmm", "full_asof__hdbscan",
                 "trajectory__kmeans", "network__kmeans"]:
        lab = assign[name].to_numpy()
        valid = lab != -1
        prof = df[["target_address", "fwd30_evt_cnt", "fwd30_new_cp"]].copy()
        prof["persona"] = lab
        pers_mean = prof[valid].groupby("persona")[["fwd30_evt_cnt", "fwd30_new_cp"]].mean()
        glob_mean = prof["fwd30_evt_cnt"].mean()
        # categorical OLS: persona one-hot on log1p(fwd30_evt_cnt)
        Z = pd.get_dummies(pd.Series(lab[valid]), prefix="p").to_numpy(dtype=float)
        reg = LinearRegression().fit(Z, y[valid])
        r2_persona = reg.score(Z, y[valid])
        # continuous feature OLS (full as-of matrix)
        Xc = X_full[valid]
        regc = LinearRegression().fit(Xc, y[valid])
        r2_feat = regc.score(Xc, y[valid])
        # combined
        Xcomb = np.hstack([Z, Xc])
        regb = LinearRegression().fit(Xcomb, y[valid])
        r2_comb = regb.score(Xcomb, y[valid])
        utility[name] = {
            "n_valid": int(valid.sum()),
            "per_persona_mean_fwd30_evt": pers_mean["fwd30_evt_cnt"].round(3).to_dict(),
            "per_persona_mean_fwd30_new_cp": pers_mean["fwd30_new_cp"].round(3).to_dict(),
            "global_mean_fwd30_evt": float(glob_mean),
            "r2_persona_only_in_sample": float(r2_persona),
            "r2_features_only_in_sample": float(r2_feat),
            "r2_combined_in_sample": float(r2_comb),
            "delta_r2_persona_over_features_in_sample": float(r2_comb - r2_feat),
        }
    report["downstream_utility_descriptive"] = utility

    (results / "evaluation_20220901.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False)[:4000])
    print("\n[ok] wrote results/evaluation_20220901.json")


if __name__ == "__main__":
    main()
