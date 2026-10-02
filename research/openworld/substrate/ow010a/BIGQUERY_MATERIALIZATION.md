# OW-010A BigQuery Materialization

## Tables

### 1. `openworld_anchor_events_v1`

Source: the unified target-events view. The query expands every target-touching event into anchor rows, retains unmapped counterparties, preserves source fields and sub-day ordering, applies family-specific identity/deduplication, and flags collisions.

### 2. `openworld_wallet_cutoff_features_v1`

Grain: `(anchor_wallet, cutoff_time)`. It is an outer grid over all mapped anchors and the three cutoffs. The only event join is `event_timestamp < cutoff_time`, with history `[t-30d,t)`. It includes activity, flow, family composition, counterparty, temporal-order, reciprocal-pair counts, rapid-forwarding adjacent proxy, fan-in/fan-out proxy, and explicit status fields.

### 3. `openworld_wallet_cutoff_future_outcomes_v1`

Grain: `(anchor_wallet, cutoff_time)`. It computes future activity and future counterparty outcomes in `[t,t+7d)` and `[t,t+30d)`, including new counterparties relative to the pre-cutoff 30-day history. It is marked `evaluation_only=TRUE` and is not referenced by the discovery query.

## Cost evidence

| query | job id | bytes processed | bytes billed |
|---|---|---:|---:|
| source audit | `job_c1dN0Ytvul5ZueYnDSd39WQuxD9F` | 2,864,416,975 | 2,864,709,632 |
| event identity audit | `job_Z9trYqX7EQ5Zk-FDqKBtNEq-KFW_` | 2,864,416,975 | 2,864,709,632 |
| anchor events CTAS | `job_jJTsEUoG6OEfg0KNOhTdB7GiCo9J` | 3,124,491,755 | 3,124,756,480 |
| discovery features CTAS | `job_f19tdkLAoUUQkRCUHkSIRdFyylzk` | 4,739,749,254 | 4,740,612,096 |
| future outcomes CTAS | `job_HEl6AsFFPtrtk9wSVVVeRP0ZQr3I` | 2,001,228,347 | 2,001,731,584 |

All jobs used maximum-bytes guards. Only compact aggregate outputs were downloaded; no full raw transaction table was exported.
