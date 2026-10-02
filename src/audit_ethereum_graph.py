#!/usr/bin/env python3
"""Audit EX-Graph's Ethereum Graph without making transaction-level claims silently.

The official file is a pickle of a NetworkX graph. Loading it requires enough RAM
for the full graph. The audit deliberately checks the graph class first because a
DiGraph cannot represent parallel transactions between the same ordered pair.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return str(value)
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return repr(value)


def numeric_summary(values: list[Any]) -> dict[str, Any]:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    result: dict[str, Any] = {
        "observed": len(values),
        "numeric": len(nums),
        "missing_or_non_numeric": len(values) - len(nums),
    }
    if nums:
        result.update(
            {
                "min": min(nums),
                "max": max(nums),
                "mean": statistics.fmean(nums),
                "median": statistics.median(nums),
                "unique_numeric": len(set(nums)),
                "integer_like": all(float(x).is_integer() for x in nums),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=20)
    args = parser.parse_args()

    if not args.graph.exists():
        parser.error(f"graph not found: {args.graph}")

    started = time.time()
    print(f"loading {args.graph} ({args.graph.stat().st_size:,} bytes)", flush=True)
    with args.graph.open("rb") as handle:
        graph = pickle.load(handle)
    loaded_seconds = time.time() - started

    # NetworkX's API is intentionally accessed through the object so this script
    # remains compatible with the released pickle's class implementation.
    graph_type = f"{type(graph).__module__}.{type(graph).__name__}"
    is_directed = bool(graph.is_directed()) if hasattr(graph, "is_directed") else None
    is_multigraph = bool(graph.is_multigraph()) if hasattr(graph, "is_multigraph") else None
    n_nodes = int(graph.number_of_nodes()) if hasattr(graph, "number_of_nodes") else None
    n_edges = int(graph.number_of_edges()) if hasattr(graph, "number_of_edges") else None

    samples: list[dict[str, Any]] = []
    edge_key_counter: Counter[str] = Counter()
    block_values: list[Any] = []
    weight_values: list[Any] = []
    weight_histogram: Counter[Any] = Counter()
    missing_block = 0
    missing_weight = 0
    nonempty_edges = 0

    # Do not retain all edge attributes in a second structure. This scan is over
    # the already-loaded NetworkX graph and is intentionally one-pass.
    for idx, item in enumerate(graph.edges(data=True)):
        u, v, data = item
        if not isinstance(data, dict):
            data = {"__edge_data_type__": type(data).__name__, "value": repr(data)}
        if len(samples) < max(0, args.sample):
            samples.append(
                {
                    "source_node": jsonable(u),
                    "target_node": jsonable(v),
                    "data": jsonable(data),
                }
            )
        edge_key_counter.update(str(k) for k in data.keys())
        if data:
            nonempty_edges += 1
        if "block_number" in data:
            block_values.append(data["block_number"])
        else:
            missing_block += 1
        if "weight" in data:
            weight_values.append(data["weight"])
            try:
                weight_histogram[data["weight"]] += 1
            except TypeError:
                pass
        else:
            missing_weight += 1

    official = {
        "nodes": 2_610_465,
        "edges": 29_585_858,
        "edge_fields": ["from_address", "to_address", "weight", "block_number"],
    }
    result = {
        "graph_path": str(args.graph),
        "graph_file_bytes": args.graph.stat().st_size,
        "graph_type": graph_type,
        "is_directed": is_directed,
        "is_multigraph": is_multigraph,
        "nodes": n_nodes,
        "edges": n_edges,
        "official_readme_reference": official,
        "counts_match_official_readme": {
            "nodes": n_nodes == official["nodes"],
            "edges": n_edges == official["edges"],
        },
        "edge_key_counts": dict(edge_key_counter),
        "nonempty_edge_attribute_count": nonempty_edges,
        "missing_block_number": missing_block,
        "missing_weight": missing_weight,
        "block_number": numeric_summary(block_values),
        "weight": numeric_summary(weight_values),
        "weight_sum": sum(v for v in weight_values if isinstance(v, (int, float)) and not isinstance(v, bool)),
        "edges_with_weight_gt_one": sum(n for w, n in weight_histogram.items() if isinstance(w, (int, float)) and w > 1),
        "edges_with_weight_equal_one": weight_histogram.get(1, 0),
        "sample_edges": samples,
        "temporal_order_assessment": {
            "parallel_edges_supported": bool(is_multigraph),
            "same_ordered_pair_can_have_multiple_graph_edges": bool(is_multigraph),
            "safe_to_treat_each_graph_edge_as_a_distinct_transaction": bool(is_multigraph),
            "released_graph_has_transaction_level_time_field": bool(block_values),
            "weight_looks_like_multiplicity_count": (
                bool(weight_values)
                and all(isinstance(v, int) and not isinstance(v, bool) for v in weight_values)
                and any(v > 1 for v in weight_values)
            ),
            "caveat": (
                "A NetworkX DiGraph has at most one edge per ordered node pair. "
                "If this is confirmed, repeated transactions for the same (from, to) "
                "pair cannot remain as separate parallel edges; inspect weight and "
                "block_number before using the file as an event sequence."
            ),
        },
        "bottom_line": (
            "The released object is a weighted static NetworkX DiGraph, not a transaction-event stream: "
            "it has no block_number edge field, cannot represent parallel edges, and its integer weight "
            "values are consistent with aggregated transaction multiplicity. Treat this as an evidence-based "
            "dataset conclusion; the publisher does not document the exact weight construction in the README."
            if (is_multigraph is False and not block_values and weight_values)
            else "See the field-level audit above; the graph does not meet the conditions for this conclusion."
        ),
        "load_seconds": loaded_seconds,
        "audit_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
