# OW-010A Missingness Policy

No global `fillna(0)` is permitted. The following semantics are used:

- `TRUE_ZERO`: a fully observed window contains no events/countable counterparties. Explicit count fields may be zero.
- `OBSERVED_ACTIVITY`: the window contains at least one event.
- `NOT_APPLICABLE`: a statistic has no meaningful denominator, e.g. native amount when there are no native events or an inter-event gap with fewer than two events.
- `UNSUPPORTED`: the current representation cannot faithfully define the feature, e.g. higher-order temporal cycles.
- `UNSUPPORTED_CROSS_ASSET_AGGREGATION`: token quantity is retained but not economically aggregated across contracts.
- `EXTRACTION_FAILURE`: reserved for a source/materialization error; none was observed in the completed QA.

The v1 discovery table explicitly records `history_activity_status`, `score_activity_status`, `history_window_coverage_status`, `native_amount_status`, `token_quantity_status`, `temporal_cycle_status`, and `split_merge_status`. Missing-rate CSVs distinguish a structural N/A from a source failure; a null statistic is not silently converted to a zero.
