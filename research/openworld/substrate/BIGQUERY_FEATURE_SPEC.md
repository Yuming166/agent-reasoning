# BigQuery feature materialization specification (substrate repair)

**Status:** specification only; no expensive CTAS was run by this audit.

## Goal and grain

Create a compact, leakage-safe table with one row per
`(target_exgraph_node_id, cutoff_time)` for cutoffs
`2022-06-01`, `2022-07-01`, and `2022-08-01`.  The discovery table must be
constructed only from events with `block_timestamp < cutoff_time`.  Keep all
27,613 mapped wallets as the outer dimension and add coverage/count columns;
do not make the wallet eligible only when a counterparty is also EX-Graph
mapped.

Recommended objects:

```text
ictdata-507912.exgraph.openworld_wallet_features_v2
ictdata-507912.exgraph.openworld_future_outcomes_v2  -- evaluation_only
```

Do not export raw transactions.  Build the event-normalization and aggregation
CTAS jobs in BigQuery, partition by event date/cutoff and cluster by
`target_exgraph_node_id, cutoff_time`.

## Event normalization

Read the already materialized source-specific tables, not the public tables
again:

```text
external_transactions_20220301_20220901
token_transfers_20220301_20220901
internal_traces_20220301_20220901
```

For each source retain only the columns needed for aggregation:

```text
event_family, block_timestamp, block_number, transaction_index,
transaction_hash, event_index/trace identity, from_address, to_address,
from_exgraph_node_id, to_exgraph_node_id, value/value_lossless,
quantity, token_contract_address, token_id, trace_type/call_type
```

Use a family-specific event key.  A native transaction key is
`(event_family, transaction_hash)`, a token key is
`(event_family, transaction_hash, event_index)`, and an internal-trace key
must include the trace identity/path.  Do not deduplicate different families
merely because `transaction_hash` is equal.  Preserve both wallet roles:
`from_wallet` contributes an outgoing event and `to_wallet` contributes an
incoming event.  An unmapped counterparty remains a valid counterparty token
for wallet-level counts; mapped-node network features get a separate coverage
flag.

## Exact as-of intervals

For cutoff `t`, every discovery feature uses one of these half-open intervals:

| family | interval | purpose |
|---|---|---|
| `w_1h` | `[t-1h,t)` | very short burst/activity |
| `w_6h` | `[t-6h,t)` | intraday activity |
| `w_1d` | `[t-1d,t)` | daily burst and event composition |
| `w_7d` | `[t-7d,t)` | score/novelty/rapid-forward |
| `w_30d` | `[t-30d,t)` | primary history and graph state |
| `w_30d_prior` | `[t-30d,t-7d)` | baseline for 7-day change |

All joins use `block_timestamp < t` on the feature side.  The feature CTAS
must retain `coverage_event_count` and `coverage_last_timestamp` so that zero
activity is distinguishable from missing extraction.

## Feature columns

### Activity

```text
tx_count_1h, tx_count_6h, tx_count_1d, tx_count_7d, tx_count_30d
active_days_30d, active_hours_1d, first_event_age_30d, last_event_recency
inter_event_mean/median/std/max_gap_30d
burstiness_1d, burstiness_7d, burstiness_30d
```

Use event-key counts for `tx_count` and event-row counts separately.  Inter-event
statistics require the event timestamp and are not recoverable from OW-009's
day-level CSV.

### Flow and amount

```text
native_in/out/count/sum/median/max_30d
token_in/out/count/quantity_sum_30d
net_native_flow_30d, inflow_outflow_ratio_30d
flow_conservation_ratio_7d/30d
```

Keep native values and token quantities separate; never add their raw numeric
scales.  USD conversion, if later added, must use an as-of price join and a
separate coverage flag.

### Counterparty

```text
unique_counterparties_1d/7d/30d
new_counterparties_7d_vs_prior23d
new_counterparty_rate_7d_vs_prior23d
repeat_counterparty_rate_7d/30d
counterparty_entropy_7d/30d
counterparty_growth_7d_vs_prior23d
```

The novelty set is `CP([t-7d,t)) - CP([t-30d,t-7d))`.  The denominator and
zero-activity convention must be fixed before scoring.

### Temporal structure

```text
reciprocal_counterparties_7d/30d
reciprocity_rate_7d/30d
rapid_forward_count_1d/7d
fan_in_max_1d/7d, fan_out_max_1d/7d
cycle2_proxy_7d/30d
split_merge_count_7d/30d
```

Define rapid forwarding using timestamped directed events and a fixed interval
(e.g. a source wallet receives an event and sends an outgoing event within
`[0,24h]`; the exact event-pair semantics must be frozen before execution).
Define fan-in/out and split/merge on fixed calendar-day and transaction-event
windows.  These cannot be reconstructed from day-level `weight` alone.

### Event composition

```text
native_event_ratio_7d/30d
token_event_ratio_7d/30d
internal_trace_event_ratio_7d/30d
token_contract_count_7d/30d
token_id_count_7d/30d
```

These require the source event family and token/trace identity.  Internal
traces remain part of discovery coverage even if a later label protocol excludes
them from future-counterparty labels.

### Network (mapped-counterparty subset only)

```text
temporal_in_degree_30d, temporal_out_degree_30d
weighted_temporal_degree_30d
local_density_30d, bridge_proxy_30d
mapped_counterparty_fraction_30d
```

Build these from a cutoff-specific graph over `[t-30d,t)`.  Do not use the full
static `ethereum_graph.gpickle` or future cumulative degree.  Network columns
must be nullable with explicit coverage flags so they do not define the wallet
population.

## Separate future outcomes

Create `openworld_future_outcomes_v2` only after the feature table is frozen.
For each `(wallet, t)` use:

```text
future_7d:  [t,t+7d)
future_30d: [t,t+30d)
```

Store `future_active_days`, `future_events`, `future_new_counterparties`,
`future_reciprocity`, and any open-world outcome flags here.  This table is
`evaluation_only`; it must never be used for discovery eligibility, feature
normalization, threshold selection, matching, or model selection.

## Cost and audit guard

1. Dry-run every CTAS with a bounded `maximumBytesBilled`.
2. Materialize/filter in BigQuery and return only the wallet×cutoff table plus
   compact coverage summaries.
3. Record source table versions, SQL hashes, row counts, bytes processed/billed,
   and the exact cutoff/window predicates.
4. Validate metadata and run a bounded `COUNT(*)`/`GROUP BY cutoff_time` query
   before accepting the table.
