#!/usr/bin/env python3
"""Train the FROZEN pre-call budget router on June measured gains; use July
only to select the model iteration/depth; evaluate August without refit.

Router input = pre-LLM as-of features only. Score = predicted E[gain_full].
At budget b, route the top-b events to the full counterfactual FSM, else use
the cheap ranker. Policies compared: router, cp_type(repeat), mask-sensitive
(post-hoc reference; uses an in-FSM signal), random, oracle, all-cheap,
all-full. Reports weighted MRR and paired bootstrap CIs on August.
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.build_router_dataset import FEATURES  # noqa: E402

BUDGETS = [0.05, 0.10, 0.20, 0.50, 0.75]


def wmean(x, w):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    m = ~np.isnan(x)
    return float((x[m] * w[m]).sum() / w[m].sum())


def policy_mrr(df, route_flag):
    flag = np.asarray(route_flag, bool)
    return wmean(np.where(flag, df.full_rr, df.cheap_rr), df.pop_weight)


def boot_delta(df, flag_a, flag_b, n=3000, seed=3):
    a = np.where(flag_a, df.full_rr, df.cheap_rr)
    b = np.where(flag_b, df.full_rr, df.cheap_rr)
    d = a - b
    w = df.pop_weight.to_numpy()
    m = ~np.isnan(d)
    d, w = d[m], w[m]
    rng = np.random.default_rng(seed)
    bs = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, len(d), len(d))
        bs[i] = (d[idx] * w[idx]).sum() / w[idx].sum()
    return float((d * w).sum() / w.sum()), [float(np.percentile(bs, 2.5)),
                                             float(np.percentile(bs, 97.5))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    ds = pd.read_csv(args.dataset)
    tr = ds[ds.snapshot_date == "2022-06-01"]
    va = ds[ds.snapshot_date == "2022-07-01"]
    te = ds[ds.snapshot_date == "2022-08-01"]

    from sklearn.ensemble import HistGradientBoostingRegressor
    # grid selected ONLY on July mean routing utility across fixed budgets
    grid = [(50, 3), (100, 3), (200, 3), (100, None), (200, None)]
    best = None
    for it, depth in grid:
        m = HistGradientBoostingRegressor(max_iter=it, max_depth=depth,
                                          learning_rate=0.05, l2_regularization=1.0,
                                          random_state=11)
        m.fit(tr[FEATURES].to_numpy(), tr.gain_full.to_numpy())
        va = va.copy()
        va["score"] = m.predict(va[FEATURES].to_numpy())
        util = []
        for b in [0.1, 0.2, 0.5]:
            k = int(round(b * len(va)))
            flag = np.zeros(len(va), bool)
            flag[np.argsort(-va.score.to_numpy())[:k]] = True
            util.append(policy_mrr(va, flag))
        cand = (float(np.mean(util)), it, depth, m)
        if best is None or cand[0] > best[0]:
            best = cand
    _, it, depth, model = best
    with open(os.path.join(args.outdir, "budget_router_jun_frozen.pkl"), "wb") as f:
        pickle.dump({"model": model, "features": FEATURES,
                     "selected": {"max_iter": it, "max_depth": depth}}, f)

    te = te.copy()
    te["router_score"] = model.predict(te[FEATURES].to_numpy())
    rng = np.random.default_rng(7)

    # mask_sensitive is an in-FSM signal: join from the August run separately
    # via full_rr availability is not enough; caller dataset lacks it, so build
    # the flag from optional column if present.
    has_msens = "mask_sensitive" in te.columns

    rows = []
    n = len(te)
    for b in BUDGETS:
        k = max(1, int(round(b * n)))
        flags = {}
        flags["router"] = np.zeros(n, bool)
        flags["router"][np.argsort(-te.router_score.to_numpy())[:k]] = True
        flags["repeat"] = np.zeros(n, bool)
        # top-k by (repeat-first, then router) to honor fixed budget
        order = sorted(range(n), key=lambda i: (te.cp_type.iloc[i] != "repeat",
                                                -te.router_score.iloc[i]))
        flags["repeat"][order[:k]] = True
        rand_flags = []
        for _ in range(100):
            f = np.zeros(n, bool)
            f[rng.choice(n, k, replace=False)] = True
            rand_flags.append(f)
        flags["oracle"] = np.zeros(n, bool)
        flags["oracle"][np.argsort(-te.gain_full.fillna(-9).to_numpy())[:k]] = True
        if "mask_sensitive" in te.columns:
            ms = pd.to_numeric(te.mask_sensitive, errors="coerce").fillna(0).to_numpy()
            flags["msens"] = np.zeros(n, bool)
            ms_order = sorted(range(n), key=lambda i: (-int(ms[i]), -float(te.router_score.iloc[i])))
            for i in ms_order[:k]:
                flags["msens"][i] = True
        row = {"budget": b, "k": k}
        for name, fl in flags.items():
            row["mrr_" + name] = round(policy_mrr(te, fl), 4)
        row["mrr_random"] = round(float(np.mean([policy_mrr(te, f) for f in rand_flags])), 4)
        rows.append(row)

    endpoints = {
        "mrr_all_cheap": round(wmean(te.cheap_rr, te.pop_weight), 4),
        "mrr_all_full": round(wmean(te.full_rr, te.pop_weight), 4),
        "mrr_oracle_max": round(wmean(np.maximum(te.cheap_rr, te.full_rr), te.pop_weight), 4),
        "selected_hyperparams": {"max_iter": it, "max_depth": depth},
    }

    # paired CIs at the primary budget b=0.5
    k = int(round(0.5 * n))
    f_router = np.zeros(n, bool)
    f_router[np.argsort(-te.router_score.to_numpy())[:k]] = True
    f_random = np.zeros(n, bool)
    f_random[rng.choice(n, k, replace=False)] = True
    order = sorted(range(n), key=lambda i: (te.cp_type.iloc[i] != "repeat",
                                            -te.router_score.iloc[i]))
    f_repeat = np.zeros(n, bool)
    f_repeat[order[:k]] = True
    cis = {}
    for name, fb in [("vs_random", f_random), ("vs_repeat", f_repeat),
                     ("vs_allcheap", np.zeros(n, bool)),
                     ("vs_allfull", np.ones(n, bool))]:
        d, ci = boot_delta(te, f_router, fb)
        cis[name] = {"delta": round(d, 4), "ci": [round(ci[0], 4), round(ci[1], 4)]}

    # router calibration: predicted vs realized deciles
    te["dec"] = pd.qcut(te.router_score, 10, labels=False, duplicates="drop")
    dec = te.groupby("dec", observed=True).apply(
        lambda g: pd.Series({"score": g.router_score.mean(),
                             "realized_gain": g.gain_full.mean(),
                             "full_win_rate": (g.gain_full > 0).mean(),
                             "n": len(g)}), include_groups=False)

    result = {"aug_endpoints": endpoints, "curves": rows, "paired_at_b50": cis,
              "router_deciles": dec.round(4).reset_index().to_dict("records")}
    outj = os.path.join(args.outdir, "budget_router_aug_eval.json")
    with open(outj, "w") as f:
        json.dump(result, f, indent=2)
    te.to_csv(os.path.join(args.outdir, "aug_router_scores.csv"), index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
