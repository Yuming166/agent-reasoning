"""Experiment 1 — wallet masking (per-wallet predictive information gain).

Method (panel-level, single cutoff 2022-09-01):
  IG_i(t) = H(Y_i | C_t) - H(Y_i | C_t, X_i(t))
  5-fold CV; for wallet i in the held-out fold:
    p_full  = P(Y_i | C_t, X_i(t))            (model trained on other wallets, actual features)
    p_mask  = P(Y_i | C_t)                    (same model, wallet i's features -> fold-train medians)
    IG_i    = NLL(p_mask) - NLL(p_full)       (out-of-sample; positive = history reduces uncertainty)
  Aggregate wallet-subset masking: mask top-K / bottom-K / volume-top-K wallets'
  features and report pooled dNLL/dAUC on those wallets.

Also a permutation robustness check (features replaced by another wallet's features)
and a retraining diagnostic: train with top-100 IG wallets' rows removed vs kept,
measure pooled dNLL on the held-out eval fold (panel-level cross-wallet effect).

Outputs: results/wallet_ig_20220901.csv, results/wallet_masking_20220901.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
import config as C
import models as M

OUT_CSV = C.RESULTS / "wallet_ig_20220901.csv"
OUT_JSON = C.RESULTS / "wallet_masking_20220901.json"


def run_target(df: pd.DataFrame, target: str, model_name: str, seed: int = C.SEED) -> pd.DataFrame:
    feats = [c for c in df.columns if c not in
             (set(C.ID_COLS) | set(C.LABEL_COLS) | set(C.TARGETS) |
              {"volume_usd", "log_volume_usd"} | set(C.PERSONA_COLS))]
    X = df[feats].to_numpy(dtype=float)
    y = df[target].to_numpy().astype(int)
    n = len(df)
    skf = StratifiedKFold(n_splits=C.CV_FOLDS, shuffle=True, random_state=seed)
    p_full = np.full(n, np.nan)
    p_mask = np.full(n, np.nan)
    p_perm = np.full(n, np.nan)
    # permutation: replace with a random other wallet's features (average 3 draws)
    rng = np.random.default_rng(seed + 1)
    perm_idx = np.stack([rng.permutation(n) for _ in range(3)], axis=0)
    fold = np.full(n, -1)
    for f, (tr, te) in enumerate(skf.split(X, y)):
        fold[te] = f
        pipe = M.Pipeline(model_name, seed=seed).fit(X[tr], y[tr])
        p_full[te] = pipe.predict_proba1(X[te])
        p_mask[te] = pipe.predict_proba1(M.mask_features(X[te], pipe.medians_))
        # permutation: each eval row gets features of another wallet (3 averaged)
        p3 = np.zeros(len(te))
        for d in range(3):
            donor = perm_idx[d][te]          # donor index for each eval row
            Xp = X[te].copy()
            Xp[:] = X[donor, :]
            p3 += pipe.predict_proba1(Xp) / 3.0
        p_perm[te] = clip3(p3)
    out = pd.DataFrame({
        "target_address": df["target_address"].values,
        "target_exgraph_node_id": df["target_exgraph_node_id"].values,
        "target": target,
        "model": model_name,
        "y": y,
        "fold": fold,
        "p_full": p_full,
        "p_mask": p_mask,
        "p_perm": p_perm,
        "nll_full": -np.log(np.where(y == 1, M.clip(p_full), 1.0 - M.clip(p_full))),
        "nll_mask": -np.log(np.where(y == 1, M.clip(p_mask), 1.0 - M.clip(p_mask))),
        "nll_perm": -np.log(np.where(y == 1, M.clip(p_perm), 1.0 - M.clip(p_perm))),
    })
    out["ig_occ"] = out["nll_mask"] - out["nll_full"]
    out["ig_perm"] = out["nll_perm"] - out["nll_full"]
    return out


def clip3(p: np.ndarray) -> np.ndarray:
    return M.clip(p)


def subset_mask_metrics(out: pd.DataFrame, target: str, model_name: str, df: pd.DataFrame):
    """Aggregate dNLL/dAUC when a wallet subset's features are masked to median."""
    res = {}
    ig = out[out["target"] == target].set_index("target_address")["ig_occ"].sort_values(ascending=False)
    vol = df.set_index("target_address")["volume_usd"]
    vol_top = vol.sort_values(ascending=False).index.tolist()
    ig_top = ig.index.tolist()
    ig_bot = ig.index.tolist()[::-1]
    subsets = {"top50_ig": ig_top[:50], "top100_ig": ig_top[:100], "top500_ig": ig_top[:500],
               "bottom50_ig": ig_bot[:50], "vol_top50": vol_top[:50], "vol_top100": vol_top[:100]}
    feats = [c for c in df.columns if c not in
             (set(C.ID_COLS) | set(C.LABEL_COLS) | set(C.TARGETS) |
              {"volume_usd", "log_volume_usd"} | set(C.PERSONA_COLS))]
    X = df[feats].to_numpy(dtype=float)
    y = df[target].to_numpy().astype(int)
    skf = StratifiedKFold(n_splits=C.CV_FOLDS, shuffle=True, random_state=C.SEED)
    for name, wallets in subsets.items():
        p_full_all = np.full(len(df), np.nan)
        p_mask_all = np.full(len(df), np.nan)
        for tr, te in skf.split(X, y):
            pipe = M.Pipeline(model_name, seed=C.SEED).fit(X[tr], y[tr])
            mask_rows = [i for i in te if df["target_address"].iloc[i] in set(wallets)]
            if not mask_rows:
                continue
            p_full_all[mask_rows] = pipe.predict_proba1(X[mask_rows])
            Xm = M.mask_features(X, pipe.medians_, mask_rows)
            p_mask_all[mask_rows] = pipe.predict_proba1(Xm[mask_rows])
        ok = ~np.isnan(p_full_all)
        res[name] = {
            "n_masked": int(ok.sum()),
            "nll_full": M.nll(y[ok], p_full_all[ok]),
            "nll_masked": M.nll(y[ok], p_mask_all[ok]),
            "delta_nll": float(M.nll(y[ok], p_mask_all[ok]) - M.nll(y[ok], p_full_all[ok])),
            "auc_full": M.auc(y[ok], p_full_all[ok]),
            "auc_masked": M.auc(y[ok], p_mask_all[ok]),
            "delta_auc": float(M.auc(y[ok], p_mask_all[ok]) - M.auc(y[ok], p_full_all[ok])),
            "brier_full": float(np.mean((p_full_all[ok] - y[ok]) ** 2)),
            "brier_masked": float(np.mean((p_mask_all[ok] - y[ok]) ** 2)),
            "delta_brier": float(np.mean((p_mask_all[ok] - y[ok]) ** 2) - np.mean((p_full_all[ok] - y[ok]) ** 2)),
            "mean_p_full": float(np.mean(p_full_all[ok])),
            "mean_p_masked": float(np.mean(p_mask_all[ok])),
            "auc_available": bool(len(np.unique(y[ok])) == 2),
        }
    return res


