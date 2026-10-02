"""Emit per-snapshot community_evolution_<cutoff>.json artifacts."""
from __future__ import annotations
import json
import pandas as pd
import config

CUTOFFS = ["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]

def main() -> None:
    gs = json.load(open(config.JSON / "community_graph_stats.json"))
    ev = json.load(open(config.JSON / "community_evolution_summary.json"))
    allm = pd.read_csv(config.DATA / "monthly_communities.csv")
    for c in CUTOFFS:
        d = allm[allm["snapshot"] == c]
        sizes = d.groupby("community_id").size().sort_values(ascending=False)
        role_counts = ev["role_analysis"].get(c, {}).get("role_class_counts", {})
        out = {
            "snapshot": c,
            "lookback_window": [config.CUTOFFS[c], c],
            "graph_stats": gs[c],
            "community_sizes": {
                "n_communities": int(len(sizes)),
                "top10_sizes": [int(x) for x in sizes.head(10).tolist()],
                "mean_size": round(float(sizes.mean()), 2),
                "median_size": float(sizes.median()),
                "max_size": int(sizes.max()),
                "size_gini": round(float(
                    1 - 2 * sum((i + 1) * s for i, s in
                                enumerate(sorted(sizes))) /
                    (len(sizes) * sizes.sum() + 1e-9)), 4),
            },
            "role_analysis": ev["role_analysis"].get(c, {}),
            "role_class_counts": role_counts,
            "membership_file": f"monthly_communities.csv (snapshot={c})",
            "edge_file": f"edges_asof_{c.replace('-', '')}.csv",
            "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
            "method": "networkx.community.greedy_modularity_communities "
                      "(weight), nodes sorted; roles per Group C definitions",
        }
        with open(config.JSON / f"community_evolution_{c.replace('-', '')}.json", "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"[emit] community_evolution_{c.replace('-', '')}.json", flush=True)

if __name__ == "__main__":
    main()
