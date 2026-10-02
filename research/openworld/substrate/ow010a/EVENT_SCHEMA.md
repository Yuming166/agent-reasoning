# OW-010A Event Schema

## Sources

- `ictdata-507912.exgraph.external_transactions_20220301_20220901`
- `ictdata-507912.exgraph.token_transfers_20220301_20220901`
- `ictdata-507912.exgraph.internal_traces_20220301_20220901`
- unified view: `target_events_20220301_20220901`
- mapping: `exgraph_x_matches_v1`

Observed source rows are 2,877,009 external transactions, 4,275,544 token transfers, and 4,478,515 internal traces.

## Anchor event table

`openworld_anchor_events_v1` is partitioned by `DATE(event_timestamp)` and clustered by `(anchor_wallet, event_family, counterparty_identity)`. Important fields are:

| field | type | meaning |
|---|---|---|
| `anchor_wallet` | STRING | mapped wallet used as observational anchor |
| `anchor_exgraph_node_id` | INT64 | EX-Graph node for anchor |
| `counterparty_address` | STRING | opposite endpoint, nullable |
| `counterparty_exgraph_node_id` | INT64 | mapped node when available, nullable |
| `counterparty_identity` | STRING | `mapped_node:<id>` or `unmapped_address:<address>` |
| `counterparty_is_exgraph_mapped` | BOOL | mapping status of counterparty |
| `direction` | STRING | `incoming`, `outgoing`, or `self` |
| `event_family` | STRING | `external_tx`, `token_transfer`, `internal_trace` |
| `event_timestamp` | TIMESTAMP | sub-day event time |
| `block_number`, `transaction_index`, `event_index` | INT64 | deterministic ordering components |
| `transaction_hash` | STRING | transaction identity component |
| `trace_address_json` | STRING | internal trace path |
| `event_identity` | STRING | source semantic identity |
| `anchor_event_identity` | STRING | source identity plus anchor/direction |
| `identity_collision_flag` | BOOL | same semantic identity had differing full-row variants |
| `native_value`, `native_value_lossless` | BIGNUMERIC/STRING | native amount, lossless representation |
| `token_quantity`, `token_contract_address`, `token_id` | STRING | token fields retained without cross-asset aggregation |
| `trace_type`, `subtrace_count`, `call_type`, `removed`, `error` | mixed | internal/token event metadata |

No source event rows are exported locally.

## Feature and outcome tables

The feature table has 70 columns including counts, direction, composition, counterparties, entropy, inter-event statistics, burstiness proxies, status fields, and `feature_version`. The outcome table has 25 columns and is evaluation-only. Exact BigQuery schemas are recorded in the materialization manifests and can be rechecked with `INFORMATION_SCHEMA.COLUMNS`.
