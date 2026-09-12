"""COMM group - build per-cutoff as-of graphs, detect fixed communities, roles.

CPU-only (networkx 3.6, scipy). Reads day-level bounded pull
results/data/edges_day_20220303_20220901.csv and reconstructs exactly:
  * per-cutoff as-of graphs  [t-90d, t)  for t in 06-01, 07-01, 08-01, 09-01
  * calendar-month slices    Jun/Jul/Aug  (Group C comparison)
Community algorithm fixed: networkx greedy_modularity_communities on the
weighted undirected graph (role edges summed), nodes added in sorted order.
Roles follow Group C definitions exactly.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

import config

CUTOFF_ORDER = ["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]


def load_edges() -> pd.DataFrame:
    p = config.DATA / "edges_day_20220303_20220901.csv"
    df = pd.read_csv(p, dtype={"u": "int64", "v": "int64", "weight": "int64"})
    return df


def build_undirected(rows: pd.DataFrame) -> nx.Graph:
    """Undirected weighted graph from directed role rows (Group C semantics)."""
    G = nx.Graph()
    for r in rows.itertuples(index=False):
        u, v, w = int(r.u), int(r.v), int(r.weight)
        if u == v:
            continue
        if G.has_edge(u, v):
            G[u][v]["weight"] += w
        else:
            G.add_edge(u, v, weight=w)
    return G


def snapshot_graphs(df: pd.DataFrame) -> dict[str, dict]:
    """Return {snapshot_name: {'nodes': int, 'edges': int, 'event_weight': int,
    'G': Graph, 'comm': node->comm_id, 'comm_size': comm_id->size}}."""
    out: dict[str, dict] = {}
    day = pd.to_datetime(df["day"])
    for cutoff, start in config.CUTOFFS.items():
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(cutoff)
        sel = df[(day >= start_ts) & (day < end_ts)]
        G = build_undirected(sel)
        comms = list(nx.community.greedy_modularity_communities(G, weight="weight"))
        node_comm: dict[int, int] = {}
        comm_size: dict[int, int] = {}
        for ci, nodes in enumerate(comms):
            comm_size[ci] = len(nodes)
            for n in nodes:
                node_comm[n] = ci
        out[cutoff] = {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "event_weight": int(sel["weight"].sum()),
            "G": G, "comm": node_comm, "comm_size": comm_size,
        }
        print(f"[{cutoff}] nodes={G.number_of_nodes()} edges={G.number_of_edges()} "
              f"communities={len(comms)}", flush=True)
    # calendar-month slices (Group C comparison)
    for m in config.MONTHS:
        sel = df[df["month"] == m]
        G = build_undirected(sel)
        comms = list(nx.community.greedy_modularity_communities(G, weight="weight"))
        node_comm = {}
        comm_size = {}
        for ci, nodes in enumerate(comms):
            comm_size[ci] = len(nodes)
            for n in nodes:
                node_comm[n] = ci
        out[m] = {
            "nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
            "event_weight": int(sel["weight"].sum()),
            "G": G, "comm": node_comm, "comm_size": comm_size,
        }
        print(f"[{m}] nodes={G.number_of_nodes()} edges={G.number_of_edges()} "
              f"communities={len(comms)}", flush=True)
    return out


def role_features(G: nx.Graph, comm: dict[int, int], comm_size: dict[int, int],
                  betweenness: dict[int, float]) -> pd.DataFrame:
    """Group C role definitions per node (within/cross comm wdeg, bridge/hub)."""
    rows = []
    for n in sorted(G.nodes()):
        ci = comm[n]
        within_w, cross_w, within_n, cross_n = 0.0, 0.0, 0, 0
        for nb, d in G[n].items():
            w = float(d.get("weight", 1.0))
            if comm[nb] == ci:
                within_w += w
                within_n += 1
            else:
                cross_w += w
                cross_n += 1
        tot = within_w + cross_w
        cross_share = cross_w / tot if tot > 0 else 0.0
        rows.append({
            "node_id": n,
            "community_id": ci,
            "community_size": comm_size[ci],
            "within_comm_wdeg": within_w,
            "cross_comm_wdeg": cross_w,
            "cross_comm_share": cross_share,
            "within_comm_deg": within_n,
            "cross_comm_deg": cross_n,
            "bridge_score": betweenness.get(n, 0.0) * (1.0 + cross_n),
            "hub_score": within_w / max(1, comm_size[ci] - 1),
            "is_boundary": bool(cross_share >= 0.5),
            "betweenness": betweenness.get(n, 0.0),
        })
    return pd.DataFrame(rows)


def main() -> None:
    config.DATA.mkdir(parents=True, exist_ok=True)
    config.JSON.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    df = load_edges()
    snaps = snapshot_graphs(df)

    # per-cutoff edge lists (compact, for audit/reproducibility)
    day = pd.to_datetime(df["day"])
    for cutoff, start in config.CUTOFFS.items():
        sel = df[(day >= pd.Timestamp(start)) & (day < pd.Timestamp(cutoff))]
        agg = (sel.groupby(["u", "v", "direction"], as_index=False)["weight"].sum()
                  .sort_values(["u", "v", "direction"]))
        agg.to_csv(config.DATA / f"edges_asof_{cutoff.replace('-', '')}.csv", index=False)
        print(f"[edges] {cutoff}: {len(agg)} rows", flush=True)

    stats = {}
    for name, s in snaps.items():
        G = s["G"]
        n, m = G.number_of_nodes(), G.number_of_edges()
        if name == "2022-09-01":
            btw_method = "full"
            btw = nx.betweenness_centrality(G, weight="weight", normalized=True)
        elif name in config.CUTOFFS:
            btw_method = "sampled_k1000_seed42"
            btw = nx.betweenness_centrality(G, k=1000, seed=42, weight="weight",
                                            normalized=True)
        else:
            btw_method = "not_computed"
            btw = {}
        print(f"[btw] {name} method={btw_method} nodes={n} edges={m} ...", flush=True)
        roles = role_features(G, s["comm"], s["comm_size"], btw)
        roles.to_csv(config.DATA / f"community_membership_{name.replace('-', '')}.csv", index=False)
        s["roles"] = roles
        n_boundary = int(roles["is_boundary"].sum())
        sizes = pd.Series(s["comm_size"]).sort_values(ascending=False)
        stats[name] = {
            "nodes": s["nodes"], "edges": s["edges"],
            "event_weight": s["event_weight"],
            "n_communities": len(s["comm_size"]),
            "betweenness_method": btw_method,
            "modularity": round(float(nx.community.modularity(
                G, list(_comm_sets(s["comm"]).values()), weight="weight")), 5),
            "n_boundary_wallets": n_boundary,
            "boundary_share": round(n_boundary / s["nodes"], 4),
            "top10_community_sizes": [int(x) for x in sizes.head(10).tolist()],
            "singleton_communities": int((pd.Series(s["comm_size"]) == 1).sum()),
            "mean_community_size": round(float(np.mean(list(s["comm_size"].values()))), 2),
        }
        print(f"    modularity={stats[name]['modularity']} "
              f"boundary={n_boundary} ({stats[name]['boundary_share']})", flush=True)

    # save graph stats
    with open(config.JSON / "community_graph_stats.json", "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # save full community membership (long format, all snapshots)
    parts = []
    for name, s in snaps.items():
        r = s["roles"].copy()
        r["snapshot"] = name
        parts.append(r)
    allm = pd.concat(parts, ignore_index=True)
    allm.to_csv(config.DATA / "monthly_communities.csv", index=False)
    print(f"[save] monthly_communities.csv {len(allm)} rows; total {time.time()-t0:.1f}s", flush=True)


def _comm_sets(comm: dict[int, int]) -> dict[int, set]:
    out: dict[int, set] = {}
    for n, ci in comm.items():
        out.setdefault(ci, set()).add(n)
    return out


if __name__ == "__main__":
    main()
