"""Experiment 3 — community masking (persona-level predictive IG).

Uses Group A's as-of persona assignments (no future leakage; features < cutoff).
For each community c (persona column x cluster label):
  (a) input-mask c's features to fold-train medians -> dNLL/dAUC on c's wallets
  (b) retrain-without-c diagnostic: train on all-but-c, predict c (CV)
Reports per-community size, mean member wallet-IG, mean volume.

Outputs: results/community_masking_20220901.json
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

OUT_JSON = C.RESULTS / "community_masking_20220901.json"


def feature_list(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in
            (set(C.ID_COLS) | set(C.LABEL_COLS) | set(C.TARGETS) |
             {"volume_usd", "log_volume_usd"} | set(C.PERSONA_COLS))]


def main() -> None:
    t0 = time.time()
    df = pd.read_parquet(C.RESULTS / "dataset_subset_20220901.parquet")
    feats = feature_list(df)
    target = C.PRIMARY_TARGET
    X = df[feats].to_numpy(dtype=float)
    y = df[target].to_numpy().astype(int)
    skf = StratifiedKFold(n_splits=C.CV_FOLDS, shuffle=True, random_state=C.SEED)

    # baseline full-model pooled metrics
    p_base = np.full(len(df), np.nan)
    pipes = {}
    for tr, te in skf.split(X, y):
        pipe = M.Pipeline("histgbm", seed=C.SEED).fit(X[tr], y[tr])
        pipes[te[0]] = pipe   # store one pipe per fold for reuse
        p_base[te] = pipe.predict_proba1(X[te])
    ok = ~np.isnan(p_base)
    full_metrics = {"nll": M.nll(y[ok], p_base[ok]), "auc": M.auc(y[ok], p_base[ok]),
                    "brier": float(np.mean((p_base[ok] - y[ok]) ** 2))}

    # wallet-level IG for member stats
    wig = pd.read_csv(C.RESULTS / "wallet_ig_20220901.csv")
    wig = wig[(wig.target == target) & (wig.model == "histgbm")][["target_address", "ig_occ"]]

    result = {"cutoff": C.CUTOFF, "target": target, "subset": int(len(df)),
              "full_model": full_metrics, "persona_cols": C.PERSONA_COLS}
    communities = {}
    for pcol in C.PERSONA_COLS:
        df[pcol] = df[pcol].fillna(-999).astype(int)
        for lab, grp in df.groupby(pcol):
            idx = grp.index.to_numpy()
            if len(idx) < 20:
                continue
            pos = {g: j for j, g in enumerate(idx)}
            idxset = set(idx)
            # (a) input-mask community features
            p_f = np.full(len(idx), np.nan)
            p_m = np.full(len(idx), np.nan)
            for tr, te in skf.split(X, y):
                pipe = M.Pipeline("histgbm", seed=C.SEED).fit(X[tr], y[tr])
                te_c = [i for i in te if i in idxset]
                if not te_c:
                    continue
                loc = [pos[i] for i in te_c]
                p_f[loc] = pipe.predict_proba1(X[te_c])
                Xm = M.mask_features(X, pipe.medians_, te_c)
                p_m[loc] = pipe.predict_proba1(Xm[te_c])
            okc = ~np.isnan(p_f)
            y_c = y[idx]
            # (b) retrain-without-c (diagnostic): model trained on non-c training rows
            p_wo = np.full(len(idx), np.nan)
            for tr, te in skf.split(X, y):
                te_c = [i for i in te if i in idxset]
                if not te_c:
                    continue
                loc = [pos[i] for i in te_c]
                tr_wo = [i for i in tr if i not in idxset]
                pipe = M.Pipeline("histgbm", seed=C.SEED).fit(X[tr_wo], y[tr_wo])
                p_wo[loc] = pipe.predict_proba1(X[te_c])
            okw = ~np.isnan(p_wo)
            n_masked = int(okc.sum())
            communities.setdefault(pcol, {})[int(lab)] = {
                "n_members_subset": int(len(idx)),
                "n_eval": n_masked,
                "base_rate": float(grp[target].mean()),
                "mean_volume_usd": float(grp["volume_usd"].mean()),
                "mean_wallet_ig": float(grp["target_address"].map(
                    wig.set_index("target_address")["ig_occ"]).mean()),
                "nll_full": M.nll(y_c[okc], p_f[okc]),
                "nll_masked": M.nll(y_c[okc], p_m[okc]),
                "delta_nll_mask": float(M.nll(y_c[okc], p_m[okc]) - M.nll(y_c[okc], p_f[okc])),
                "auc_full": M.auc(y_c[okc], p_f[okc]),
                "auc_masked": M.auc(y_c[okc], p_m[okc]),
                "delta_auc_mask": float(M.auc(y_c[okc], p_m[okc]) - M.auc(y_c[okc], p_f[okc])),
                "auc_available": bool(len(np.unique(y_c[okc])) == 2),
                "retrain_without_c_delta_nll": float(M.nll(y_c[okw], p_wo[okw]) - M.nll(y_c[okw], p_f[okw])),
            }
    result["communities"] = communities
    result["elapsed_sec"] = round(time.time() - t0, 1)

    # summarize: which communities have highest mean wallet IG
    summary = {}
    for pcol in C.PERSONA_COLS:
        coms = communities.get(pcol, {})
        if not coms:
            continue
        arr = pd.DataFrame(coms).T
        summary[pcol] = {
            "n_communities": int(len(arr)),
            "max_mean_wallet_ig_community": int(arr["mean_wallet_ig"].idxmax()),
            "max_mean_wallet_ig": float(arr["mean_wallet_ig"].max()),
            "max_delta_nll_mask_community": int(arr["delta_nll_mask"].idxmax()),
            "max_delta_nll_mask": float(arr["delta_nll_mask"].max()),
        }
    result["summary"] = summary
    (C.RESULTS / "community_masking_20220901.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"[community] done in {time.time()-t0:.1f}s -> {OUT_JSON}")
    for pcol, s in summary.items():
        print(f"[community] {pcol}: {s}")


if __name__ == "__main__":
    main()
