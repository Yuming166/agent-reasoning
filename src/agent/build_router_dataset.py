#!/usr/bin/env python3
"""Assemble pre-deliberation router features and join measured LLM gains.

Hard rule: every router feature must be available BEFORE any LLM call. No
truth_g_rank, no realized rank, no mask_sensitive (that is emitted inside the
FSM and cannot be used by an external pre-call router).

Targets (from run CSVs): gain_full = full_rr - cheap_rr; gain_nocf likewise.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.data import EVENT_KEY, PANEL_DIR  # noqa: E402


def event_features(scored: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, g in scored.groupby(EVENT_KEY, sort=False):
        g = g.sort_values("cheap_score", ascending=False).reset_index(drop=True)
        s = g.cheap_score.to_numpy()
        p = np.clip(s, 1e-9, 1 - 1e-9)
        ent = float(-(p * np.log(p) + (1 - p) * np.log(1 - p)).mean())
        top1, top2 = float(s[0]), float(s[1]) if len(s) > 1 else 0.0
        src = g.cand_source
        n = len(g)
        rows.append({
            "snapshot_date": key[0], "target_address": key[1],
            "target_sequence_index": key[2],
            "cp_type_repeat": int(g.cp_type.iloc[0] == "repeat"),
            "evt_cnt_90d": float(g.evt_cnt_90d.iloc[0]),
            "cp_entropy_90d": float(g.cp_entropy_90d.iloc[0]),
            "cp_new_rate_30d": float(g.cp_new_rate_30d.iloc[0]),
            "pool_n": n,
            "cheap_top_score": top1,
            "cheap_margin": top1 - top2,
            "cheap_score_entropy": ent,
            "frac_bridge": float((src == "new_bridge").mean()),
            "frac_personal": float((src == "repeat_personal").mean()),
            "frac_tail": float(src.isin(["new_tail", "repeat_tail"]).mean()),
            "frac_top2000": float(src.isin(["new_top2000", "repeat_top2000"]).mean()),
            "n_bridge": int((src == "new_bridge").sum()),
            "n_personal": int((src == "repeat_personal").sum()),
            "top1_is_personal": int(g.cand_source.iloc[0] == "repeat_personal"),
            "top1_is_bridge": int(g.cand_source.iloc[0] == "new_bridge"),
            "pop_weight": float(g.pop_weight.iloc[0]),
        })
    return pd.DataFrame(rows)


FEATURES = [
    "cp_type_repeat", "log_evt_cnt", "cp_entropy_90d", "cp_new_rate_30d",
    "log_pool_n", "cheap_top_score", "cheap_margin", "cheap_score_entropy",
    "frac_bridge", "frac_personal", "frac_tail", "frac_top2000",
    "log_n_bridge", "log_n_personal", "top1_is_personal", "top1_is_bridge",
]


def augment(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_evt_cnt"] = np.log1p(df.evt_cnt_90d)
    df["log_pool_n"] = np.log(df.pool_n)
    df["log_n_bridge"] = np.log1p(df.n_bridge)
    df["log_n_personal"] = np.log1p(df.n_personal)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True,
                    help="run CSVs: month=path pairs, e.g. 2022-06-01=runs/jun.csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    scored = pd.read_csv(os.path.join(PANEL_DIR, "panel_scored.csv.gz"))
    feats = augment(event_features(scored))

    parts = []
    for spec in args.runs:
        month, path = spec.split("=", 1)
        run = pd.read_csv(path)
        run = run[run.snapshot_date == month]
        run = run.copy()
        run["gain_full"] = run.full_rr - run.cheap_rr
        run["gain_nocf"] = run.nocf_rr - run.cheap_rr
        run["full_wins"] = (run.gain_full > 0).astype(int)
        keep = EVENT_KEY + ["gain_full", "gain_nocf", "full_wins",
                            "full_rr", "cheap_rr", "nocf_rr", "total_tokens",
                            "mask_sensitive", "stratum", "cp_type",
                            "truth_in_pool"]
        parts.append(run[keep])
    gains = pd.concat(parts, ignore_index=True)
    ds = feats.merge(gains, on=EVENT_KEY, how="inner")
    ds.to_csv(args.out, index=False)
    print("wrote", args.out, ds.shape)
    print(ds.groupby("snapshot_date").gain_full.agg(["count", "mean"]))


if __name__ == "__main__":
    main()
