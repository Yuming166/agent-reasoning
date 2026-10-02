# OW-010A: Event-Level As-Of Substrate Reconstruction

**Execution date:** 2026-09-18  
**Scope:** substrate reconstruction and audit only.

This run implements the event-level, leakage-safe substrate described by `OW-010A_Event_Level_AsOf_Substrate_Reconstruction.md`. It does **not** start OW-010B, change OW-009's detector, tune thresholds, inspect EX-Graph wash labels, generate pseudo-labels, or build a new GNN.

## Result

`SUBSTRATE_READY_FOR_OW010B`: the event substrate, discovery/future separation, population audit, identity audit, missingness policy, and leakage QA are complete. OW-010B is **not** started. Exact OW-009 reciprocity-change parity remains a declared feature-freeze item for the next stage, not a reason to conflate this substrate with an effectiveness result.

## BigQuery tables

- `ictdata-507912.exgraph.openworld_anchor_events_v1`: event-level anchor expansion, 11,835,499 rows, 21,469 observed anchors; unmapped counterparties retained.
- `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`: 27,613 anchors × 3 cutoffs = 82,839 discovery rows.
- `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`: 82,839 evaluation-only rows, physically separate.

## Key population counts

|cutoff|mapped anchors|observed pre-cutoff|history >=1|history >=3|history >=10|history >=20|
|---|---|---|---|---|---|---|
|2022-06-01|27613|20461|17156|15647|13130|11013|
|2022-07-01|27613|20818|15736|14212|11469|9172|
|2022-08-01|27613|21123|14683|13020|10294|8222|


The old local OW-009 strict candidate counts remain 370 / 282 / 359 and are preserved as a comparison only; they are not overwritten or relabeled as the event-level discovery cohort.

## Files

- `EVENT_SCHEMA.md`, `EVENT_IDENTITY_POLICY.md`: event contract and identity/dedup rules.
- `DATA_CONTRACT.md`, `MISSINGNESS_POLICY.md`: as-of windows and explicit missingness semantics.
- `POPULATION_AUDIT.md`, `QA_REPORT.md`, `OW010A_FINAL_REPORT.md`: findings and decisions.
- `BIGQUERY_MATERIALIZATION.md`, `BIGQUERY_FEATURE_SPEC.md`: materialization specification.
- `sql/00_source_audit.sql` through `sql/05_population_summary.sql`: executable SQL.
- `results/`: compact summaries and BigQuery job manifests; no raw event rows were downloaded.
