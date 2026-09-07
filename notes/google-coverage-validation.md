# Google Blockchain Analytics overlap validation

**Run date:** 2026-09-07

## Scope

- Billing/query project: `ictdata-507912`
- Local staging dataset/table: `ictdata-507912.exgraph.target_addresses`
- Loaded rows: 27,613 (the de-duplicated EX-Graph Ethereum-address mapping)
- Public source: `bigquery-public-data.goog_blockchain_ethereum_mainnet_us`
- Window: `[2022-03-01 00:00:00 UTC, 2022-09-01 00:00:00 UTC)`
- Event families checked: native/external transactions and token-transfer events

The check is **count-only**. The public source rows were scanned inside
BigQuery; they were not streamed to the jump host.

## Result

| Measure | Count | Share of 27,613 targets |
|---|---:|---:|
| EX-Graph target addresses | 27,613 | 100.00% |
| Observed in native/external transactions | 20,969 | 75.94% |
| Observed in token transfers | 19,940 | 72.21% |
| Observed in either source | 21,421 | **77.58%** |
| Not observed in either source | 6,192 | 22.42% |

“Observed” means that the lower-cased address appeared as either
`from_address` or `to_address` in at least one event in the selected window.
It does not yet assert that every address has an influencer identity, nor that
an observed address is economically active in the same sense as the EX-Graph
edge weight.

## Query and transfer accounting

- Dry-run estimate: 38,836,926,968 bytes processed.
- Actual query: 38,836,926,968 bytes processed and 38,837,157,888 bytes billed.
- Local CSV uploaded to BigQuery: 1,412,793 bytes; 27,613 rows.
- Result artifact: `artifacts/google_exgraph_address_coverage_2022-03_2022-09.json`
- Reproducible runner: `src/run_google_coverage_validation.py`
- BigQuery job ID: `job_k6p1rUbE3P7X6Wstzfc2cezzyveG`

The public views currently expose `transactions.transaction_hash` and
`token_transfers.event_index`, `token_transfers.address`, and
`token_transfers.quantity`; the SQL extraction template was updated to match
that schema on this run.

## Decision

This six-month pilot gives a sufficiently large address overlap to proceed with
an event-level extraction experiment: roughly three quarters of the mapped
cohort is observed, and the union reaches 21,421 addresses. It supports using
Google Blockchain Analytics as the temporal transaction source for this
cohort, but it is not a guarantee of full coverage or a guarantee that the
remaining 6,192 addresses are inactive.

Next step should be a bounded extraction of event rows for the 21,421 observed
addresses (or a one-year coverage check first), while retaining transaction
hash, block timestamp/number, transaction index, event index, endpoints, and
contract/quantity fields. Keep external transactions and token transfers as
separate event families until their labels and deduplication policy are fixed.
