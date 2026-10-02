#!/usr/bin/env python3
"""Bounded BigQuery audit runner (Group 0, Phase I).

Reads SQL from stdin or first argument; runs with a hard maximum_bytes_billed
guard; prints job id, bytes billed, cache flag, schema, and rows as TSV.
Uses google.cloud.bigquery with ADC through the jump-host proxy.

Usage:
  echo "SELECT 1" | python audit_query.py [--max-bytes-billed 500000000] [--dry]
"""
import argparse, json, os, sys

from google.cloud import bigquery

PROJECT = "ictdata-507912"
DATASET = "exgraph"
DEFAULT_MAX_BYTES = 200_000_000  # 200 MB guard per query by default

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql_file", nargs="?", help="SQL file; defaults to stdin")
    ap.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max-rows", type=int, default=1000)
    args = ap.parse_args()
    sql = open(args.sql_file).read() if args.sql_file else sys.stdin.read()

    client = bigquery.Client(project=PROJECT, default_query_job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=args.max_bytes_billed,
        use_legacy_sql=False,
        dry_run=args.dry,
    ))
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=args.max_bytes_billed,
                                  use_legacy_sql=False, dry_run=args.dry)
    job = client.query(sql, job_config=cfg)
    if args.dry:
        print(f"dryrun OK estimated_bytes={job.total_bytes_processed} billed={job.total_bytes_billed}")
        return
    rows = list(job.result(max_results=args.max_rows))
    stats = job.query_plan  # not used
    print(f"# job_id={job.job_id}", file=sys.stderr)
    print(f"# bytes_processed={job.total_bytes_processed}", file=sys.stderr)
    print(f"# bytes_billed={job.total_bytes_billed}", file=sys.stderr)
    print(f"# cache_hit={job.cache_hit}", file=sys.stderr)
    print(f"# num_rows_returned={len(rows)}", file=sys.stderr)
    if rows:
        cols = list(rows[0].keys())
        print("\t".join(cols))
        for r in rows:
            print("\t".join("" if v is None else str(v) for v in r.values()))

if __name__ == "__main__":
    main()