def retraining_diagnostic(df: pd.DataFrame, target: str, model_name: str, k: int = 100, seed: int = C.SEED):
    """Panel-level cross-wallet diagnostic: remove top-IG wallets' rows from TRAINING.

    i.i.d. panel rows -> expected near-zero effect; documents the boundary that
    panel-level wallet masking measures self-predictive information, not
    cross-wallet influence (the latter needs the event/candidate-level task).
    """
    feats = [c for c in df.columns if c not in
             (set(C.ID_COLS) | set(C.LABEL_COLS) | set(C.TARGETS) |
              {"volume_usd", "log_volume_usd"} | set(C.PERSONA_COLS))]
    X = df[feats].to_numpy(dtype=float)
    y = df[target].to_numpy().astype(int)
    skf = StratifiedKFold(n_splits=C.CV_FOLDS, shuffle=True, random_state=seed)
    ig = df[["target_address", target]].copy()
    ig = ig.merge(pd.read_csv(OUT_CSV, usecols=["target_address", "target", "model", "ig_occ"])
                  .query("target == @target and model == @model_name")[["target_address", "ig_occ"]],
                  on="target_address", how="left")
    top = ig.sort_values("ig_occ", ascending=False).head(k)["target_address"].tolist()
    top_set = set(top)
    p_keep = np.full(len(df), np.nan)
    p_drop = np.full(len(df), np.nan)
    for tr, te in skf.split(X, y):
        pipe = M.Pipeline(model_name, seed=seed).fit(X[tr], y[tr])
        p_keep[te] = pipe.predict_proba1(X[te])
        # retrain without top-IG wallets present in the training context
        tr_wo = [i for i in tr if df["target_address"].iloc[i] not in top_set]
        pipe2 = M.Pipeline(model_name, seed=seed).fit(X[tr_wo], y[tr_wo])
        p_drop[te] = pipe2.predict_proba1(X[te])
    ok = ~np.isnan(p_keep)
    return {
        "k": k,
        "n_top_wallets": len(top_set),
        "pooled_nll_keep": M.nll(y[ok], p_keep[ok]),
        "pooled_nll_drop": M.nll(y[ok], p_drop[ok]),
        "pooled_delta_nll": float(M.nll(y[ok], p_drop[ok]) - M.nll(y[ok], p_keep[ok])),
        "pooled_auc_keep": M.auc(y[ok], p_keep[ok]),
        "pooled_auc_drop": M.auc(y[ok], p_drop[ok]),
        "note": "i.i.d. panel rows: removing wallet rows from training has near-zero effect on "
                "other wallets' predictions; cross-wallet IG requires event/candidate-level task",
    }


