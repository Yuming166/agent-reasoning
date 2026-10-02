# OW-010B Data QA

## Pre-result freeze checks

- Source discovery table: `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`.
- Source evaluation table: `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`.
- The feature table schema was rechecked against the 70-column OW-010A contract on 2026-09-18.
- The future table schema was rechecked against the 25-column OW-010A contract on 2026-09-18.
- The expected discovery grid is 82,839 rows and 27,613 distinct anchors across three cutoffs.
- The future table is physically separate, `evaluation_only = TRUE`, and `data_role = EVALUATION_ONLY`.
- The score7 aggregate is 47,575 history-eligible wallet-cutoff rows with family and direction counts only; it is computed as an as-of aggregate from the event table and exports no raw events.
- The pre-result amendment records why this compact score7 aggregate was needed: the v1 feature table has only the external/native 7-day family count, not independent token/internal 7-day counts.
- No raw event table is exported by the OW-010B input fetcher.
- No external label source is queried, loaded, inspected, or sent to Astra6.

## Required executable checks

The input fetcher and analysis runner must verify:

1. exactly one feature row per `(anchor_wallet, cutoff_time)`;
2. exactly one outcome row per `(anchor_wallet, cutoff_time)`;
3. feature/outcome key sets match without row multiplication;
4. cutoff timestamps are exactly the three preregistered UTC values;
5. all discovery status values are `DISCOVERY_ONLY` and all outcome status values are `EVALUATION_ONLY`;
6. history and score boundaries are before the cutoff;
7. `history_event_count_30d >= 1` counts agree with the OW-010A population audit;
8. future 7-day and 30-day coverage statuses are reported by cutoff before evaluation;
9. no feature column contains an address/identifier except join/audit keys;
10. all deterministic transformed features and targets are finite after the declared missingness procedure;
11. no target, scaler, imputer, feature selection, or threshold uses August values before frozen test evaluation;
12. prediction rows remain keyed to the same wallet-cutoff rows across M0/M1/M2.

## QA failure policy

A failed critical check blocks interpretation. Fixes require a logged preregistration amendment before the affected result is inspected. A data-quality repair is not a model optimization.
