#!/usr/bin/env python3
"""Evaluate corrected LLM runs with the production failure fallback.

A failed Full or NoCF parse is operationally equivalent to not spending the
call, so its reciprocal rank is replaced by the cheap rank. This script keeps
failed rows, reports parse rates, and emits weighted paired bootstrap intervals.
It only consumes the compact per-event run CSV and does not need the private
panel shards.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ARMS = ("cheap", "nocf", "full")
KEY = ["snapshot_date", "target_address", "target_sequence_index"]


def weighted_mean(x, w):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    return float(np.sum(x * w) / np.sum(w))


def bootstrap_delta(x, w, n=10000, seed=1):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    means = (x[idx] * w[idx]).sum(axis=1) / w[idx].sum(axis=1)
    return [float(v) for v in np.quantile(means, [0.025, 0.975])]


def prepare(path):
    df = pd.read_csv(path)
    if df[KEY].duplicated().any():
        raise ValueError(f"duplicate event keys in {path}")
    if not df.truth_in_pool.astype(bool).all():
        df = df[df.truth_in_pool.astype(bool)].copy()
    for col in ("cheap_rr", "nocf_rr", "full_rr", "pop_weight"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["nocf_op_rr"] = df["nocf_rr"].where(df.nocf_parse_ok.astype(bool), df.cheap_rr)
    df["full_op_rr"] = df["full_rr"].where(df.full_parse_ok.astype(bool), df.cheap_rr)
    df["nocf_op_rr"] = df["nocf_op_rr"].fillna(df.cheap_rr)
    df["full_op_rr"] = df["full_op_rr"].fillna(df.cheap_rr)
    return df


def summarize(df, name):
    w = df.pop_weight.to_numpy(float)
    result = {
        "name": name,
        "n_events": int(len(df)),
        "full_parse": float(df.full_parse_ok.mean()),
        "nocf_parse": float(df.nocf_parse_ok.mean()),
        "full_failures": int((~df.full_parse_ok.astype(bool)).sum()),
        "nocf_failures": int((~df.nocf_parse_ok.astype(bool)).sum()),
        "mrr_cheap": weighted_mean(df.cheap_rr, w),
        "mrr_nocf_operational": weighted_mean(df.nocf_op_rr, w),
        "mrr_full_operational": weighted_mean(df.full_op_rr, w),
        "median_full_tokens": int(pd.to_numeric(df.total_tokens, errors="coerce").median()),
        "median_nocf_tokens": int(pd.to_numeric(df.nocf_total_tokens, errors="coerce").median()),
        "median_latency_s": float(pd.to_numeric(df.latency_s, errors="coerce").median()),
    }
    for label, left, right in (
        ("full_minus_cheap", "full_op_rr", "cheap_rr"),
        ("nocf_minus_cheap", "nocf_op_rr", "cheap_rr"),
        ("full_minus_nocf", "full_op_rr", "nocf_op_rr"),
    ):
        delta = (df[left] - df[right]).to_numpy(float)
        result[label] = weighted_mean(delta, w)
        result[label + "_ci95"] = bootstrap_delta(delta, w)
        result[label + "_winrate"] = float((delta > 0).mean())
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="month=run.csv or run.csv paths")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    all_results = []
    for spec in args.runs:
        if "=" in spec:
            month, path = spec.split("=", 1)
        else:
            path = spec
            month = Path(path).stem
        df = prepare(path)
        result = summarize(df, month)
        result["source"] = path
        result["by_stratum"] = {
            str(st): summarize(g, str(st))
            for st, g in df.groupby("stratum", sort=True)
        }
        all_results.append(result)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(x, sort_keys=True) for x in all_results) + "\n")
    print("wrote", out, len(all_results))


if __name__ == "__main__":
    main()
