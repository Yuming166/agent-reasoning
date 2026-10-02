"""Bounded BigQuery client for Group C (same pattern as Group A / audit).

Read-only queries through the local proxy + ADC; every query capped by
maximum_bytes_billed and partition-filtered (see sql/edges_asof.sql).
"""
from __future__ import annotations

import os

from google.cloud import bigquery

PROXY = "http://10.63.0.72:7890"
CREDS = "/home/gaoym/.config/gcloud/application_default_credentials.json"


def get_client(project: str = "ictdata-507912") -> bigquery.Client:
    env = {
        **os.environ,
        "HTTPS_PROXY": PROXY, "HTTP_PROXY": PROXY,
        "https_proxy": PROXY, "http_proxy": PROXY,
        "GOOGLE_APPLICATION_CREDENTIALS": CREDS,
    }
    os.environ.update(env)
    return bigquery.Client(project=project)


def run_bounded_query(sql: str, max_bytes_billed: int) -> list[dict]:
    client = get_client()
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=max_bytes_billed))
    rows = list(job.result())
    print(f"[bq] bytesBilled={job.total_bytes_billed} cache={job.cache_hit} "
          f"rows={len(rows)}", flush=True)
    return [dict(r) for r in rows]
