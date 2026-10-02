# OW-010A Data Contract

## Observational unit

The intended unit is exactly `(anchor_wallet, cutoff_time)`, where `anchor_wallet` is one of the 27,613 EX-Graph-mapped Ethereum addresses and `cutoff_time` is one of:

- 2022-06-01 00:00:00 UTC
- 2022-07-01 00:00:00 UTC
- 2022-08-01 00:00:00 UTC

The discovery table retains the full 27,613 × 3 grid. It does not require a wallet to have activity in every window.

## Intervals

All intervals are half-open and UTC: 

- history: `[t-30d, t)`
- prior-history component: `[t-30d, t-7d)`
- score-history component: `[t-7d, t)`
- evaluation outcome: `[t, t+7d)` and `[t, t+30d)`

For all discovery features, the maximum permitted event timestamp is strictly less than `cutoff_time`.

## Role semantics

An event touching two mapped endpoints is expanded into two anchor rows: outgoing for the source anchor and incoming for the destination anchor. Self events are represented once with `direction=self`. The counterparty may be unmapped or absent; that is not an anchor eligibility failure.

## Discovery/evaluation separation

`openworld_wallet_cutoff_features_v1` contains discovery-only fields and `data_role=DISCOVERY_ONLY`. `openworld_wallet_cutoff_future_outcomes_v1` contains future metrics and `evaluation_only=TRUE`. The latter is never used by discovery eligibility, normalization, scoring, ranking, or matching.
