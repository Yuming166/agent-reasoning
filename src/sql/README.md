# SQL templates

`extract_target_transactions_bigquery.sql` is a draft Standard SQL template for
extracting only transactions touching the 27,613 unique EX-Graph-mapped wallet
addresses. It is intentionally not executed locally because it needs a Google
Cloud/BigQuery project and the current public table schema.

Keep `external_tx`, `token_transfer`, and `internal_trace` as separate event
families until their deduplication and prediction-label semantics are fixed.

## Jump-host traffic and query-cost rules

BigQuery reads/scans the public table on the service side. The jump host does not
receive the scanned source table unless the client explicitly downloads query
rows. Prefer the following pattern:

1. dry-run the query and inspect `totalBytesProcessed`;
2. set a maximum-bytes-billed guard;
3. use `CREATE TABLE AS SELECT` or a destination table in BigQuery;
4. use `EXPORT DATA` to a Cloud Storage bucket, then download only the filtered,
   compressed result if local training is required;
5. never run a wide `SELECT *` and stream the result to stdout on the jump host.

For this project, split outgoing (`from_address IN target_addresses`) and
incoming (`to_address IN target_addresses`) extraction when possible. Keep all
counterparties in the result; filtering both endpoints to the mapped-address
set would invalidate the counterparty-prediction task.

`validate_exgraph_address_coverage_bigquery.sql` is a count-only validation
query. Run it before exporting events. It measures the fraction of mapped
addresses observed in the same historical window through external transactions
and token transfers; it prevents us from assuming that all mapping rows are
active in the selected source/window.
