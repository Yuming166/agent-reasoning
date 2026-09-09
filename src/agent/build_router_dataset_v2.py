#!/usr/bin/env python3
"""Build v2 pre-call router data with explicit parse-failure fallback.

The router target is the operational policy gain: a failed LLM call falls back
to the cheap ranker, so invalid outputs receive gain=0 rather than being
silently dropped from training/evaluation.
"""
import argparse
import os
import sys
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from agent.build_router_dataset import EVENT_KEY, FEATURES, augment, event_features  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", default="artifacts/llm_panel_v2/panel_scored_v2.csv.gz")
    ap.add_argument("--runs", nargs="+", required=True,
                    help="month=run.csv pairs for 2022-06/07/08")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    scored = pd.read_csv(args.scored)
    feats = augment(event_features(scored))
    parts = []
    for spec in args.runs:
        month, path = spec.split("=", 1)
        run = pd.read_csv(path)
        run = run[run.snapshot_date == month].copy()
        if run.empty:
            raise RuntimeError(f"no rows for {month} in {path}")
        run["full_rr_raw"] = run["full_rr"]
        run["nocf_rr_raw"] = run["nocf_rr"]
        # Operational fallback: an invalid full/nocf output is equivalent to
        # not spending the call, hence use the cheap arm's RR.
        run["full_failed"] = (pd.to_numeric(run.full_parse_ok, errors="coerce").fillna(0) < 1).astype(int)
        run["nocf_failed"] = (pd.to_numeric(run.nocf_parse_ok, errors="coerce").fillna(0) < 1).astype(int)
        run["full_rr"] = run["full_rr"].where(run["full_failed"] == 0, run["cheap_rr"])
        run["nocf_rr"] = run["nocf_rr"].where(run["nocf_failed"] == 0, run["cheap_rr"])
        run["full_rr"] = run["full_rr"].fillna(run["cheap_rr"])
        run["nocf_rr"] = run["nocf_rr"].fillna(run["cheap_rr"])
        run["mask_sensitive"] = pd.to_numeric(run["mask_sensitive"], errors="coerce").fillna(0)
        run["gain_full"] = run.full_rr - run.cheap_rr
        run["gain_nocf"] = run.nocf_rr - run.cheap_rr
        run["full_wins"] = (run.gain_full > 0).astype(int)
        keep = EVENT_KEY + ["gain_full", "gain_nocf", "full_wins",
                            "full_rr", "cheap_rr", "nocf_rr", "total_tokens",
                            "mask_sensitive", "full_failed", "nocf_failed",
                            "full_rr_raw", "nocf_rr_raw", "stratum", "cp_type",
                            "truth_in_pool"]
        parts.append(run[keep])
    gains = pd.concat(parts, ignore_index=True)
    ds = feats.merge(gains, on=EVENT_KEY, how="inner")
    if len(ds) != len(gains):
        raise RuntimeError(f"feature join lost rows: {len(ds)} vs {len(gains)}")
    ds.to_csv(args.out, index=False)
    print("wrote", args.out, ds.shape)
    print(ds.groupby("snapshot_date").agg(
        n=("gain_full", "size"), mean_gain=("gain_full", "mean"),
        full_failed=("full_failed", "sum"), nocf_failed=("nocf_failed", "sum")))


if __name__ == "__main__":
    main()
