#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from run_google_coverage_validation import BigQueryClient
from bq_openworld import job_summary

ROOT=Path(__file__).resolve().parents[1]
SQL_PATH=ROOT/'scripts'/'first_sanity_check_wide.sql'
OUT=ROOT/'results'/'first_sanity_check_wide_202203_202208.json'
PROJECT='ictdata-507912'

def rows(result):
    cols=[f['name'] for f in result.get('schema',{}).get('fields',[])]
    return [dict(zip(cols,[x.get('v') for x in row.get('f',[])])) for row in result.get('rows',[])]

client=BigQueryClient(PROJECT,'gcloud')
sql=SQL_PATH.read_text()
dry=client.query(sql,dry_run=True,max_bytes=20_000_000_000)
actual=client.query(sql,dry_run=False,max_bytes=20_000_000_000)
result={
 'experiment_id':'OW-003',
 'sql_path':str(SQL_PATH),
 'project':PROJECT,
 'data_version':'target_event_sequences_20220301_20220901',
 'label_table':'openworld_wash_labels_v1',
 'label_policy':'external_evaluation_only',
 'dry_run':job_summary(dry),
 'actual':job_summary(actual),
 'columns':[f['name'] for f in actual.get('schema',{}).get('fields',[])],
 'rows':rows(actual),
}
OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
