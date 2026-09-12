"""S_i(t) -> Z_i(t): build the as-of behavioral feature matrix for Group A.

Primary cutoff: 2022-09-01 (config.CUTOFF).
All features use only information <= cutoff:
  * activity / capital / counterparty groups   -> wallet_asof_features_20220901
  * trajectory group                           -> per-wallet gap/dormancy stats
                                                    (bounded BigQuery aggregate)
  * network group                              -> as-of matched-matched temporal
                                                    subgraph features (bounded
                                                    BigQuery edge list + networkx)
  * USD capital (optional, coverage-limited)   -> local wallet_usd_outflow_v1.csv
Future-window labels (fwd30_*) are kept apart from the feature matrix.

Local static structural features (exgraph_structural_features.csv) are
full-period aggregates and are written OUT as a clearly-labelled leaky
"static prior" file, NOT merged into the as-of feature matrix.

Outputs (results/data/):
  feature_matrix_20220901.parquet   feature columns + label columns
  network_features_20220901.csv     as-of matched-matched network features
  trajectory_stats_20220901.csv     per-wallet trajectory stats (raw pull)
  static_prior_20220901.csv         full-period structural prior (leaky label)
  usd_capital_20220901.csv          USD outflow at snapshot (coverage-limited)
  manifest.json                     scope/cutoff/coverage/leakage statement
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import bq_client  # noqa: E402
import config  # noqa: E402


def pull_sql(name: str, max_bytes_billed: int) -> list[dict]:
    sql = (config.SQL / f"{name}.sql").read_text()
    print(f"[pull] {name} ...", flush=True)
    t0 = time.time()
    rows = bq_client.run_bounded_query(sql, max_bytes_billed=max_bytes_billed)
    print(f"[pull] {name} done in {time.time()-t0:.1f}s, {len(rows)} rows", flush=True)
    return rows


def compute_network_features(edge_rows: list[dict]) -> pd.DataFrame:
    """Compute as-of network features on the matched-matched temporal subgraph."""
    if not edge_rows:
        return pd.DataFrame(columns=[
            "target_exgraph_node_id", "asof_mm_in_degree", "asof_mm_out_degree",
            "asof_mm_undir_degree", "asof_mm_w_in_degree", "asof_mm_w_out_degree",
            "asof_mm_pagerank", "asof_mm_kcore", "asof_mm_clustering",
            "asof_mm_hub_neighbors", "in_mm_subgraph"])

    edges = pd.DataFrame(edge_rows)
    G = nx.DiGraph()
    for r in edges.itertuples(index=False):
        u, v, direction, w = int(r.u), int(r.v), r.direction, int(r.weight)
        if u == v:
            continue
        G.add_edge(u, v, weight=w)

    und = G.to_undirected()
    deg = dict(und.degree())
    p90 = np.percentile(list(deg.values()), 90) if deg else 0.0
    kcore = nx.core_number(und)
    clustering = nx.clustering(und)
    pagerank = nx.pagerank(G, alpha=0.85, weight="weight")

    rows = []
    for node in G.nodes():
        rows.append({
            "target_exgraph_node_id": node,
            "asof_mm_in_degree": G.in_degree(node),
            "asof_mm_out_degree": G.out_degree(node),
            "asof_mm_undir_degree": und.degree(node),
            "asof_mm_w_in_degree": float(sum(d["weight"] for _, _, d in G.in_edges(node, data=True))),
            "asof_mm_w_out_degree": float(sum(d["weight"] for _, _, d in G.out_edges(node, data=True))),
            "asof_mm_pagerank": pagerank.get(node, 0.0),
            "asof_mm_kcore": kcore.get(node, 0),
            "asof_mm_clustering": clustering.get(node, 0.0),
            "asof_mm_hub_neighbors": sum(1 for nb in und.neighbors(node) if deg.get(nb, 0) >= p90),
            "in_mm_subgraph": True,
        })
    df = pd.DataFrame(rows)
    df["target_exgraph_node_id"] = df["target_exgraph_node_id"].astype("int64")
    return df


def main() -> None:
    results = config.RESULTS
    data_dir = results / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1) as-of aggregated features + future labels (primary table, 1 partition)
    asof_rows = pull_sql("asof_features_20220901", config.MAX_BYTES_BILLED)
    asof = pd.DataFrame(asof_rows)
    asof["target_exgraph_node_id"] = asof["target_exgraph_node_id"].astype("int64")
    asof = asof.sort_values("target_address").reset_index(drop=True)
    n_wallets = len(asof)

    # 2) trajectory stats (bounded aggregate)
    traj_rows = pull_sql("trajectory_stats", config.MAX_BYTES_BILLED)
    traj = pd.DataFrame(traj_rows)
    traj = traj.rename(columns={"n_events_90d": "n_events_90d_traj"})
    traj_cover = len(traj)

    # 3) network features on matched-matched as-of subgraph (bounded edge list)
    edge_rows = pull_sql("network_edges_asof", config.MAX_BYTES_BILLED)
    net = compute_network_features(edge_rows)
    net_cover = len(net)

    # 4) local artifacts
    usd = pd.read_csv(config.USD_OUTFLOW_CSV)
    usd = usd[usd.snapshot_date == config.CUTOFF].copy()
    usd["target_address"] = usd["target_address"].str.lower()
    usd_cover = len(usd)

    static = pd.read_csv(config.STRUCTURAL_FEATURES_CSV)
    static = static.rename(columns={"ethereum_address": "target_address"})
    static["target_address"] = static["target_address"].str.lower()
    static["target_exgraph_node_id"] = static["exgraph_node_id"].astype("int64")
    static_cover = len(static)

    # 5) merge all as-of feature sources on the primary table's wallet set
    base = asof.copy()
    base = base.merge(traj, on="target_address", how="left")
    base = base.merge(usd[["target_address", "native_usd", "token_usd_priced",
                           "token_rows", "token_rows_priced"]],
                      on="target_address", how="left")
    base = base.merge(net, on="target_exgraph_node_id", how="left")

    # feature columns that are strictly as-of (no future labels)
    feature_cols = [c for c in base.columns if not c.startswith("fwd30_")
                    and c != "importance_proxy_p3"]
    label_cols = [c for c in base.columns if c.startswith("fwd30_")
                  or c == "importance_proxy_p3"]

    # coverage summary
    cov = {}
    for c in feature_cols:
        if base[c].dtype.kind in "if":
            cov[c] = {
                "non_null": int(base[c].notna().sum()),
                "coverage": float(base[c].notna().mean()),
            }
    coverage_report = {
        "n_wallets_primary": n_wallets,
        "n_trajectory_covered": traj_cover,
        "n_network_mm_covered": net_cover,
        "n_usd_covered": usd_cover,
        "n_static_prior_covered": static_cover,
        "cutoff": config.CUTOFF,
        "lookback_window": [config.LOOKBACK_START, config.CUTOFF],
        "label_window": [config.CUTOFF, config.LABEL_END],
        "n_feature_cols": len(feature_cols),
        "n_label_cols": len(label_cols),
    }

    # 6) write outputs
    base.to_parquet(data_dir / "feature_matrix_20220901.parquet", index=False)
    net.to_csv(data_dir / "network_features_20220901.csv", index=False)
    traj.to_csv(data_dir / "trajectory_stats_20220901.csv", index=False)
    usd.to_csv(data_dir / "usd_capital_20220901.csv", index=False)
    static.to_csv(data_dir / "static_prior_20220901.csv", index=False)

    manifest = {
        "scope": "Bounded sample = all 18,519 wallets in wallet_asof_features_20220901 "
                 "partition 2022-09-01 (compact aggregated table, not raw event export).",
        "leakage_statement": (
            "Every feature in the matrix uses only events in "
            f"[{config.LOOKBACK_START}, {config.CUTOFF}) UTC (90-day lookback). "
            "fwd30_* labels use [cutoff, cutoff+30d) and are excluded from clustering. "
            "Static full-period structural features are written to static_prior_20220901.csv "
            "and are NOT part of the as-of feature matrix."),
        "coverage": coverage_report,
        "columns": {"features": feature_cols, "labels": label_cols},
        "bytes_billed_note": "Per-query bytesBilled printed to stdout; all queries partition-filtered "
                             "with maximum_bytes_billed cap.",
    }
    (results / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(coverage_report, indent=2, ensure_ascii=False))
    print("[ok] feature matrix written:", data_dir / "feature_matrix_20220901.parquet")


if __name__ == "__main__":
    main()
