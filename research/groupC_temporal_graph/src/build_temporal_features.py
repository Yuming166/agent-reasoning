"""Group C — build as-of temporal-graph structural features (cutoff 2022-09-01).

CPU-only (networkx 3.6, no GPU, no LLM). One bounded BigQuery pull returns
matched-matched primary directed edges aggregated by (u,v,direction,month)
inside the 90-day lookback [2022-06-03, 2022-09-01) UTC. From that single
bounded pull we construct:

  * rolling-window aggregate graph  (full 90d, event-count edge weights)
  * monthly temporal snapshots      (Jun / Jul / Aug 2022 subgraphs)
  * static leaky prior              (artifacts/exgraph_structural_features.csv,
                                     read-only, used only as an external prior)

and compute, per node in the as-of matched-matched subgraph:
  degree / weighted degree / PageRank / k-core / clustering / betweenness /
  recency-weighted degree / activity trend / persistence / repeated-edge &
  mutual-edge & triangle motif proxies / community (Louvain) hub & bridge scores.

Outputs (results/data/):
  edges_asof_20220901.csv           pulled edge list
  structural_features_20220901.csv  per-node structural + temporal + community
                                    features (ALL nodes in the as-of subgraph)
  monthly_graph_stats.json          nodes/edges/coverage per month + full
  community_summary.json            community sizes + top hub/bridge nodes
  build_manifest.json               windows, billed bytes, method notes
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import bq_client  # noqa: E402
import config  # noqa: E402


def pull_edges() -> pd.DataFrame:
    sql = (config.SRC.parent / "sql" / "edges_asof.sql").read_text()
    print("[pull] edges_asof ...", flush=True)
    t0 = time.time()
    rows = bq_client.run_bounded_query(sql, config.MAX_BYTES_BILLED)
    print(f"[pull] done in {time.time()-t0:.1f}s, {len(rows)} rows", flush=True)
    edges = pd.DataFrame(rows)
    edges["u"] = edges["u"].astype("int64")
    edges["v"] = edges["v"].astype("int64")
    edges["weight"] = edges["weight"].astype("int64")
    return edges


def monthly_decay_weights() -> dict[str, float]:
    """Exponential recency decay per month, anchored at the cutoff.

    age = days from end of month to cutoff (2022-09-01); weight = exp(-age/30).
    """
    month_ends = {"2022-06": "2022-06-30", "2022-07": "2022-07-31",
                  "2022-08": "2022-08-31"}
    cutoff = pd.Timestamp("2022-09-01")
    out = {}
    for m, end in month_ends.items():
        age_days = (cutoff - pd.Timestamp(end)).days
        out[m] = float(math.exp(-age_days / config.RECENCY_TAU_DAYS))
    return out


def build_graphs(edges: pd.DataFrame):
    """Return (G_di, G_und, monthly dict of DiGraph, per-month edge weights)."""
    G = nx.DiGraph()
    und = nx.Graph()
    monthly: dict[str, nx.DiGraph] = {m: nx.DiGraph() for m in config.MONTHS}
    monthly_w: dict[str, dict[tuple, int]] = {m: {} for m in config.MONTHS}
    for r in edges.itertuples(index=False):
        u, v, w, m = int(r.u), int(r.v), int(r.weight), r.month
        if u == v:
            continue
        if G.has_edge(u, v):
            G[u][v]["weight"] += w
        else:
            G.add_edge(u, v, weight=w)
        if und.has_edge(u, v):
            und[u][v]["weight"] += w
        else:
            und.add_edge(u, v, weight=w)
        if m in monthly:
            monthly_w[m][(u, v)] = monthly_w[m].get((u, v), 0) + w
    for m, wdict in monthly_w.items():
        for (u, v), w in wdict.items():
            monthly[m].add_edge(u, v, weight=w)
    return G, und, monthly, monthly_w


def community_features(G: nx.DiGraph, und: nx.Graph, betweenness: dict):
    """Louvain (greedy modularity) communities on the weighted undirected graph."""
    comms = list(nx.community.greedy_modularity_communities(und, weight="weight"))
    node_comm: dict[int, int] = {}
    for ci, nodes in enumerate(comms):
        for n in nodes:
            node_comm[n] = ci
    comm_size = {ci: len(nodes) for ci, nodes in enumerate(comms)}
    feat = {}
    for n in und.nodes():
        ci = node_comm[n]
        within_w = 0.0
        cross_w = 0.0
        within_n = 0
        cross_n = 0
        for nb, d in und[n].items():
            w = float(d.get("weight", 1.0))
            if node_comm[nb] == ci:
                within_w += w
                within_n += 1
            else:
                cross_w += w
                cross_n += 1
        tot = within_w + cross_w
        cross_share = cross_w / tot if tot > 0 else 0.0
        feat[n] = {
            "community_id": ci,
            "community_size": comm_size[ci],
            "within_comm_wdeg": within_w,
            "cross_comm_wdeg": cross_w,
            "cross_comm_share": cross_share,
            "within_comm_deg": within_n,
            "cross_comm_deg": cross_n,
            # brokerage proxy: normalized betweenness x (1 + cross-community degree)
            "bridge_score": betweenness.get(n, 0.0) * (1.0 + cross_n),
            # hub-in-community proxy: mean within-community edge weight per other member
            "hub_score": within_w / max(1, comm_size[ci] - 1),
            "is_boundary": cross_share >= 0.5,
        }
    return feat, node_comm, comm_size


def compute_features(edges: pd.DataFrame) -> pd.DataFrame:
    G, und, monthly, monthly_w = build_graphs(edges)
    decay = monthly_decay_weights()

    # --- static centrality on the rolling-window (90d aggregate) graph ---
    kcore = nx.core_number(und)
    clustering = nx.clustering(und)
    pagerank = nx.pagerank(G, alpha=0.85, weight="weight")
    deg = dict(und.degree())

    # betweenness: full on small graphs, sampled k=1000 otherwise (recorded)
    n_nodes, n_edges = und.number_of_nodes(), und.number_of_edges()
    betweenness_method = "full"
    t0 = time.time()
    if n_nodes <= 30000 and n_edges <= 120000:
        betweenness = nx.betweenness_centrality(und, weight="weight", normalized=True)
    else:
        betweenness = nx.betweenness_centrality(und, k=1000, weight="weight",
                                                normalized=True)
        betweenness_method = f"sampled_k1000 (n={n_nodes}, m={n_edges})"
    print(f"[btw] method={betweenness_method} nodes={n_nodes} edges={n_edges} "
          f"took={time.time()-t0:.1f}s", flush=True)

    # --- temporal features from monthly snapshots ---
    recency_wdeg: dict[int, float] = {}
    trend: dict[int, float] = {}
    active_months: dict[int, int] = {}
    persistent_edges: dict[int, int] = {}
    mutual_pairs: dict[int, int] = {}
    new_edges_recent: dict[int, int] = {}

    for n in G.nodes():
        rw = 0.0
        for m, wdict in monthly_w.items():
            rw += sum(w for (u, v), w in wdict.items() if u == n or v == n) * decay[m]
        recency_wdeg[n] = rw
        am = sum(1 for m in config.MONTHS if any(u == n or v == n for (u, v) in monthly_w[m]))
        active_months[n] = am

        # trend: normalized linear slope over month indices (0=Jun,1=Jul,2=Aug)
        w_by_m = [sum(w for (u, v), w in monthly_w[m].items() if u == n or v == n)
                  for m in config.MONTHS]
        xs = np.array([0.0, 1.0, 2.0])
        ys = np.array(w_by_m, dtype=float)
        if ys.sum() > 0:
            slope = np.polyfit(xs, ys, 1)[0]
            trend[n] = slope / (ys.sum() + 1.0)
        else:
            trend[n] = 0.0

    # edge-level temporal motif proxies
    edge_months: dict[tuple, set] = {}
    for m, wdict in monthly_w.items():
        for (u, v) in wdict:
            edge_months.setdefault((u, v), set()).add(m)
    for n in G.nodes():
        persistent_edges[n] = 0
        new_edges_recent[n] = 0
        for (u, v), ms in edge_months.items():
            if u == n or v == n:
                if len(ms) >= 2:
                    persistent_edges[n] += 1
                if "2022-08" in ms and not (ms & {"2022-06", "2022-07"}):
                    new_edges_recent[n] += 1
    for n in G.nodes():
        mutual_pairs[n] = sum(1 for nb in G.successors(n)
                              if G.has_edge(nb, n))

    triangles = nx.triangles(und)

    comm_feat, node_comm, comm_size = community_features(G, und, betweenness)

    rows = []
    for n in G.nodes():
        w_in = float(sum(d["weight"] for _, _, d in G.in_edges(n, data=True)))
        w_out = float(sum(d["weight"] for _, _, d in G.out_edges(n, data=True)))
        d_in = G.in_degree(n)
        d_out = G.out_degree(n)
        cf = comm_feat[n]
        rows.append({
            "target_exgraph_node_id": int(n),
            "deg_in": d_in, "deg_out": d_out, "deg_und": deg.get(n, 0),
            "wdeg_in": w_in, "wdeg_out": w_out,
            "wdeg_und": w_in + w_out,
            "pagerank": pagerank.get(n, 0.0),
            "kcore": kcore.get(n, 0),
            "clustering": clustering.get(n, 0.0),
            "betweenness": betweenness.get(n, 0.0),
            "betweenness_method": betweenness_method,
            # temporal
            "recency_wdeg": recency_wdeg.get(n, 0.0),
            "activity_trend": trend.get(n, 0.0),
            "active_months": active_months.get(n, 0),
            "persistent_edges": persistent_edges.get(n, 0),
            "mutual_pairs": mutual_pairs.get(n, 0),
            "triangles": triangles.get(n, 0),
            "new_edges_recent": new_edges_recent.get(n, 0),
            # community
            "community_id": cf["community_id"],
            "community_size": cf["community_size"],
            "within_comm_wdeg": cf["within_comm_wdeg"],
            "cross_comm_wdeg": cf["cross_comm_wdeg"],
            "cross_comm_share": cf["cross_comm_share"],
            "bridge_score": cf["bridge_score"],
            "hub_score": cf["hub_score"],
            "is_boundary": cf["is_boundary"],
        })
    df = pd.DataFrame(rows)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    return df, G, und, monthly, monthly_w, node_comm, comm_size, betweenness_method


def main() -> None:
    config.DATA.mkdir(parents=True, exist_ok=True)

    edges = pull_edges()
    edges.to_csv(config.DATA / "edges_asof_20220901.csv", index=False)

    feats, G, und, monthly, monthly_w, node_comm, comm_size, btw_method = \
        compute_features(edges)
    feats.to_csv(config.DATA / "structural_features_20220901.csv", index=False)

    # monthly graph stats
    monthly_stats = {}
    for m in config.MONTHS:
        gm = monthly[m]
        monthly_stats[m] = {
            "nodes": gm.number_of_nodes(),
            "edges": gm.number_of_edges(),
            "event_weight": int(sum(d["weight"] for _, _, d in gm.edges(data=True))),
        }
    full_stats = {
        "nodes": G.number_of_nodes(),
        "directed_edges": G.number_of_edges(),
        "undirected_edges": und.number_of_edges(),
        "monthly": monthly_stats,
        "betweenness_method": btw_method,
    }

    # community summary
    comm_df = pd.DataFrame([
        {"community_id": ci, "size": s} for ci, s in comm_size.items()
    ]).sort_values("size", ascending=False).reset_index(drop=True)
    comm_summary = {
        "n_communities": len(comm_size),
        "top_sizes": comm_df.head(10).to_dict(orient="records"),
        "n_boundary_wallets": int(feats["is_boundary"].sum()),
    }

    manifest = {
        "cutoff": config.CUTOFF,
        "lookback_window": [config.LOOKBACK_START, config.CUTOFF],
        "edge_scope": "matched-matched primary edges (both endpoints in the "
                      "27,613 EX-Graph-mapped set), counterparty_present, "
                      "not self_transaction",
        "leakage_statement": "features use only events strictly before cutoff; "
                             "static full-window prior is kept separate and "
                             "labeled leaky",
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
        "n_edge_rows_pulled": len(edges),
        "graph": full_stats,
        "community_summary": comm_summary,
    }
    with open(config.DATA / "monthly_graph_stats.json", "w") as f:
        json.dump(full_stats, f, indent=2)
    with open(config.DATA / "community_summary.json", "w") as f:
        json.dump(comm_summary, f, indent=2)
    with open(config.DATA / "build_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print("[done] structural_features:", feats.shape)
    print("[done] graph:", json.dumps(full_stats))


if __name__ == "__main__":
    main()
