#!/usr/bin/env python3
"""Build the frozen September temporal-holdout panel without mutating v1.

The June cheap ranker and June budget router are later applied unchanged.  The
September event sample is generated natively from the Mar-Sep sequence view so
that cp_type uses the same event-specific prior-90d definition as nc_events_v1.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import build_llm_panel as base  # noqa: E402

SNAP = "2022-09-01"
SEQ = "`ictdata-507912.exgraph.target_event_sequences_20220301_20221001`"
ASOF = "`ictdata-507912.exgraph.wallet_asof_features_20220901`"
EVENT_TABLE = "llm_panel_events_20220901"
CAND_TABLE = "llm_panel_candidates_20220901"
GCS_PREFIX = "llm_panel_20220901/"
DEST = "artifacts/llm_panel_20220901"


OLD_TABLE = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
SEP_TABLE = "`ictdata-507912.exgraph.target_event_sequences_20220901_20221001`"
TH_LIT = "TIMESTAMP('2022-06-03 00:00:00+00:00')"
T0_LIT = "TIMESTAMP('2022-09-01 00:00:00+00:00')"
T1_LIT = "TIMESTAMP('2022-10-01 00:00:00+00:00')"


COMMON_COLS = """
  target_sequence_index,target_exgraph_node_id,target_address,target_match_status,target_is_x_matched,
  counterparty_exgraph_node_id,counterparty_address,counterparty_match_status,
  counterparty_is_x_matched,counterparty_present,both_endpoints_are_x_matched,
  direction,self_transaction,sequence_role,event_family,event_family_order,
  block_timestamp,block_number,transaction_index,event_index,transaction_hash,
  from_address,to_address,value,token_contract_address,token_id,quantity,removed,
  trace_type,subtrace_count,call_type,error,
  source_from_exgraph_node_id,source_to_exgraph_node_id,
  touches_target_from,touches_target_to"""


def old_pre_source():
    return f"""(
  SELECT {COMMON_COLS} FROM {OLD_TABLE}
  WHERE block_timestamp >= {TH_LIT}
    AND block_timestamp <  {T0_LIT}
)"""


def full_native_source():
    return f"""((
  SELECT {COMMON_COLS} FROM {OLD_TABLE}
  WHERE block_timestamp >= {TH_LIT}
    AND block_timestamp <  {T0_LIT}
  UNION ALL
  SELECT {COMMON_COLS} FROM {SEP_TABLE}
  WHERE block_timestamp >= {T0_LIT}
    AND block_timestamp <  {T1_LIT}
))"""


def literal_window(sql):
    """Rewrite logical-view refs to physical tables that satisfy required filters."""
    pre_pattern = (
        f"FROM {SEQ}, params p\n"
        "  WHERE block_timestamp >= p.th AND block_timestamp < p.t0"
    )
    pre_replacement = f"FROM {old_pre_source()} AS src, params p\n  WHERE 1=1"
    sql = sql.replace(pre_pattern, pre_replacement)

    native_pattern = f"""FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP('2022-06-03 00:00:00+00:00')
    AND block_timestamp <  TIMESTAMP('2022-10-01 00:00:00+00:00')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction"""
    native_replacement = f"""FROM {full_native_source()} AS src
  WHERE sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction"""
    sql = sql.replace(native_pattern, native_replacement)

    if SEQ in sql:
        raise RuntimeError("unrewritten logical view reference")
    return sql

def ctas(select_sql, table):
    return (f"CREATE OR REPLACE TABLE `{base.PROJECT}.{base.DATASET}.{table}`\n"
            "PARTITION BY snapshot_date\nCLUSTER BY target_address AS\n"
            f"SELECT * FROM ({select_sql})")


def verify(op, tok):
    queries = {
        "events": f"""
            SELECT snapshot_date, cp_type, stratum, activity,
                   COUNT(*) n, ROUND(AVG(pop_weight), 5) avg_pop_weight,
                   ROUND(AVG(truth_g_rank),1) avg_truth_rank,
                   MIN(truth_g_rank) min_rank, MAX(truth_g_rank) max_rank
            FROM `{base.PROJECT}.{base.DATASET}.{EVENT_TABLE}`
            GROUP BY 1,2,3,4 ORDER BY 2,3,4""",
        "pools": f"""
            SELECT c.snapshot_date, COUNT(DISTINCT FORMAT('%t', c)) AS should_not_use,
                   COUNT(*) AS cand_rows,
                   COUNT(DISTINCT CONCAT(CAST(c.target_sequence_index AS STRING),'|',c.target_address)) AS events,
                   ROUND(COUNT(*)*1.0/COUNT(DISTINCT CONCAT(CAST(c.target_sequence_index AS STRING),'|',c.target_address)),2) avg_pool,
                   SUM(c.label) positives,
                   APPROX_QUANTILES(COUNT(*), 100)[OFFSET(50)] AS placeholder
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}` c
            GROUP BY 1""",
        "pool_distribution": f"""
            WITH p AS (
              SELECT target_address,target_sequence_index,COUNT(*) n,
                     SUM(label) labels,
                     COUNT(DISTINCT candidate_address) distinct_candidates
              FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}`
              GROUP BY 1,2)
            SELECT MIN(n) min_n, APPROX_QUANTILES(n,100)[OFFSET(50)] median_n,
                   MAX(n) max_n, COUNTIF(labels<>1) bad_positive_events,
                   COUNTIF(distinct_candidates<>n) duplicate_events, COUNT(*) events
            FROM p""",
        "positive_join": f"""
            SELECT COUNT(*) total,
                   SUM(IF(c.candidate_address=e.counterparty_address,1,0)) matching_positives,
                   SUM(IF(c.label=1,1,0)) label_rows
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}` c
            JOIN `{base.PROJECT}.{base.DATASET}.{EVENT_TABLE}` e
              ON e.snapshot_date=c.snapshot_date AND e.target_address=c.target_address
             AND e.target_sequence_index=c.target_sequence_index
            WHERE c.label=1""",
        "sources": f"""
            SELECT cand_source, COUNT(*) n, ROUND(AVG(g_rank),1) avg_g_rank,
                   COUNTIF(g_rank=99999) sentinel_rows
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}`
            GROUP BY 1 ORDER BY 1""",
        "new_tail_support": f"""
            SELECT e.stratum, COUNT(*) events,
                   COUNTIF(EXISTS(
                     SELECT 1 FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}` c
                     WHERE c.snapshot_date=e.snapshot_date AND c.target_address=e.target_address
                       AND c.target_sequence_index=e.target_sequence_index
                       AND c.cand_source='new_tail')) events_with_tail_neg
            FROM `{base.PROJECT}.{base.DATASET}.{EVENT_TABLE}` e
            WHERE e.cp_type='new'
            GROUP BY 1""",
        "temporal_negative_audit": f"""
            SELECT COUNT(*) post_snapshot_features
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}`
            WHERE days_since < 0""",
        "unknown_negative_balance": f"""
            WITH e AS (
              SELECT target_address,target_sequence_index,
                     MAX(IF(label=1 AND g_rank=99999,1,0)) positive_unknown,
                     MAX(IF(label=0 AND cand_source='unknown_tail',1,0)) has_unknown_neg,
                     COUNTIF(label=0 AND cand_source='unknown_tail') unknown_neg_n
              FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}`
              GROUP BY 1,2)
            SELECT COUNT(*) events,
                   COUNTIF(positive_unknown=1) unknown_positive_events,
                   COUNTIF(positive_unknown=1 AND has_unknown_neg=0) unmatched_events,
                   MIN(unknown_neg_n) min_unknown_neg,
                   MAX(unknown_neg_n) max_unknown_neg
            FROM e""",
        "stratum_sources": f"""
            SELECT e.stratum, e.cp_type, c.cand_source, COUNT(*) n
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}` c
            JOIN `{base.PROJECT}.{base.DATASET}.{EVENT_TABLE}` e USING(snapshot_date,target_address,target_sequence_index)
            GROUP BY 1,2,3 ORDER BY 1,3""",
    }
    results = {}
    for name, q in queries.items():
        # Pools query was intentionally kept simple below; BQ does not allow
        # approximate quantiles after COUNT(*) without a subquery, so fix it now.
        if name == "pools":
            q = f"""
            SELECT snapshot_date, COUNT(*) cand_rows,
                   COUNT(DISTINCT CONCAT(CAST(target_sequence_index AS STRING),'|',target_address)) events,
                   ROUND(COUNT(*)*1.0/COUNT(DISTINCT CONCAT(CAST(target_sequence_index AS STRING),'|',target_address)),2) avg_pool,
                   SUM(label) positives,
                   SUM(IF(label=1 AND g_rank>2000,1,0)) positive_outside_top2000,
                   COUNTIF(g_rank=99999) sentinel_rows
            FROM `{base.PROJECT}.{base.DATASET}.{CAND_TABLE}`
            GROUP BY 1"""
        print("\n##", name, flush=True)
        cols, rows, _ = base.query_rows(op, tok, q, "sept verify " + name)
        print("\t".join(cols))
        for r in rows:
            print("\t".join(r))
        results[name] = {"columns": cols, "rows": rows}
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--manifest", default=os.path.join(DEST, "sept_panel_manifest.json"))
    args = ap.parse_args()

    op = base.opener()
    tok = base.token()
    ev_sql = literal_window(base.events_select_sql(
        SNAP, SEQ=SEQ, ASOF=ASOF, NATIVE_EVENTS=True))
    cand_sql = literal_window(base.candidates_sql(
        SNAP, SEQ=SEQ, EVENT_TABLE=EVENT_TABLE,
        ADD_UNKNOWN_NEGATIVES=True))

    if args.build:
        jr1 = base.run_sql(op, tok, ctas(ev_sql, EVENT_TABLE),
                           "sept panel events", dry=args.dry_run)
        jr2 = base.run_sql(op, tok, ctas(cand_sql, CAND_TABLE),
                           "sept panel candidates", dry=args.dry_run)
        if args.dry_run:
            return
        os.makedirs(DEST, exist_ok=True)
        with open(args.manifest, "w") as f:
            json.dump({
                "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "snapshot": SNAP, "event_table": EVENT_TABLE,
                "candidate_table": CAND_TABLE, "seq": SEQ, "asof": ASOF,
                "bytes_billed": {
                    "events": jr1.get("statistics", {}).get("query", {}).get("totalBytesBilled"),
                    "candidates": jr2.get("statistics", {}).get("query", {}).get("totalBytesBilled"),
                },
                "design": "Independent second temporal test month; no June/July/August refit.",
            }, f, indent=2)

    if args.verify:
        results = verify(op, tok)
        if args.build or os.path.exists(args.manifest):
            os.makedirs(DEST, exist_ok=True)
            with open(os.path.join(DEST, "sept_panel_verify.json"), "w") as f:
                json.dump(results, f, indent=2)

    if args.export and not args.dry_run:
        base.export_table(op, tok, EVENT_TABLE, GCS_PREFIX + "events/")
        base.export_table(op, tok, CAND_TABLE, GCS_PREFIX + "candidates/")
        p1 = base.download_prefix(op, tok, GCS_PREFIX + "events/", DEST + "/events")
        p2 = base.download_prefix(op, tok, GCS_PREFIX + "candidates/", DEST + "/candidates")
        os.makedirs(DEST, exist_ok=True)
        with open(os.path.join(DEST, "llm_panel_20220901_manifest.json"), "w") as f:
            json.dump({"events_files": p1, "candidates_files": p2,
                       "event_table": EVENT_TABLE, "candidate_table": CAND_TABLE,
                       "note": "September temporal holdout; truth_g_rank analysis-only"},
                      f, indent=2)
        print("export complete", len(p1), len(p2))


if __name__ == "__main__":
    main()
