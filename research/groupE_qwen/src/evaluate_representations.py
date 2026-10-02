"""Downstream validation of Qwen semantic representation (descriptive pilot).

Compares, on the SAME 200-wallet sample and SAME 5-fold split:
  R_num    : Group A as-of numeric representation (57 features)
  R_traj   : trajectory/timing representation only
  R_qwen   : Qwen summary embedding (1024-dim -> PCA-64)
  R_num+qwen, R_traj+qwen : combined (concatenation)

Metric: 5-fold out-of-fold Ridge R2 and Spearman rho for log1p(fwd30_*) labels.
Also reports an OOF kNN(k=5) regression on the Qwen embedding as a second
descriptor. All numbers are descriptive on a small bounded sample; no
effectiveness/superiority/causality claim is made.

Fidelity check (NOT ground truth): ordinal agreement between the Qwen
`activity_regime` token and the numeric activity tier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402   # Group E config FIRST (so it is not shadowed)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "groupA_behavior" / "src"))
import cluster_personas as cp  # noqa: E402


def load_aligned() -> pd.DataFrame:
    sample = pd.read_csv(config.SAMPLE_CSV)
    df = pd.read_parquet(config.FEATURE_MATRIX)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    df = df[df["target_address"].isin(sample["target_address"])].copy()
    df = cp.add_derived(df)
    # summaries
    summ = {}
    for line in open(config.SUMMARIES_JSONL, encoding="utf-8"):
        r = json.loads(line)
        summ[r["target_address"]] = r
    df["parse_ok"] = df["target_address"].map(lambda a: summ.get(a, {}).get("parse_ok", False))
    df["activity_regime"] = df["target_address"].map(
        lambda a: (summ.get(a, {}).get("parsed") or {}).get("activity_regime"))
    tier = sample[["target_address", "activity_tier"]]
    df = df.merge(tier, on="target_address", how="left")
    return df.set_index("target_address"), summ


def build_reps(df: pd.DataFrame) -> dict[str, np.ndarray]:
    X_num = cp.prepare_matrix(df, [cp.ACTIVITY, cp.CAPITAL, cp.COUNTERPARTIES,
                                   cp.NETWORK, cp.TRAJECTORY]).to_numpy()
    X_traj = cp.prepare_matrix(df, [cp.TRAJECTORY]).to_numpy()

    # Qwen embeddings aligned by address
    emb_rows = {}
    for line in open(config.EMBEDDINGS_JSONL, encoding="utf-8"):
        r = json.loads(line)
        emb_rows[r["target_address"]] = r["embedding"]
    order = df.index.tolist()
    X_q = np.array([emb_rows[a] for a in order])
    sc = StandardScaler().fit(X_q)
    pca = PCA(n_components=min(config.PCA_DIM, X_q.shape[0] - 1), random_state=config.VAL_SEED)
    X_qp = pca.fit_transform(sc.transform(X_q))
    print(f"[eval] embedding PCA: {X_qp.shape[1]} components, explained_var={pca.explained_variance_ratio_.sum():.3f}")

    X_num_s = StandardScaler().fit_transform(X_num)
    X_traj_s = StandardScaler().fit_transform(X_traj)
    return {
        "R_num": X_num_s,
        "R_traj": X_traj_s,
        "R_qwen_pca": X_qp,
        "R_num+qwen": np.hstack([X_num_s, X_qp]),
        "R_traj+qwen": np.hstack([X_traj_s, X_qp]),
        "_X_q_raw": X_q,
    }


def oof_ridge(X: np.ndarray, y: np.ndarray, folds, alpha: float | None = None) -> tuple[float, float, np.ndarray]:
    yhat = np.full_like(y, np.nan)
    for tr, te in folds:
        m = Ridge(alpha=config.RIDGE_ALPHA if alpha is None else alpha).fit(X[tr], y[tr])
        yhat[te] = m.predict(X[te])
    r2 = 1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
    rho = sps.spearmanr(y, yhat).statistic
    return float(r2), float(rho), yhat


def oof_knn(X: np.ndarray, y: np.ndarray, folds, k: int = 5) -> float:
    from sklearn.neighbors import KNeighborsRegressor
    yhat = np.full_like(y, np.nan)
    for tr, te in folds:
        knn = KNeighborsRegressor(n_neighbors=min(k, len(tr)), weights="distance")
        knn.fit(X[tr], y[tr])
        yhat[te] = knn.predict(X[te])
    return float(1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2))


def main() -> None:
    df, summ = load_aligned()
    reps = build_reps(df)
    kf = KFold(n_splits=config.N_FOLDS, shuffle=True, random_state=config.VAL_SEED)
    folds = list(kf.split(df.index.to_numpy()))

    results = {"cutoff": config.CUTOFF, "protocol_ref": config.PROTOCOL_REF,
               "n_wallets": int(len(df)), "n_folds": config.N_FOLDS,
               "seed": config.VAL_SEED, "scope": "descriptive small-sample pilot on the 200-wallet representative subset"}
    rows_out = []

    for target in config.LABELS:
        y = np.log1p(df[target].to_numpy().astype(float))
        per_target = {"target": target}
        for name in ["R_num", "R_traj", "R_qwen_pca", "R_num+qwen", "R_traj+qwen"]:
            X = reps[name]
            r2, rho, _ = oof_ridge(X, y, folds)
            per_target[name] = {"oof_ridge_r2": r2, "oof_spearman": rho}
        # stronger regularization: alpha=10 (checks overparameterization on n=200)
        for name in ["R_num", "R_traj", "R_qwen_pca", "R_num+qwen", "R_traj+qwen"]:
            X = reps[name]
            r2, rho, _ = oof_ridge(X, y, folds, alpha=10.0)
            per_target[name + "@a10"] = {"oof_ridge_r2": r2, "oof_spearman": rho}
        per_target["R_qwen_pca_knn_k5_r2"] = oof_knn(reps["_X_q_raw"], y, folds)
        rows_out.append(per_target)
        print(f"\n[{target}]")
        for name in ["R_num", "R_traj", "R_qwen_pca", "R_num+qwen", "R_traj+qwen"]:
            print(f"  {name:14s} R2={per_target[name]['oof_ridge_r2']:+.4f} rho={per_target[name]['oof_spearman']:+.4f}")
        for name in ["R_num@a10", "R_traj@a10", "R_qwen_pca@a10", "R_num+qwen@a10", "R_traj+qwen@a10"]:
            print(f"  {name:14s} R2={per_target[name]['oof_ridge_r2']:+.4f} rho={per_target[name]['oof_spearman']:+.4f}")
        print(f"  R_qwen_pca_knn_k5 R2={per_target['R_qwen_pca_knn_k5_r2']:+.4f}")

    # complementarity deltas (descriptive)
    comp = {}
    for t in rows_out:
        d = t["target"]
        comp[d] = {
            "delta_r2_qwen_over_num": round(t["R_qwen_pca"]["oof_ridge_r2"] - t["R_num"]["oof_ridge_r2"], 4),
            "delta_r2_num_qwen_over_num": round(t["R_num+qwen"]["oof_ridge_r2"] - t["R_num"]["oof_ridge_r2"], 4),
            "delta_r2_traj_qwen_over_traj": round(t["R_traj+qwen"]["oof_ridge_r2"] - t["R_traj"]["oof_ridge_r2"], 4),
        }
    results["tables"] = rows_out
    results["complementarity_deltas"] = comp

    # fidelity check: Qwen activity_regime vs numeric activity tier (ordinal)
    regime_map = {"very_low": 0, "low": 1, "medium": 2, "high": 3, "very_high": 4}
    tier_map = {"low": 1, "mid": 2, "high": 3}
    df["_regime_int"] = df["activity_regime"].map(regime_map)
    df["_tier_int"] = df["activity_tier"].map(tier_map)
    sub = df.dropna(subset=["_regime_int", "_tier_int"])
    tau = sps.kendalltau(sub["_tier_int"], sub["_regime_int"]).statistic
    rho_regime = sps.spearmanr(sub["_tier_int"], sub["_regime_int"]).statistic
    # redundancy: OOF R2 of predicting each Qwen-embedding PCA dim from R_num
    from sklearn.linear_model import Ridge
    Xn = reps["R_num"]
    Xq = reps["R_qwen_pca"]
    r2s = []
    for j in range(Xq.shape[1]):
        r2, _, _ = oof_ridge(Xn, Xq[:, j], folds)
        r2s.append(r2)
    results["qwen_embedding_redundancy"] = {
        "note": "OOF R2 of predicting each Qwen-embedding PCA dim from numeric features; high = largely redundant, low = carries new info",
        "mean_r2_embed_dims_predictable_from_num": float(np.mean(r2s)),
        "n_dims": int(len(r2s)),
        "dims_r2_gt0_5": int(sum(1 for v in r2s if v > 0.5)),
        "first10_r2": [float(v) for v in r2s[:10]],
    }

    results["fidelity_activity_regime"] = {
        "note": "ordinal agreement between Qwen activity_regime token and numeric evt_cnt tercile; NOT ground truth",
        "n_with_regime_token": int(len(sub)),
        "kendall_tau": float(tau), "spearman_rho": float(rho_regime),
        "regime_token_counts": df["activity_regime"].value_counts().to_dict(),
    }
    results["parse_yield"] = float(df["parse_ok"].mean())
    results["n_parse_ok"] = int(df["parse_ok"].sum())

    # qualitative examples (5)
    ex = []
    for a in df.index[:5]:
        s = summ.get(a, {})
        ex.append({"address": a, "parse_ok": s.get("parse_ok"),
                   "behavior_pattern": (s.get("parsed") or {}).get("behavior_pattern"),
                   "uncertainty": (s.get("parsed") or {}).get("uncertainty")})
    results["qualitative_examples"] = ex

    (config.EVAL_JSON).write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print("\n[ok] wrote", config.EVAL_JSON)


if __name__ == "__main__":
    main()
