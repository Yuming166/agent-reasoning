#!/usr/bin/env python3
"""Build leakage-hardened v2 panels for snapshots 2022-06..2022-09.

v2 differs from frozen v1 only in candidate construction: every event gets
three deterministic unknown-tail negatives, matching positive g_rank=99999
events. Event strata and positive examples are unchanged; v1 tables remain
frozen and are used as event inputs.
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import build_llm_panel as base  # noqa: E402
from build_sept_panel import literal_window  # noqa: E402

SNAPS = ["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]
EVENT_TABLES = {s: ("llm_panel_events_20220901" if s == "2022-09-01"
                    else "llm_panel_events_v1") for s in SNAPS}
CAND_TABLES = {
    "2022-06-01": "llm_panel_candidates_v2_20220601",
    "2022-07-01": "llm_panel_candidates_v2_20220701",
    "2022-08-01": "llm_panel_candidates_v2_20220801",
    "2022-09-01": "llm_panel_candidates_v2_20220901",
}
SEQ_V1 = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
SEQ_V2 = "`ictdata-507912.exgraph.target_event_sequences_20220301_20221001`"
ASOF = {
    "2022-06-01": "`ictdata-507912.exgraph.wallet_asof_features_v1`",
    "2022-07-01": "`ictdata-507912.exgraph.wallet_asof_features_v1`",
    "2022-08-01": "`ictdata-507912.exgraph.wallet_asof_features_v1`",
    "2022-09-01": "`ictdata-507912.exgraph.wallet_asof_features_20220901`",
}
DEST = "artifacts/llm_panel_v2"


def ctas(sql, table):
    return (f"CREATE OR REPLACE TABLE `{base.PROJECT}.{base.DATASET}.{table}`\n"
            "PARTITION BY snapshot_date CLUSTER BY target_address AS\n"
            f"SELECT * FROM ({sql})")


def rewrite_unknown_source(sql, snap, september):
    # Generic base candidate generator uses the v1 physical source for Jun-Aug
    # and physical union for Sep. Its unknown CTE currently hardcodes the old
    # Mar-Sep table + Sep snapshot; patch both literals here.
    lo = {"2022-06-01": "2022-03-03", "2022-07-01": "2022-04-02",
          "2022-08-01": "2022-05-03", "2022-09-01": "2022-06-03"}[snap]
    sql = sql.replace("TIMESTAMP('2022-03-01 00:00:00+00:00')",
                      f"TIMESTAMP('{lo} 00:00:00+00:00')")
    sql = sql.replace("TIMESTAMP('2022-09-01 00:00:00+00:00')",
                      f"TIMESTAMP('{snap} 00:00:00+00:00')")
    if not september:
        # The known-address CTE already has direct literal filters, satisfying
        # the partition requirement. Keep the old physical source.
        pass
    return sql


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--snaps', nargs='+', default=SNAPS)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--export', action='store_true')
    args=ap.parse_args()
    op=base.opener(); tok=base.token()
    manifest=[]
    for snap in args.snaps:
        sept = snap == '2022-09-01'
        seq = SEQ_V2 if sept else SEQ_V1
        q0=base.candidates_sql(snap, SEQ=seq, EVENT_TABLE=EVENT_TABLES[snap],
                               ADD_UNKNOWN_NEGATIVES=True)
        q=rewrite_unknown_source(q0,snap,sept)
        if sept:
            q=literal_window(q)
        table=CAND_TABLES[snap]
        print('\n###',snap,table,flush=True)
        if args.build:
            jr=base.run_sql(op,tok,ctas(q,table),f'v2 candidates {snap}',dry=args.dry_run)
            if not args.dry_run:
                manifest.append({'snapshot':snap,'table':table,
                    'bytes_billed':jr.get('statistics',{}).get('query',{}).get('totalBytesBilled')})
        if args.verify and not args.dry_run:
            vq=f"""
SELECT '{snap}' snapshot, COUNT(*) AS n_rows, COUNT(DISTINCT CONCAT(CAST(target_sequence_index AS STRING),'|',target_address)) events,
       SUM(label) positives, COUNTIF(cand_source='unknown_tail') unknown_negs,
       COUNTIF(label=1 AND g_rank=99999) unknown_pos,
       SUM(IF(label=1 AND g_rank=99999,1,0)) x
FROM `{base.PROJECT}.{base.DATASET}.{table}` GROUP BY 1"""
            cols, rows,_=base.query_rows(op,tok,vq,'verify v2 '+snap)
            print('\t'.join(cols)); [print('\t'.join(r)) for r in rows]
        if args.export and not args.dry_run:
            prefix=f'llm_panel_v2/{snap}/candidates/'
            base.export_table(op,tok,table,prefix)
            paths=base.download_prefix(op,tok,prefix,os.path.join(DEST,snap,'candidates'))
            manifest.append({'snapshot':snap,'files':paths})
    if manifest:
        os.makedirs(DEST,exist_ok=True)
        with open(os.path.join(DEST,'v2_build_manifest.json'),'w') as f: json.dump({'built_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'items':manifest},f,indent=2)
if __name__=='__main__': main()
