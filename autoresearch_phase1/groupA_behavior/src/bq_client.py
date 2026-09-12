"""Bounded BigQuery client helper for Group A.

Uses google.cloud.bigquery through the local proxy + ADC, mirrors the
environment documented in notes/embed-server-and-bigquery-client-20260911.md.
Every query is capped by maximum_bytes_billed and should include partition
filters; no full-table exports. Keeps only query results (metadata/aggregates).
"""
from __future__ import annotations

import os

from google.cloud import bigquery

PROXY = "http://10.63.0.72:7890"
CREDS = "/home/gaoym/.config/gcloud/application_default_credentials.json"


def get_client(project: str = "ictdata-507912") -> bigquery.Client:
    env = {
        **os.environ,
        "HTTPS_PROXY": PROXY,
        "HTTP_PROXY": PROXY,
        "https_proxy": PROXY,
        "http_proxy": PROXY,
        "GOOGLE_APPLICATION_CREDENTIALS": CREDS,
    }
    os.environ.update(env)
    return bigquery.Client(project=project)


def run_bounded_query(
    sql: str,
    max_bytes_billed: int,
    client: bigquery.Client | None = None,
) -> list[dict]:
    """Run a bounded query and return rows as dicts, printing bytes billed."""
    if client is None:
        client = get_client()
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes_billed),
    )
    rows = list(job.result())
    tb = job.total_bytes_billed
    print(f"[bq] bytesBilled={tb} cache={job.cache_hit} rows={len(rows)}", flush=True)
    return [dict(r) for r in rows]
