#!/usr/bin/env python3
"""Extract per-address structural features from EX-Graph's static weighted graph.

Only the 27,613 EX-Graph-mapped addresses are emitted, keeping the output
small. The graph itself is solved from the already-downloaded pickle; nothing
is re-downloaded. Graph nodes are integer EX-Graph node ids (not addresses),
so the mapping dimension ``target_addresses.csv`` is used as the bridge.

Features:
  * graph_node_present : whether the EX-Graph node id exists in the graph
  * in_degree / out_degree : unweighted edge counts
  * w_in_degree / w_out_degree : sum of ``weight`` on in / out edges
  * degree / w_degree : combined totals
  * pagerank (optional, --pagerank) : global recursive importance over the
    directed graph; the canonical "structural influence" prior.

Weighted degree is meaningful here because the released graph aggregates
repeated (from, to) transactions into one weighted edge.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.algorithms.link_analysis import pagerank_alg
from networkx.exception import PowerIterationFailedConvergence

FIELDS = [
    "ethereum_address", "exgraph_node_id", "graph_node_present",
    "in_degree", "out_degree", "w_in_degree", "w_out_degree",
    "degree", "w_degree", "pagerank",
]


def sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--target-addresses", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--graph-sha256", type=str, default=None,
                    help="Optional already-computed graph SHA-256; avoids rehashing 11.6 GB.")
    ap.add_argument("--pagerank", action="store_true",
                    help="Compute global recursive PageRank over the full graph.")
    ap.add_argument("--pagerank-alpha", type=float, default=0.85)
    ap.add_argument("--pagerank-max-iter", type=int, default=100)
    ap.add_argument("--pagerank-tol", type=float, default=1e-6)
    args = ap.parse_args()

    started = time.time()
    print(f"loading graph: {args.graph}", flush=True)
    with args.graph.open("rb") as handle:
        graph = pickle.load(handle)
    load_s = time.time() - started
    print(f"graph loaded in {load_s:.1f}s (type={type(graph).__name__})", flush=True)

    pagerank: dict[Any, float] | None = None
    pagerank_s: float | None = None
    if args.pagerank:
        print("computing PageRank (full graph, recursive)...", flush=True)
        t0 = time.time()
        try:
            pagerank = pagerank_alg._pagerank_python(
                graph,
                alpha=args.pagerank_alpha,
                max_iter=args.pagerank_max_iter,
                tol=args.pagerank_tol,
                weight="weight",
            )
        except PowerIterationFailedConvergence:
            print("PageRank did not converge at default max_iter; retrying with 300.", flush=True)
            pagerank = pagerank_alg._pagerank_python(
                graph,
                alpha=args.pagerank_alpha,
                max_iter=300,
                tol=args.pagerank_tol,
                weight="weight",
            )
        pagerank_s = time.time() - t0
        print(f"PageRank done in {pagerank_s:.1f}s ({len(pagerank)} nodes)", flush=True)

    rows: list[dict[str, Any]] = []
    with args.target_addresses.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            addr = record["ethereum_address"].strip().lower()
            node_id = int(record["exgraph_node_id"])
            present = graph.has_node(node_id) if hasattr(graph, "has_node") else False
            if present:
                in_deg = int(graph.in_degree(node_id))
                out_deg = int(graph.out_degree(node_id))
                w_in = sum(int(d.get("weight", 0)) for _, _, d in graph.in_edges(node_id, data=True))
                w_out = sum(int(d.get("weight", 0)) for _, _, d in graph.out_edges(node_id, data=True))
                pr = pagerank.get(node_id) if pagerank is not None else None
                rows.append({
                    "ethereum_address": addr,
                    "exgraph_node_id": node_id,
                    "graph_node_present": True,
                    "in_degree": in_deg,
                    "out_degree": out_deg,
                    "w_in_degree": w_in,
                    "w_out_degree": w_out,
                    "degree": in_deg + out_deg,
                    "w_degree": w_in + w_out,
                    "pagerank": "" if pr is None else f"{pr:.10g}",
                })
            else:
                rows.append({
                    "ethereum_address": addr,
                    "exgraph_node_id": node_id,
                    "graph_node_present": False,
                    "in_degree": "",
                    "out_degree": "",
                    "w_in_degree": "",
                    "w_out_degree": "",
                    "degree": "",
                    "w_degree": "",
                    "pagerank": "",
                })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    present = [r for r in rows if r["graph_node_present"]]
    pr_values = [float(r["pagerank"]) for r in present if r["pagerank"] != ""]
    manifest: dict[str, Any] = {
        "run_seconds": round(time.time() - started, 2),
        "load_seconds": round(load_s, 2),
        "graph_path": str(args.graph),
        "graph_file_bytes": args.graph.stat().st_size,
        "graph_type": f"{type(graph).__module__}.{type(graph).__name__}",
        "graph_nodes": int(graph.number_of_nodes()),
        "graph_edges": int(graph.number_of_edges()),
        "graph_sha256": args.graph_sha256 or sha256_hex(args.graph),
        "target_addresses_path": str(args.target_addresses),
        "target_addresses_sha256": sha256_hex(args.target_addresses),
        "mapped_rows": len(rows),
        "mapped_rows_present_in_graph": len(present),
        "mapped_rows_missing_from_graph": len(rows) - len(present),
        "output_rows": len(rows),
        "columns": FIELDS,
        "degree_summary": {
            "min_in_degree": min(r["in_degree"] for r in present) if present else None,
            "max_in_degree": max(r["in_degree"] for r in present) if present else None,
            "min_out_degree": min(r["out_degree"] for r in present) if present else None,
            "max_out_degree": max(r["out_degree"] for r in present) if present else None,
            "min_w_in_degree": min(r["w_in_degree"] for r in present) if present else None,
            "max_w_in_degree": max(r["w_in_degree"] for r in present) if present else None,
            "min_w_out_degree": min(r["w_out_degree"] for r in present) if present else None,
            "max_w_out_degree": max(r["w_out_degree"] for r in present) if present else None,
        },
    }
    if pagerank is not None:
        manifest["pagerank"] = {
            "alpha": args.pagerank_alpha,
            "max_iter": args.pagerank_max_iter,
            "tol": args.pagerank_tol,
            "compute_seconds": round(pagerank_s, 2) if pagerank_s is not None else None,
            "mapped_with_pagerank": len(pr_values),
            "min": min(pr_values) if pr_values else None,
            "max": max(pr_values) if pr_values else None,
            "mean": sum(pr_values) / len(pr_values) if pr_values else None,
        }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2)[:1600])
    print(f"wrote {args.output} and {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
