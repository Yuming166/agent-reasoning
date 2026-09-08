# Data access and reproduction

This repository intentionally contains **code, small manifests, the EX-Graph
address mapping CSV, and audit results**, but not the 11.6 GB EX-Graph graph
pickle or the multi-gigabyte BigQuery event tables.

## Existing materialization

The validated six-month materialization used during development is in the US
BigQuery dataset:

```text
ictdata-507912.exgraph
```

Tables:

```text
external_transactions_20220301_20220901
token_transfers_20220301_20220901
internal_traces_20220301_20220901
target_events_20220301_20220901           # UNION ALL view
exgraph_x_matches_v1                      # official address-to-X match dimension
target_event_sequences_20220301_20220901  # directional target/counterparty roles
nc_ranker_samples_v2                     # sampled candidate-ranker pilot (top-2000 negatives)
```

Each event row has at least one endpoint matching the EX-Graph address list.
The other endpoint is retained so that counterparty prediction is not limited
to mapped-to-mapped edges.

If you are a collaborator with access to that dataset, query with a time
predicate because the materialized tables require partition filters:

```sql
SELECT event_family, block_timestamp, transaction_hash,
       from_address, to_address,
       from_exgraph_node_id, to_exgraph_node_id
FROM `ictdata-507912.exgraph.target_events_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
  AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
LIMIT 100;
```

The dataset owner can grant dataset-level `BigQuery Data Viewer` access. The
query runner also needs permission to create jobs in the billing project used
for the query. Use your own billing project when possible.

`nc_ranker_samples_v2` is a 28,472,717-row pilot table for diagnosing candidate
learning. It is intentionally support-biased: deterministic sampled negatives
come from each month's historical global top-2000 addresses, while positives
outside that support retain `g_rank=99999`. Use `evaluate_supported_pool.py`
for comparable support-conditional metrics; do not interpret the naive
sampled-pool classifier accuracy/MRR as full-candidate performance.

## Reproduce in your own Google Cloud project

1. Enable BigQuery and configure billing for your project.
2. Authenticate Application Default Credentials, for example with
   `gcloud auth application-default login`.
3. Install dependencies:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Upload the checked-in address mapping and run the bounded dry-run:

   ```bash
   python src/run_google_coverage_validation.py \
     --project-id YOUR_PROJECT_ID \
     --target-csv data/metadata/target_addresses.csv \
     --start 2022-03-01 \
     --end 2022-09-01 \
     --output artifacts/coverage.json
   ```

5. Materialize native transactions and token transfers:

   ```bash
   python src/prepare_google_event_tables.py \
     --project-id YOUR_PROJECT_ID \
     --dataset-id exgraph \
     --target-table target_addresses \
     --start 2022-03-01 \
     --end 2022-09-01 \
     --output artifacts/event_prep.json
   ```

6. Materialize internal traces with the larger guard after reviewing the
   dry-run estimate:

   ```bash
   python src/prepare_google_trace_table.py \
     --project-id YOUR_PROJECT_ID \
     --dataset-id exgraph \
     --target-table target_addresses \
     --start 2022-03-01 \
     --end 2022-09-01 \
     --output artifacts/trace_prep.json
   ```

7. Create the official match dimension and the directional sequence table:

   ```bash
   python src/create_exgraph_sequence_tables.py \
     --project-id YOUR_PROJECT_ID \
     --dataset-id exgraph \
     --output artifacts/sequence_tables.json
   ```

   The SQL is pinned to the development project in the checked-in file; edit
   `src/sql/create_exgraph_sequence_tables_ictdata.sql` before using another
   namespace.

8. Create the portable unified view:

   ```bash
   python src/create_target_events_view.py \
     --project-id YOUR_PROJECT_ID \
     --dataset-id exgraph \
     --start 2022-03-01 \
     --end 2022-09-01 \
     --output artifacts/unified_view.json
   ```

The scripts use the Google BigQuery REST API through Application Default
Credentials and do not stream the public Ethereum source rows through the
client machine. They materialize results in BigQuery. Review every dry-run
estimate and keep `--max-bytes-billed` guards in place.

## Data not redistributed here

- `ethereum_graph.gpickle` is intentionally omitted because it is about
  11.6 GB and its upstream data licensing should be checked before mirroring.
  Its source commit, size, observed structure, and SHA-256 are recorded under
  `data/metadata/`.
- The Crypto Influencer raw files are omitted. The repository records the
  dataset identifier, version, observed schema/time range, and checksums, but
  users must obtain it under its own terms.
- The BigQuery event tables are not exported into Git. Use the existing shared
  dataset or reproduce them in your own project.
