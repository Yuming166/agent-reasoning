"""Reproduce Group C's rough calendar-month switch rate and formalize it.

Data: Group C's own edges file (edges_asof_20220901.csv, window
[2022-06-03, 2022-09-01)) so the comparison isolates protocol differences.

Variants (same calendar months 06/07/08):
  A. groupC_exact      : overwrite-weight month graphs (Group C's
                         evaluate_importance.py semantics: add_edge(weight=w)
                         overwrites the reverse-direction row) + greedy
                         best-Jaccard matching WITHOUT minimum overlap.
                         Expected reproduction: 58.0% / 56.3%.
  B. formal_hungarian_overwrite : same overwrite graphs + Hungarian
                         max-Jaccard bijective matching (threshold 0.05).
                         Isolates the matching-protocol effect.
  C. formal_hungarian_summed : summed-weight month graphs (consistent with
                         Group C's main build_temporal_features.py and with
                         this group's as-of graphs) + Hungarian matching.
                         Isolates weight-semantics + matching effects.

Note: our per-cutoff as-of analysis (results/json/community_evolution_summary.json)
uses summed weights with 90-day as-of windows at 06-01/07-01/08-01/09-01.
"""
from __future__ import annotations

import json

import networkx as nx
import pandas as pd

import config
import community_evolution as ce


def month_graphs(edges: pd.DataFrame, months: list[str],
                 sum_weights: bool) -> dict[str, dict]:
    out = {}
    for m in months:
        em = edges[edges["month"] == m]
        G = nx.Graph()
        for r in em.itertuples(index=False):
            u, v, w = int(r.u), int(r.v), int(r.weight)
            if u == v:
                continue
            if G.has_edge(u, v):
                if sum_weights:
                    G[u][v]["weight"] += w
                else:
                    G[u][v]["weight"] = w          # Group C overwrite semantics
            else:
                G.add_edge(u, v, weight=w)
        comms = list(nx.community.greedy_modularity_communities(G, weight="weight"))
        node_comm = {}
        for ci, nodes in enumerate(comms):
            for n in nodes:
                node_comm[n] = ci
        out[m] = {"comm": node_comm, "nodes": G.number_of_nodes(),
                  "edges": G.number_of_edges()}
    return out


def frame_from(mg: dict) -> dict[str, pd.DataFrame]:
    return {m: pd.DataFrame([{"node_id": n, "community_id": ci}
                             for n, ci in s["comm"].items()])
            for m, s in mg.items()}


def main() -> None:
    edges = pd.read_csv(config.GROUP_C_EDGES, dtype={"u": "int64", "v": "int64",
                                                    "weight": "int64"})
    months = ["2022-06", "2022-07", "2022-08"]
    overwrite = month_graphs(edges, months, sum_weights=False)
    summed = month_graphs(edges, months, sum_weights=True)
    for m, s in overwrite.items():
        print(f"[month] {m} overwrite edges={s['edges']} comm={len(s['comm'])}", flush=True)

    fw = frame_from(overwrite)
    fs = frame_from(summed)
    out = {}
    for prev, cur in zip(months[:-1], months[1:]):
        a = ce.pair_metrics(fw[prev], fw[cur], "greedy_no_threshold")
        b = ce.pair_metrics(fw[prev], fw[cur], "hungarian_max_sum_jaccard")
        c = ce.pair_metrics(fs[prev], fs[cur], "hungarian_max_sum_jaccard")
        out[f"{prev}|{cur}"] = {
            "groupC_exact_overwrite_greedy_nothr": a,
            "formal_hungarian_overwrite": b,
            "formal_hungarian_summed": c,
        }
        print(f"[pair] {prev}|{cur} A={a['membership_switch_rate_common']} "
              f"B={b['membership_switch_rate_common']} "
              f"C={c['membership_switch_rate_common']}", flush=True)

    with open(config.JSON / "groupC_monthly_comparison.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("[done] groupC_monthly_comparison.json", flush=True)


if __name__ == "__main__":
    main()
