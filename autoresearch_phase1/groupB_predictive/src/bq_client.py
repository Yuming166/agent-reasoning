"""Bounded BigQuery client helper for Group B (Predictive-Influence-First).

Mirrors the Group 0/1 environment: google.cloud.bigquery through the local
proxy + ADC; every query capped by maximum_bytes_billed and partition-filtered.
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
    max_bytes_billed: int = 3 * 1024**3,
    client: bigquery.Client | None = None,
) -> list[dict]:
    if client is None:
        client = get_client()
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes_billed),
    )
    rows = list(job.result())
    print(f"[bq] bytesBilled={job.total_bytes_billed} cache={job.cache_hit} rows={len(rows)}", flush=True)
    return [dict(r) for r in rows]
