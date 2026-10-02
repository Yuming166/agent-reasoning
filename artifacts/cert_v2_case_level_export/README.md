# Certificate v2 case-level export (featfix run 20261002T000000Z)

Per-case details for the 150 dev cases (cutoff 2022-07-01) of the
`cert_v2_featfix_20261002T000000Z` run: pool state, full ranks for four
retrievers, top-50 lists, and metric denominator structure.

## Files

| File | Content |
|---|---|
| `cert_v2_featfix_20261002T000000Z_percase_full.csv` | Wide table, 150 rows x 54 cols: pool state + per-variant rank stats + top-k hits + denominator flags |
| `cert_v2_featfix_20261002T000000Z_percase_ranks_long.csv` | Long table, 150 cases x 4 variants |
| `cert_v2_featfix_20261002T000000Z_denominator_structure.json` | Denominator structure and rank semantics |
| `case_pool_state.csv` | Per-case pool state (active, visibility, supported, pool_size, ...) |
| `case_ranks_by_seed.csv` | Per-variant per-seed case ranks (own_frequency has seed0 only) |
| `case_mean_rank.csv` | Seed-averaged case ranks |
| `top50_{variant}_seed0.parquet` | Candidate-level top-50 lists per case (case_id, candidate, rank, score) |
| `denominator_structure.json` | Earlier denominator summary (same structure) |

## Variants

- `chain_all` — certificate-augmented scorer (all feature blocks)
- `direct_global_legacy` — strong frequency baseline (small MLP)
- `own_frequency` — parameter-free frequency baseline (deterministic, seed0 only)
- `graphmixer` — GNN baseline (3.4M params)

## Key numbers (52 active dev wallets; R@k = fraction of actives with target rank in 1..k; rank<=0 counts as miss)

| Variant | R@5 | R@50 |
|---|---:|---:|
| chain_all | 0.3782 | 0.6090 |
| direct_global_legacy | 0.3654 | 0.6090 |
| own_frequency | 0.2692 | 0.5769 |
| graphmixer | 0.2436 | 0.5128 |

Denominators: 150 dev cases -> 52 active -> 40 target-in-pool -> 28 supported.
Visibility (active): own_seen 32, global_seen 11, open_world 9.
Pool sizes: median 4077 (3830-4633).

Rank semantics: `rank > 0` is the in-pool rank of the target; `rank <= 0`
(includes -1) means the target is not in the pool / case not active; those
cases stay in the denominator but never enter a numerator.

Two-stage context (top-50 then top-5): first-stage ceiling is R@50 = 0.609;
current R@5 = 0.378 leaves ~23 points recoverable by a second-stage reranker.
Oracle union of the four methods' top-50 covers 0.673; naive RRF fusion
reaches only 0.365 R@5 / 0.635 R@50, so learned routing/fusion is where the
headroom lives.

## Provenance

Source run: `/storage/gaoym/ex-graph-microtransaction-analysis/artifacts/cert_v2_featfix_20261002T000000Z`
(that directory holds the full run: models/, paired_bootstrap.csv, REPORT.md).
Training: 22 variants x 3 seeds x 6 epochs; seed-averaged wallet-cluster
paired bootstrap (2000 replicates) in the source run's `paired_bootstrap.csv`.

No raw chain data, no candidate pools beyond dev top-50 lists, no credentials.
