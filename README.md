# EX-Graph microtransaction analysis

Reproducible preparation and audit code for joining EX-Graph-mapped Ethereum
addresses with temporal Ethereum events. The repository is designed to keep
large/raw data outside Git while preserving the code, schemas, manifests,
checksums, and bounded validation results needed to reproduce the workflow.

## What is included

- EX-Graph graph and temporal-dataset audits under `src/` and `notes/`.
- The 27,613-address mapping used as the target whitelist at
  `data/metadata/target_addresses.csv`.
- BigQuery SQL and Python scripts for address upload, overlap validation,
  six-month event-table materialization, quality checks, and the unified view.
- Small JSON execution manifests and audit summaries under `artifacts/`.
- Data provenance, checksums, and third-party notices.

## What is intentionally not included

The raw 11.6 GB `ethereum_graph.gpickle`, raw Crypto Influencer files, Python
virtual environment, and BigQuery event tables are not part of this GitHub
repository. See [`DATA_ACCESS.md`](DATA_ACCESS.md) for shared-table access and
reproduction in another Google Cloud project.

## Validated six-month preparation

The development materialization covers **2022-03-01 (inclusive) through
2022-09-01 (exclusive), UTC** and uses 27,613 EX-Graph-mapped addresses. The
validated outputs in BigQuery contain:

| Event family | Rows |
|---|---:|
| Native transactions | 2,877,009 |
| Token transfers | 4,275,544 |
| Internal traces | 4,478,515 |
| **Total** | **11,631,068** |

Rows are retained when at least one endpoint matches the EX-Graph address set;
the other counterparty endpoint is intentionally preserved. The unified view
uses `UNION ALL` and does not deduplicate by `transaction_hash`.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Then follow [`DATA_ACCESS.md`](DATA_ACCESS.md). The BigQuery scripts require a
Google Cloud project with BigQuery enabled, Application Default Credentials,
and a reviewed billing/bytes-billed guard.

## Important audit boundary

The currently downloadable EX-Graph graph binary was observed as an aggregated
NetworkX `DiGraph` rather than a transaction-level event stream. It therefore
cannot by itself recover transaction ordering or faithfully represent repeated
parallel transactions between the same ordered address pair. The temporal
prediction workflow uses the filtered BigQuery event tables instead.

## Status

This repository publishes the completed data-preparation and audit scope. It
does not claim that the downstream transaction-object prediction model or
trading effectiveness has been established.
