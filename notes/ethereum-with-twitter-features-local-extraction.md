# 35 GB Ethereum Graph with X features: local extraction (2026-09-10)

## Scope and reproducibility

The source file was processed locally only:

- source: `/storage/gaoym/ethereum_with_twitter_features.pkl`
- size: `37,329,036,840` bytes (`34.765 GiB`)
- source SHA-256: `074bc973e025e85fd57106cd4ef7f83d5432ce5f8ef1c64690c2bbfd587b42cd`
- loaded object: `dgl.heterograph.DGLGraph`
- graph size: `1,709,575` nodes and `13,170,869` edges
- node data: 24 fields; edge data: empty
- environment: `/storage/gaoym/ex-graph-microtransaction-analysis/.venv-35gb` (Python 3.12, DGL 2.1.0, torch 2.2.1+cpu, pyarrow 19.0.1)

Command used:

```bash
/storage/gaoym/ex-graph-microtransaction-analysis/.venv-35gb/bin/python \
  src/extract_local_ethereum_with_twitter_features.py \
  --source /storage/gaoym/ethereum_with_twitter_features.pkl \
  --mapping vendor/EX-Graph-repo/twitter_matching.csv \
  --reference-structural artifacts/exgraph_structural_features.csv \
  --output-dir artifacts/ethereum_with_twitter_features_v1 \
  --chunk-size 100000 --overwrite
```

No LLM, OpenAI-compatible endpoint, cloud inference service, or text-cleaning API was used. The original pickle was not modified or deleted.

## Derived products

All files are under `artifacts/ethereum_with_twitter_features_v1/`:

- `node_features_compact.parquet` — all `1,709,575` source nodes, keyed by `eth_node_id`; 44 columns: 8 structural values, two 16-dimensional PCA/combined views, and X-feature availability summaries (`has_x_features`, nonzero dimension count, L2 norm).
- `mapped_address_features.parquet` — `27,477` rows whose `twitter_matching.csv` node ids fall numerically inside `0..1,709,574`; includes the same compact features and `join_status`.
- `address_mapping_audit.csv` — all `27,613` unique mapping pairs, including the out-of-range rows and conflict/format checks.
- `manifest.json` — source metadata, field dimensions, feature consistency checks, mapping coverage, output hashes, and claim boundary.
- `README.md` — short data-product description.

Important counts:

- `twitter_features` has width `770`; `24,142` of `1,709,575` nodes have at least one nonzero X feature dimension; no non-finite values were observed.
- `features` is exactly the stack of the eight scalar structural fields in the source graph.
- The two retained 16-dimensional views are not duplicates: their maximum absolute difference is about `18.1618` and no row is exactly equal.
- The mapping CSV has `27,614` raw rows, one exact duplicate, and `27,613` unique pairs. `27,477` are in the source numeric range; `136` are outside it.

## Namespace and address-join boundary

The `mapped_address_features.parquet` table is intentionally **not** an authoritative address-to-feature crosswalk. Every row is marked:

```text
numeric_range_only_unverified_namespace
```

Evidence for this boundary:

- `twitter_matching.csv` has Ethereum-side node ids with maximum `1,809,649`.
- The large graph has only `1,709,575` nodes and exposes no address labels in `ndata` or `edata`.
- The published static Ethereum graph in `artifacts/ethereum_graph_audit.json` has a different observed version (`1,810,641` nodes, `11,876,618` edges).
- The merged matching graph is a separate homogeneous DGL graph (`2,833,659` nodes, `18,433,366` edges, one 16-d feature field), not an address-labeled crosswalk. Its node/feature namespace cannot be assumed to be the large graph's prefix.
- For the `27,477` in-range pairs, comparison with the existing address-keyed structural artifact produced only `5,725/27,477` exact matches for the total/degree field, `4,112/27,477` for in-degree, and `4,764/27,477` for out-degree; only `1,906` rows matched all three. This is a version/namespace warning, not a basis for relabeling nodes.

Use the full node table for node-id-keyed feature experiments. Use the address-keyed table only after an authoritative graph-version/crosswalk check is obtained; do not interpret the numeric-range join as proof that a particular Ethereum address owns the attached X vector.

## Validation evidence

- `logs/extract_local_ethereum_with_twitter_features_20260910.log` records the full extraction, including source hash and row-group progress.
- `logs/validate_local_ethereum_with_twitter_features_20260910.log` independently reloads the 35 GB source and checks source-vs-Parquet values for sentinel nodes `0, 1, 2, 62728, 50336, 88942, 520475, 110599, 1700000, 1709574`; all checks passed.
