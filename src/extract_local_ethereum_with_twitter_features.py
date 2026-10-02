#!/usr/bin/env python3
"""Extract a compact, auditable view of EX-Graph's 35 GB DGL pickle.

This script is deliberately deterministic and local-only.  It does not call an
LLM, an OpenAI-compatible endpoint, a cloud API, or a text-cleaning service.
The input pickle is read but never modified.

The released ``twitter_matching.csv`` contains Ethereum-side node ids.  The
large DGL graph does not expose address labels, so numeric in-range joins are
written with an explicit ``unverified_namespace`` status rather than being
presented as an authoritative address crosswalk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
STRUCTURAL_KEYS = (
    "total_degree",
    "in_degree",
    "out_degree",
    "number_of_neighbors",
    "in_neighbors",
    "out_neighbors",
    "most_frequent_neighbor_transactions",
    "average_neighbor_degree",
)
PCA8_KEY = "pca_8_normalized_twitter_features"
COMBINED_PCA8_KEY = "combine_normalized_pca_8_twitter_features"
TWITTER_KEY = "twitter_features"
FEATURES_KEY = "features"


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return str(value) if not math.isfinite(value) else value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return repr(value)


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def tensor_numpy(graph: Any, key: str) -> np.ndarray:
    value = graph.ndata[key]
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def field_summary(array: np.ndarray, *, scan_limit: int = 50_000_000) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": type(array).__name__,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "numel": int(array.size),
    }
    if not np.issubdtype(array.dtype, np.number) or not array.size:
        result["finite_values"] = None
        return result
    # Avoid allocating multi-gigabyte boolean masks repeatedly for redundant
    # 770/778-dimensional tensors.  The selected Twitter tensor is checked in
    # full separately below; smaller fields receive exact summary statistics.
    if array.size > scan_limit:
        result["finite_values"] = "not_scanned_large_field"
        return result
    finite_mask = np.isfinite(array)
    result["finite_values"] = int(finite_mask.sum())
    finite = array[finite_mask]
    if finite.size:
        result.update(
            {
                "min": float(finite.min()),
                "max": float(finite.max()),
                "mean": float(finite.mean()),
            }
        )
    return result


def ensure_2d(array: np.ndarray, key: str, width: int | None = None) -> None:
    if array.ndim != 2:
        raise ValueError(f"{key} must be 2-D, got shape {array.shape}")
    if width is not None and array.shape[1] != width:
        raise ValueError(f"{key} must have width {width}, got shape {array.shape}")
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError(f"{key} must be numeric, got {array.dtype}")


def parquet_write_chunks(
    output_path: Path,
    n: int,
    chunk_size: int,
    columns: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Write a dense numeric/boolean table without making one giant DataFrame."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    writer = None
    row_groups = 0
    try:
        for start in range(0, n, chunk_size):
            end = min(n, start + chunk_size)
            batch = {name: array[start:end] for name, array in columns.items()}
            table = pa.Table.from_pydict(batch)
            if writer is None:
                writer = pq.ParquetWriter(
                    temp_path,
                    table.schema,
                    compression="zstd",
                    use_dictionary=False,
                    write_statistics=True,
                )
            writer.write_table(table, row_group_size=end - start)
            row_groups += 1
            log(f"wrote node rows {start:,}:{end:,} ({end / n:.1%})")
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise RuntimeError("no rows were written")
    temp_path.replace(output_path)
    return {"rows": n, "row_groups": row_groups, "bytes": output_path.stat().st_size}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n")


def output_sha(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def parse_mapping(mapping_path: Path, n_nodes: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = pd.read_csv(mapping_path)
    expected = {"node_id", "ethereum_address"}
    missing = expected - set(raw.columns)
    if missing:
        raise ValueError(f"mapping is missing columns: {sorted(missing)}")
    raw = raw[["node_id", "ethereum_address"]].copy()
    raw["mapping_row_id"] = np.arange(len(raw), dtype=np.int64)
    raw["ethereum_address"] = raw["ethereum_address"].astype(str).str.strip().str.lower()
    raw["address_format_valid"] = raw["ethereum_address"].map(lambda x: bool(ADDRESS_RE.fullmatch(x)))
    raw["eth_node_id"] = pd.to_numeric(raw["node_id"], errors="coerce")
    if raw["eth_node_id"].isna().any():
        raw["node_id_parse_valid"] = False
    else:
        raw["node_id_parse_valid"] = True
        raw["eth_node_id"] = raw["eth_node_id"].astype(np.int64)
    raw["exact_pair_duplicate"] = raw.duplicated(["eth_node_id", "ethereum_address"], keep=False)
    pair_counts = (
        raw.groupby(["eth_node_id", "ethereum_address"], dropna=False, as_index=False)
        .size()
        .rename(columns={"size": "mapping_row_count"})
    )
    pairs = raw.drop_duplicates(["eth_node_id", "ethereum_address"], keep="first").copy()
    pairs = pairs.drop(columns=["mapping_row_id", "exact_pair_duplicate"], errors="ignore")
    pairs = pairs.merge(pair_counts, on=["eth_node_id", "ethereum_address"], how="left", validate="one_to_one")
    pairs["node_id_in_source_range"] = (
        pairs["node_id_parse_valid"]
        & pairs["eth_node_id"].between(0, n_nodes - 1)
    )
    pairs["address_join_status"] = np.where(
        pairs["node_id_in_source_range"],
        "numeric_range_only_unverified_namespace",
        "out_of_source_range",
    )
    address_node_counts = pairs.groupby("ethereum_address")["eth_node_id"].nunique()
    node_address_counts = pairs.groupby("eth_node_id")["ethereum_address"].nunique()
    pairs["address_has_node_conflict"] = pairs["ethereum_address"].map(address_node_counts).gt(1)
    pairs["node_has_address_conflict"] = pairs["eth_node_id"].map(node_address_counts).gt(1)
    pairs = pairs[
        [
            "eth_node_id",
            "ethereum_address",
            "address_format_valid",
            "node_id_parse_valid",
            "node_id_in_source_range",
            "mapping_row_count",
            "address_has_node_conflict",
            "node_has_address_conflict",
            "address_join_status",
        ]
    ].sort_values(["node_id_in_source_range", "eth_node_id", "ethereum_address"], ascending=[False, True, True])
    pairs.reset_index(drop=True, inplace=True)

    audit = {
        "raw_rows": int(len(raw)),
        "unique_pairs": int(len(pairs)),
        "exact_duplicate_rows": int(raw.duplicated(["eth_node_id", "ethereum_address"], keep="first").sum()),
        "unique_addresses": int(pairs["ethereum_address"].nunique()),
        "unique_node_ids": int(pairs["eth_node_id"].nunique()),
        "min_node_id": int(pairs["eth_node_id"].min()),
        "max_node_id": int(pairs["eth_node_id"].max()),
        "in_source_range_pairs": int(pairs["node_id_in_source_range"].sum()),
        "out_of_source_range_pairs": int((~pairs["node_id_in_source_range"]).sum()),
        "invalid_address_rows": int((~pairs["address_format_valid"]).sum()),
        "address_node_conflict_pairs": int(pairs["address_has_node_conflict"].sum()),
        "node_address_conflict_pairs": int(pairs["node_has_address_conflict"].sum()),
    }
    return pairs, audit


def reference_alignment(
    pairs: pd.DataFrame,
    features: np.ndarray,
    reference_path: Path,
) -> dict[str, Any]:
    """Compare the source feature graph with the older address-keyed artifact.

    This is only an audit.  It never uses the reference values to overwrite the
    large graph and does not turn a numeric node-id join into a crosswalk.
    """
    result: dict[str, Any] = {
        "reference_path": str(reference_path),
        "reference_exists": reference_path.exists(),
        "comparison_basis": "source features[0:3] vs reference degree/in_degree/out_degree",
    }
    if not reference_path.exists():
        result["status"] = "not_run_reference_missing"
        return result
    ref = pd.read_csv(reference_path, usecols=["ethereum_address", "exgraph_node_id", "in_degree", "out_degree", "degree"])
    ref["ethereum_address"] = ref["ethereum_address"].astype(str).str.strip().str.lower()
    joined = pairs.merge(ref, on="ethereum_address", how="inner", validate="one_to_one", suffixes=("", "_reference"))
    joined = joined[joined["node_id_in_source_range"]].copy()
    result["reference_rows"] = int(len(ref))
    result["joined_in_range_rows"] = int(len(joined))
    if joined.empty:
        result["status"] = "no_joined_rows"
        return result
    idx = joined["eth_node_id"].astype(np.int64).to_numpy()
    src = features[idx, :3].astype(np.float64, copy=False)
    target = joined[["degree", "in_degree", "out_degree"]].to_numpy(dtype=np.float64)
    diff = np.abs(src - target)
    row_exact = np.all(diff == 0, axis=1)
    result.update(
        {
            "field_names": ["total_degree_vs_degree", "in_degree_vs_in_degree", "out_degree_vs_out_degree"],
            "field_exact_counts": [int(x) for x in np.sum(diff == 0, axis=0)],
            "field_exact_fractions": [float(x) for x in np.mean(diff == 0, axis=0)],
            "row_exact_count": int(row_exact.sum()),
            "row_exact_fraction": float(row_exact.mean()),
            "max_abs_diff": [float(x) for x in diff.max(axis=0)],
            "mean_abs_diff": [float(x) for x in diff.mean(axis=0)],
            "status": "mismatch_or_match_observed",
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/storage/gaoym/ethereum_with_twitter_features.pkl"),
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("vendor/EX-Graph-repo/twitter_matching.csv"),
    )
    parser.add_argument(
        "--reference-structural",
        type=Path,
        default=Path("artifacts/exgraph_structural_features.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ethereum_with_twitter_features_v1"),
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--skip-source-hash", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    for path in (args.source, args.mapping):
        if not path.exists():
            parser.error(f"file not found: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_names = (
        "node_features_compact.parquet",
        "mapped_address_features.parquet",
        "address_mapping_audit.csv",
        "manifest.json",
        "README.md",
    )
    if not args.overwrite:
        existing = [args.output_dir / name for name in output_names if (args.output_dir / name).exists()]
        if existing:
            parser.error("outputs already exist; use --overwrite: " + ", ".join(map(str, existing)))

    started = time.time()
    source_stat_before = args.source.stat()
    source_hash = None
    if not args.skip_source_hash:
        log(f"hashing source ({source_stat_before.st_size:,} bytes)")
        source_hash = sha256_file(args.source)
        log(f"source sha256={source_hash}")
    source_stat_after_hash = args.source.stat()
    if (source_stat_before.st_size, source_stat_before.st_mtime_ns) != (
        source_stat_after_hash.st_size,
        source_stat_after_hash.st_mtime_ns,
    ):
        raise RuntimeError("source changed while hashing; refusing to continue")

    log("loading DGL pickle locally; no network/model/API call is used")
    # Import DGL before unpickling so the serialized DGLGraph class is available.
    import dgl  # noqa: F401

    with args.source.open("rb") as handle:
        graph = pickle.load(handle)
    source_stat_after_load = args.source.stat()
    if (source_stat_before.st_size, source_stat_before.st_mtime_ns) != (
        source_stat_after_load.st_size,
        source_stat_after_load.st_mtime_ns,
    ):
        raise RuntimeError("source changed during load; refusing to write derived outputs")

    n_nodes = int(graph.num_nodes())
    n_edges = int(graph.num_edges())
    ndata_keys = sorted(str(k) for k in graph.ndata.keys())
    edata_keys = sorted(str(k) for k in graph.edata.keys())
    log(f"loaded {type(graph).__name__}: nodes={n_nodes:,}, edges={n_edges:,}")
    log(f"ndata keys={ndata_keys}")
    log(f"edata keys={edata_keys}")

    arrays: dict[str, np.ndarray] = {}
    for key in ndata_keys:
        arrays[key] = tensor_numpy(graph, key)
    required = set(STRUCTURAL_KEYS) | {FEATURES_KEY, TWITTER_KEY, PCA8_KEY, COMBINED_PCA8_KEY}
    missing = required - set(arrays)
    if missing:
        raise RuntimeError(f"required ndata keys missing: {sorted(missing)}")
    for key in STRUCTURAL_KEYS:
        if arrays[key].shape != (n_nodes,):
            raise RuntimeError(f"scalar structural key has unexpected shape: {key}={arrays[key].shape}")
    ensure_2d(arrays[FEATURES_KEY], FEATURES_KEY, 8)
    ensure_2d(arrays[TWITTER_KEY], TWITTER_KEY, 770)
    ensure_2d(arrays[PCA8_KEY], PCA8_KEY, 16)
    ensure_2d(arrays[COMBINED_PCA8_KEY], COMBINED_PCA8_KEY, 16)
    for key, array in arrays.items():
        if array.shape[0] != n_nodes:
            raise RuntimeError(f"ndata field {key} has first dimension {array.shape[0]}, expected {n_nodes}")

    # Validate the semantic 8-dimensional structural view without assuming it.
    structural_stack = np.column_stack([arrays[key] for key in STRUCTURAL_KEYS])
    structural_diff = np.abs(arrays[FEATURES_KEY].astype(np.float64) - structural_stack.astype(np.float64))
    structural_rows_exact = np.all(structural_diff == 0, axis=1)
    structural_names = list(STRUCTURAL_KEYS) if np.all(structural_diff == 0) else [f"eth_structural_f{i}" for i in range(8)]
    # The two 16-d views are kept separately because they may represent different
    # normalizations even when their dimensions are identical.
    pca_diff = np.abs(arrays[PCA8_KEY].astype(np.float64) - arrays[COMBINED_PCA8_KEY].astype(np.float64))

    mapping_pairs, mapping_audit = parse_mapping(args.mapping, n_nodes)
    log(
        "mapping rows="
        f"{mapping_audit['raw_rows']:,}, unique_pairs={mapping_audit['unique_pairs']:,}, "
        f"in_range={mapping_audit['in_source_range_pairs']:,}, "
        f"out_of_range={mapping_audit['out_of_source_range_pairs']:,}"
    )

    # Write the full node table in row groups.  Only compact, model-relevant
    # views are materialized; the redundant 35 GB tensor set remains in the
    # source pickle and is documented in the manifest.
    node_columns: dict[str, np.ndarray] = {
        "eth_node_id": np.arange(n_nodes, dtype=np.int64),
        "has_x_features": np.zeros(n_nodes, dtype=np.bool_),
        "twitter_nonzero_dims": np.zeros(n_nodes, dtype=np.int16),
        "twitter_l2_norm": np.zeros(n_nodes, dtype=np.float32),
    }
    for i, name in enumerate(structural_names):
        node_columns[name] = arrays[FEATURES_KEY][:, i].astype(np.float32, copy=False)
    for i in range(16):
        node_columns[f"pca8_feature_{i:02d}"] = arrays[PCA8_KEY][:, i].astype(np.float32, copy=False)
        node_columns[f"combined_pca8_feature_{i:02d}"] = arrays[COMBINED_PCA8_KEY][:, i].astype(np.float32, copy=False)

    # Availability summary uses the original 770-d tensor, not the PCA values
    # (which contain the structural part and can be nonzero for every node).
    twitter = arrays[TWITTER_KEY]
    finite_twitter = np.isfinite(twitter)
    safe_twitter = np.where(finite_twitter, twitter, 0)
    nonzero_dims = np.count_nonzero(safe_twitter != 0, axis=1)
    l2 = np.sqrt(np.sum(np.square(safe_twitter.astype(np.float64)), axis=1, dtype=np.float64))
    node_columns["has_x_features"][:] = nonzero_dims > 0
    node_columns["twitter_nonzero_dims"][:] = nonzero_dims.astype(np.int16)
    node_columns["twitter_l2_norm"][:] = l2.astype(np.float32)

    full_path = args.output_dir / "node_features_compact.parquet"
    full_stats = parquet_write_chunks(full_path, n_nodes, args.chunk_size, node_columns)

    # Mapping audit CSV contains all unique pairs, including out-of-range ids.
    mapping_path = args.output_dir / "address_mapping_audit.csv"
    mapping_pairs.to_csv(mapping_path, index=False)

    # Produce an address-keyed compact table only for numeric in-range ids.  The
    # status column is intentionally explicit: this is not an authoritative
    # crosswalk until the graph version/namespace is independently confirmed.
    in_range = mapping_pairs[mapping_pairs["node_id_in_source_range"]].copy()
    idx = in_range["eth_node_id"].astype(np.int64).to_numpy()
    mapped_columns: dict[str, Any] = {
        "eth_node_id": idx,
        "ethereum_address": in_range["ethereum_address"].to_numpy(dtype=object),
        "mapping_row_count": in_range["mapping_row_count"].to_numpy(dtype=np.int16),
        "join_status": np.full(len(in_range), "numeric_range_only_unverified_namespace", dtype=object),
        "has_x_features": node_columns["has_x_features"][idx],
        "twitter_nonzero_dims": node_columns["twitter_nonzero_dims"][idx],
        "twitter_l2_norm": node_columns["twitter_l2_norm"][idx],
    }
    for name in structural_names:
        mapped_columns[name] = node_columns[name][idx]
    for i in range(16):
        mapped_columns[f"pca8_feature_{i:02d}"] = node_columns[f"pca8_feature_{i:02d}"][idx]
        mapped_columns[f"combined_pca8_feature_{i:02d}"] = node_columns[f"combined_pca8_feature_{i:02d}"][idx]
    mapped_df = pd.DataFrame(mapped_columns)
    mapped_path = args.output_dir / "mapped_address_features.parquet"
    mapped_tmp = mapped_path.with_suffix(mapped_path.suffix + ".tmp")
    mapped_df.to_parquet(mapped_tmp, index=False, engine="pyarrow", compression="zstd")
    mapped_tmp.replace(mapped_path)

    alignment = reference_alignment(mapping_pairs, arrays[FEATURES_KEY], args.reference_structural)
    source_feature_fields = {name: field_summary(arrays[name]) for name in ndata_keys}
    source_feature_fields["_structural_stack"] = field_summary(structural_stack)
    manifest: dict[str, Any] = {
        "schema_version": "ethereum_with_twitter_features_compact_v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "processing": {
            "local_only": True,
            "llm_used": False,
            "remote_api_used": False,
            "source_unchanged_during_processing": True,
            "chunk_size": args.chunk_size,
            "elapsed_seconds": round(time.time() - started, 2),
        },
        "source": {
            "path": str(args.source),
            "bytes": int(source_stat_before.st_size),
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(source_stat_before.st_mtime)),
            "sha256": source_hash,
            "loaded_type": f"{type(graph).__module__}.{type(graph).__name__}",
            "num_nodes": n_nodes,
            "num_edges": n_edges,
            "ntypes": list(getattr(graph, "ntypes", [])),
            "etypes": list(getattr(graph, "etypes", [])),
            "ndata_keys": ndata_keys,
            "edata_keys": edata_keys,
        },
        "source_ndata_fields": source_feature_fields,
        "selected_feature_views": {
            "structural_source_key": FEATURES_KEY,
            "structural_columns": structural_names,
            "structural_column_mapping_verified": bool(np.all(structural_diff == 0)),
            "twitter_source_key": TWITTER_KEY,
            "twitter_source_width": 770,
            "pca8_source_key": PCA8_KEY,
            "combined_pca8_source_key": COMBINED_PCA8_KEY,
            "output_float_dtype": "float32",
            "output_float64_to_float32_cast": True,
            "pca8_vs_combined_pca8_max_abs_difference": float(pca_diff.max()),
            "pca8_vs_combined_pca8_exact_rows": int(np.all(pca_diff == 0, axis=1).sum()),
        },
        "feature_availability": {
            "nodes_with_any_nonzero_twitter_feature": int((nonzero_dims > 0).sum()),
            "nodes_without_nonzero_twitter_feature": int((nonzero_dims == 0).sum()),
            "max_nonzero_twitter_dims": int(nonzero_dims.max()),
            "nodes_with_nonfinite_twitter_values": int((~finite_twitter.all(axis=1)).sum()),
        },
        "mapping": {
            "path": str(args.mapping),
            **mapping_audit,
            "namespace_status": "unverified_numeric_range_only",
            "namespace_note": (
                "The mapping node_id values are only checked against the large graph's numeric range. "
                "The published reference graph has a different node/edge version and the large graph has "
                "no address field; do not treat this table as an authoritative address-to-feature crosswalk."
            ),
            "reference_structural_alignment": alignment,
        },
        "outputs": {
            "node_features_compact": {
                **full_stats,
                "path": str(full_path),
                "sha256": sha256_file(full_path),
                "columns": list(node_columns),
            },
            "mapped_address_features": {
                "rows": int(len(mapped_df)),
                "bytes": int(mapped_path.stat().st_size),
                "path": str(mapped_path),
                "sha256": sha256_file(mapped_path),
                "columns": list(mapped_df.columns),
            },
            "address_mapping_audit": output_sha(mapping_path) | {"rows": int(len(mapping_pairs))},
        },
        "claim_boundary": (
            "This release contains compact node-id-keyed features for all nodes and a separately marked "
            "numeric-range-only address join. It does not claim that the 35 GB graph's node namespace is "
            "identical to twitter_matching.csv until an authoritative address label/crosswalk is supplied."
        ),
    }
    manifest_path = args.output_dir / "manifest.json"
    write_json(manifest_path, manifest)
    readme_path = args.output_dir / "README.md"
    readme_path.write_text(
        "# Local compact extraction of `ethereum_with_twitter_features.pkl`\n\n"
        "- `node_features_compact.parquet`: all nodes, keyed by `eth_node_id`; 8 structural columns, "
        "16-d PCA/X view, 16-d combined normalized view, and X-feature availability summaries.\n"
        "- `mapped_address_features.parquet`: only numeric in-range rows from `twitter_matching.csv`. "
        "Every row is marked `numeric_range_only_unverified_namespace`.\n"
        "- `address_mapping_audit.csv`: all unique mapping pairs, including the 136 out-of-range rows.\n"
        "- `manifest.json`: source hash/schema, field audit, output hashes, and alignment caveats.\n\n"
        "The original 35 GB pickle is not modified or uploaded. No LLM or remote inference API was used. "
        "The address join must not be used as a confirmed crosswalk until the graph namespace is verified.\n"
    )
    manifest["outputs"]["readme"] = output_sha(readme_path)
    # Rewrite once with the README output hash included.  A manifest cannot
    # contain its own final hash without being self-referential, so callers can
    # hash this file externally (for example with sha256sum).
    write_json(manifest_path, manifest)

    log(f"done in {manifest['processing']['elapsed_seconds']} s")
    log(f"full table: {full_path} ({full_stats['bytes']:,} bytes)")
    log(f"mapped table: {mapped_path} ({len(mapped_df):,} rows)")
    log(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
