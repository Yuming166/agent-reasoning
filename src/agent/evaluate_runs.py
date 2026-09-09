#!/usr/bin/env python3
"""Paired evaluation of cheap vs deliberation arms with bootstrap CIs."""
import argparse
import json

import numpy as np
import pandas as pd

ARMS = ["cheap", "obs", "mask", "nocf", "full"]


def wmean(x, w):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    m = ~np.isnan(x)
    return float(np.sum(x[m] * w[m]) / np.sum(w[m])) if m.any() else np.nan


def boot_ci(x, w=None, n=2000, seed=1):
    x = np.asarray(x, float)
    m = ~np.isnan(x)
    x = x[m]
    w = np.ones_like(x) if w is None else np.asarray(w, float)[m]
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    N = len(x)
    for i in range(n):
        idx = rng.integers(0, N, N)
        means[i] = (x[idx] * w[idx]).sum() / w[idx].sum()
    point = float((x * w).sum() / w.sum())
    return point, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--by-stratum", action="store_true")
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    for a in ARMS:
        df[a + "_rr"] = 1.0 / df[a + "_rank"]
    df.loc[~df.truth_in_pool.astype(bool), [a + "_rr" for a in ARMS]] = np.nan

    def summarize(sub, name):
        w = sub.pop_weight.to_numpy()
        res = {"n": int(len(sub))}
        for a in ARMS:
            vals = sub[a + "_rr"].to_numpy()
            m = ~np.isnan(vals)
            res[a + "_MRR"] = round(wmean(vals, w), 4)
            hit = (sub[a + "_rank"].to_numpy() == 1).astype(float)
            res[a + "_R1"] = round(wmean(hit, w), 4)
        # paired deltas against cheap (weighted) + bootstrap
        for a in ["obs", "mask", "nocf", "full"]:
            d = (sub[a + "_rr"] - sub.cheap_rr).to_numpy()
            mm = ~np.isnan(d)
            if mm.sum() >= 2:
                mean, lo, hi = boot_ci(d[mm], w[mm])
                res[f"d_{a}_cheap"] = round(mean, 4)
                res[f"d_{a}_ci"] = [round(lo, 4), round(hi, 4)]
                res[f"d_{a}_winrate"] = round(float((d[mm] > 0).mean()), 3)
        d = (sub.full_rr - sub.nocf_rr).to_numpy()
        mm = ~np.isnan(d)
        if mm.sum() >= 2:
            mean, lo, hi = boot_ci(d[mm], w[mm])
            res["d_full_nocf"] = round(mean, 4)
            res["d_full_nocf_ci"] = [round(lo, 4), round(hi, 4)]
        res["full_parse"] = round(float(sub.full_parse_ok.mean()), 3)
        res["nocf_parse"] = round(float(sub.nocf_parse_ok.mean()), 3)
        res["tokens_full_med"] = int(sub.total_tokens.median())
        res["tokens_nocf_med"] = int(sub.nocf_total_tokens.median())
        res["latency_med_s"] = float(sub.latency_s.median())
        res["mask_sensitive_rate"] = round(float(pd.to_numeric(sub.mask_sensitive, errors="coerce").mean()), 3)
        print(name, json.dumps(res, ensure_ascii=False))

    summarize(df, "ALL")
    if args.by_stratum:
        for st, sub in df.groupby("stratum"):
            summarize(sub, st)
        for cp, sub in df.groupby("cp_type"):
            summarize(sub, cp)


if __name__ == "__main__":
    main()