def main() -> None:
    df = pd.read_parquet(C.RESULTS / "dataset_subset_20220901.parquet")
    t0 = time.time()
    frames = []
    summary = {}
    for target in C.TARGETS:
        for model_name in ["histgbm", "logistic"]:
            print(f"[wallet_masking] {model_name} / {target} ...", flush=True)
            out = run_target(df, target, model_name)
            frames.append(out)
            nll_full = M.nll(out["y"].values, out["p_full"].values)
            nll_mask = M.nll(out["y"].values, out["p_mask"].values)
            a_full = M.auc(out["y"].values, out["p_full"].values)
            a_mask = M.auc(out["y"].values, out["p_mask"].values)
            summary[f"{model_name}__{target}"] = {
                "n": int(len(out)),
                "base_rate": float(out["y"].mean()),
                "nll_full": float(nll_full),
                "nll_mask_all": float(nll_mask),
                "delta_nll_all": float(nll_mask - nll_full),
                "auc_full": float(a_full),
                "auc_mask_all": float(a_mask),
                "delta_auc_all": float(a_mask - a_full),
                "ig_occ_mean": float(out["ig_occ"].mean()),
                "ig_occ_median": float(out["ig_occ"].median()),
                "ig_occ_top5": out.sort_values("ig_occ", ascending=False).head(5)["target_address"].tolist(),
            }
            print(f"  nll_full={nll_full:.4f} nll_mask={nll_mask:.4f} "
                  f"dNLL_all={nll_mask-nll_full:+.4f} AUC={a_full:.4f}->{a_mask:.4f}")
    out_all = pd.concat(frames, ignore_index=True)
    out_all.to_csv(OUT_CSV, index=False)
    print(f"[wallet_masking] saved {OUT_CSV} rows={len(out_all)}")

    # aggregate subset masks + retraining diagnostic on primary target / histgbm
    agg = {}
    for target in C.TARGETS:
        for model_name in ["histgbm", "logistic"]:
            agg[f"{model_name}__{target}"] = subset_mask_metrics(out_all, target, model_name, df)
    diag = retraining_diagnostic(df, C.PRIMARY_TARGET, "histgbm")
    result = {
        "method": "5-fold CV input occlusion; IG_i = NLL(P(Y|C_t)) - NLL(P(Y|C_t, X_i(t)))",
        "cutoff": C.CUTOFF,
        "label_window": C.LABEL_WINDOW,
        "subset": int(len(df)),
        "models": ["histgbm", "logistic"],
        "summary": summary,
        "subset_masking": agg,
        "retraining_diagnostic": diag,
        "elapsed_sec": round(time.time() - t0, 1),
        "claim_boundary": "predictive information gain (self-predictability at wallet level); "
                          "NOT causal influence; NOT cross-wallet influence",
    }
    (C.RESULTS / "wallet_masking_20220901.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"[wallet_masking] done in {time.time()-t0:.1f}s -> {OUT_JSON}")


if __name__ == "__main__":
    main()
