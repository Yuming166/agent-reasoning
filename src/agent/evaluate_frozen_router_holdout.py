#!/usr/bin/env python3
"""Evaluate the June-frozen budget router on a later temporal holdout month."""
import argparse
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from agent.build_router_dataset import FEATURES, augment, event_features  # noqa: E402

BUDGETS = [0.05, 0.10, 0.20, 0.50, 0.75]


def wmean(x, w):
    x = np.asarray(x, float); w = np.asarray(w, float)
    m = np.isfinite(x)
    return float((x[m] * w[m]).sum() / w[m].sum())


def policy_mrr(df, flag):
    return wmean(np.where(flag, df.full_rr, df.cheap_rr), df.pop_weight)


def boot_delta(df, a, b, n=3000, seed=11):
    ya = np.where(a, df.full_rr, df.cheap_rr)
    yb = np.where(b, df.full_rr, df.cheap_rr)
    d = ya - yb
    w = df.pop_weight.to_numpy()
    m = np.isfinite(d); d, w = d[m], w[m]
    rng = np.random.default_rng(seed)
    bs = np.array([(lambda idx: (d[idx] * w[idx]).sum() / w[idx].sum())(rng.integers(0, len(d), len(d))) for _ in range(n)])
    point = wmean(d, w)
    return point, [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--router", default="artifacts/llm_panel_v1/router_v1/budget_router_jun_frozen.pkl")
    ap.add_argument("--snapshot", default="2022-09-01")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-scores", required=True)
    args = ap.parse_args()

    scored = pd.read_csv(args.scored)
    feats = augment(event_features(scored))
    run = pd.read_csv(args.runs)
    run = run[run.snapshot_date == args.snapshot].copy()
    run["gain_full"] = run.full_rr - run.cheap_rr
    run["gain_nocf"] = run.nocf_rr - run.cheap_rr
    keys = ["snapshot_date", "target_address", "target_sequence_index"]
    keep = keys + ["gain_full", "gain_nocf", "full_rr", "cheap_rr", "nocf_rr",
                   "total_tokens", "mask_sensitive", "stratum", "cp_type", "pop_weight"]
    ds = feats.merge(run[keep], on=keys, how="inner", suffixes=("", "_run"))
    if "pop_weight_run" in ds:
        ds = ds.drop(columns=["pop_weight_run"])
    if len(ds) != len(run):
        raise RuntimeError(f"joined {len(ds)} rows to {len(run)} runs")

    with open(args.router, "rb") as f:
        bundle = pickle.load(f)
    if bundle.get("features") != FEATURES:
        raise ValueError("frozen router feature mismatch")
    ds["router_score"] = bundle["model"].predict(ds[FEATURES].to_numpy())
    rng = np.random.default_rng(29)
    n = len(ds)
    curves = []
    primary_flags = {}
    for b in BUDGETS:
        k = max(1, int(round(b * n)))
        flags = {}
        idx_router = np.argsort(-ds.router_score.to_numpy())[:k]
        flags["router"] = np.zeros(n, bool); flags["router"][idx_router] = True
        # uncertainty baselines on the same pre-call cheap score distribution
        order_top = np.argsort(ds.cheap_top_score.to_numpy())[:k]
        flags["uncertainty_topscore"] = np.zeros(n, bool); flags["uncertainty_topscore"][order_top] = True
        order_ent = np.argsort(-ds.cheap_score_entropy.to_numpy())[:k]
        flags["uncertainty_entropy"] = np.zeros(n, bool); flags["uncertainty_entropy"][order_ent] = True
        order_rep = sorted(range(n), key=lambda i: (ds.cp_type_repeat.iloc[i] != 1, -ds.router_score.iloc[i]))
        flags["repeat"] = np.zeros(n, bool); flags["repeat"][order_rep[:k]] = True
        rand = []
        rand_flags = []
        for _ in range(100):
            f = np.zeros(n, bool); ii = rng.choice(n, k, replace=False); f[ii] = True
            rand.append(policy_mrr(ds, f)); rand_flags.append(f)
        flags["oracle"] = np.zeros(n, bool)
        flags["oracle"][np.argsort(-ds.gain_full.fillna(-9).to_numpy())[:k]] = True
        primary_flags["random_seed0"] = rand_flags[0]
        row = {"budget": b, "k": k, "mrr_random": round(float(np.mean(rand)), 4)}
        for name, f in flags.items():
            row["mrr_" + name] = round(policy_mrr(ds, f), 4)
        curves.append(row)

    # Deterministic fixed random policies for paired CIs.
    k50 = int(round(0.5 * n))
    f_router = np.zeros(n, bool); f_router[np.argsort(-ds.router_score.to_numpy())[:k50]] = True
    rng_ci = np.random.default_rng(709)
    f_random = np.zeros(n, bool); f_random[rng_ci.choice(n, k50, replace=False)] = True
    f_top = np.zeros(n, bool); f_top[np.argsort(ds.cheap_top_score.to_numpy())[:k50]] = True
    f_ent = np.zeros(n, bool); f_ent[np.argsort(-ds.cheap_score_entropy.to_numpy())[:k50]] = True
    order_rep = sorted(range(n), key=lambda i: (ds.cp_type_repeat.iloc[i] != 1, -ds.router_score.iloc[i]))
    f_rep = np.zeros(n, bool); f_rep[order_rep[:k50]] = True
    cis = {}
    for name, f in [("vs_random", f_random), ("vs_uncertainty_topscore", f_top),
                    ("vs_uncertainty_entropy", f_ent), ("vs_repeat", f_rep),
                    ("vs_allcheap", np.zeros(n, bool)), ("vs_allfull", np.ones(n, bool))]:
        delta, ci = boot_delta(ds, f_router, f)
        cis[name] = {"delta": round(delta, 4), "ci": [round(ci[0], 4), round(ci[1], 4)]}

    ds["score_decile"] = pd.qcut(ds.router_score, 10, labels=False, duplicates="drop")
    dec = ds.groupby("score_decile", observed=True).apply(
        lambda g: pd.Series({
            "router_score": g.router_score.mean(),
            "realized_gain": g.gain_full.mean(),
            "full_win_rate": (g.gain_full > 0).mean(),
            "n": len(g)}), include_groups=False).reset_index()

    result = {
        "snapshot": args.snapshot,
        "frozen_router": args.router,
        "n_events": n,
        "endpoints": {
            "mrr_cheap": round(wmean(ds.cheap_rr, ds.pop_weight), 4),
            "mrr_full": round(wmean(ds.full_rr, ds.pop_weight), 4),
            "mrr_nocf": round(wmean(ds.nocf_rr, ds.pop_weight), 4),
            "mrr_oracle_max": round(wmean(np.maximum(ds.cheap_rr, ds.full_rr), ds.pop_weight), 4),
            "median_full_tokens": int(ds.total_tokens.median()),
        },
        "curves": curves,
        "paired_at_b50": cis,
        "router_deciles": dec.round(4).to_dict("records"),
    }
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w") as f:
        json.dump(result, f, indent=2)
    ds.to_csv(args.out_scores, index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
