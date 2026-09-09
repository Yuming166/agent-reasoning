#!/usr/bin/env python3
"""Replace arm RR/rank fields with tie-aware average-competition ranks."""
import argparse
import os
import sys
import pandas as pd

KEY = ["snapshot_date", "target_address", "target_sequence_index"]
ARMS = ["cheap", "obs", "mask", "nocf", "full"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def addr_map_for_event(g):
    order = g.sort_values(["cheap_score", "candidate_address"],
                          ascending=[False, True]).reset_index(drop=True)
    ranks = order.cheap_score.rank(method="average", ascending=False)
    m = dict(zip(order.candidate_address, zip(ranks, order.index)))
    return order, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    scored = pd.read_csv(args.scored)
    runs = pd.read_csv(args.runs)
    # Address choices need to be reconstructed: cheap=truth; LLM arms map via
    # their existing order ranks is not stable under ties, so map rank back is
    # unsafe. For LLM arms run_agent already emits ranks but not addresses; we
    # derive selected address from the OLD deterministic cheap order index.
    # Then score that address under average ranks.
    out = runs.copy()
    for arm in ARMS:
        out[arm + "_rank"] = out[arm + "_rank"].astype(float)
    grouped = {tuple(k): g for k, g in scored.groupby(KEY, sort=False)}
    maps, old_orders, truths = {}, {}, {}
    for k, g in grouped.items():
        order, m = addr_map_for_event(g)
        maps[k], old_orders[k] = m, order
        truths[k] = g.loc[g.label == 1, "candidate_address"].iloc[0]
    selected_cols = {}
    for i, row in out.iterrows():
        k = tuple(row[c] for c in KEY)
        omap = maps[k]
        old_order = old_orders[k]
        truth = truths[k]
        selected = {"cheap": truth}
        # Existing *_rank was deterministic position+1 from run_agent; recover
        # that exact selected address from the old score-sorted order before
        # replacing metrics.
        for arm in ["obs", "mask", "nocf", "full"]:
            r = row.get(arm + "_rank")
            if pd.notna(r) and 1 <= int(r) <= len(old_order):
                selected[arm] = old_order.candidate_address.iloc[int(r)-1]
            else:
                selected[arm] = None
        selected_cols[i] = selected
        n = len(old_order) + 1
        for arm in ARMS:
            addr = selected.get(arm)
            if addr in omap:
                avg_rank, _ = omap[addr]
                out.at[i, arm + "_rank"] = float(avg_rank)
                out.at[i, arm + "_rr"] = 1.0 / float(avg_rank)
            else:
                out.at[i, arm + "_rank"] = float(n)
                out.at[i, arm + "_rr"] = 0.0
    out.to_csv(args.out, index=False)
    print("wrote", args.out, len(out))


if __name__ == "__main__":
    main()
