#!/usr/bin/env python3
"""Budget allocation curves using measured per-event gains.

Policies at deliberation fraction b (full 3-operator FSM vs cheap):
- oracle   : choose full when full_rr >= cheap_rr (labeled cheating upper bound)
- msens    : route to full when the FSM reports mask_sensitive=true
- random   : expected RR at budget b (fixed seed, averaged)
- all-full / all-cheap endpoints
Reports pooled MRR and repeat/new MRR, plus token cost (measured medians).
"""
import argparse
import json

import numpy as np
import pandas as pd


def rr(df, arm):
    return (1.0 / df[arm + "_rank"]).where(df.truth_in_pool.astype(bool))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    for a in ["cheap", "obs", "mask", "nocf", "full"]:
        df[a + "_rr"] = rr(df, a)
    df["gain"] = df.full_rr - df.cheap_rr
    df["msens"] = pd.to_numeric(df.mask_sensitive, errors="coerce").fillna(0).astype(int)
    w = df.pop_weight.to_numpy()

    def wm(x):
        x = np.asarray(x, float)
        m = ~np.isnan(x)
        return float((x[m] * w[m]).sum() / w[m].sum())

    res = {}
    res["all_cheap_mrr"] = round(wm(df.cheap_rr), 4)
    res["all_full_mrr"] = round(wm(df.full_rr), 4)
    res["all_nocf_mrr"] = round(wm(df.nocf_rr), 4)
    res["oracle_full_mrr"] = round(wm(np.maximum(df.cheap_rr, df.full_rr)), 4)
    res["median_tokens_full"] = int(df.total_tokens.median())
    res["median_tokens_nocf"] = int(df.nocf_total_tokens.median())

    rng = np.random.default_rng(7)
    rows = []
    for b in [0.01, 0.05, 0.10, 0.20, 0.40, 0.75, 1.0]:
        k = int(round(b * len(df)))
        # msens policy: route mask-sensitive events first, then by latent ordering
        order_ms = df.sort_values(["msens"], ascending=False).index[:k]
        sel = pd.Series(False, index=df.index); sel.loc[order_ms] = True
        rr_ms = np.where(sel, df.full_rr, df.cheap_rr)
        # oracle: largest realized gains first
        gain_order = np.argsort(-df.gain.fillna(-9).to_numpy())[:k]
        sel_o = pd.Series(False, index=df.index); sel_o.iloc[gain_order] = True
        rr_o = np.where(sel_o, df.full_rr, df.cheap_rr)
        # random (100 averages)
        rand_means = []
        for _ in range(100):
            idx = rng.choice(len(df), k, replace=False)
            selr = pd.Series(False, index=df.index); selr.iloc[idx] = True
            rand_means.append(wm(np.where(selr, df.full_rr, df.cheap_rr)))
        # stratum-conditional msens MRR (repeat/new)
        def wm_sub(x, sub):
            x = np.asarray(x, float)
            ww = df.pop_weight.to_numpy()[sub]
            m = ~np.isnan(x[sub])
            return float((x[sub][m] * ww[m]).sum() / ww[m].sum()) if m.any() else None
        rep = (df.cp_type == "repeat").to_numpy()
        new = ~rep
        rows.append({
            "budget_b": b, "n_full": k,
            "mrr_msens": round(wm(rr_ms), 4),
            "mrr_oracle": round(wm(rr_o), 4),
            "mrr_random": round(float(np.mean(rand_means)), 4),
            "mrr_msens_repeat": round(wm_sub(rr_ms, rep), 4),
            "mrr_msens_new": round(wm_sub(rr_ms, new), 4),
        })
    res["curves"] = rows
    # msens diagnostic: precision of mask_sensitive flag for realized gain
    ms = df.msens.astype(bool)
    res["msens_rate"] = round(float(ms.mean()), 3)
    res["mean_gain_when_msens"] = round(float(df.loc[ms, "gain"].mean()), 4)
    res["mean_gain_when_not"] = round(float(df.loc[~ms, "gain"].mean()), 4)
    res["msens_precision_posgain"] = round(float((df.loc[ms, "gain"] > 0).mean()), 3)
    res["msens_coverage_posgain"] = round(float(ms[df.gain > 0].mean()), 3)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
