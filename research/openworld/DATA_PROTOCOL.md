# Data protocol

## Temporal source

Primary temporal source: BigQuery `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`,
constructed from native transactions, token transfers, and internal traces. The static
`ethereum_graph.gpickle` is not a temporal event stream and is not used to order events.

## Evaluation labels

`vendor/EX-Graph-repo/dune_wash_trade_tx.csv` is an external evaluation-only reference.
It is not used to train, select, tune, or calibrate the discovery model. The file has no
transaction timestamp; timestamp recovery must come from a bounded join to the temporal
Ethereum tables and must be recorded as an availability/coverage audit.

## Required per-artifact fields

Every output records: data version/hash, cutoff, lookback, horizon, event families,
label access, graph construction, model/score, seed, byte/cost guard, and leakage audit.

## Current known overlap boundary

The local label file contains 22,702 rows / 22,551 unique transaction hashes. Only 258
rows have at least one endpoint in the 27,613-address EX-Graph mapping; only 14 rows have
both endpoints mapped. This is an overlap feasibility fact, not a prevalence estimate.
