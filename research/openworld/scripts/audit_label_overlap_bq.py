#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from run_google_coverage_validation import BigQueryClient
from bq_openworld import job_summary

PROJECT='ictdata-507912'
DATASET='exgraph'
TABLE=f'`{PROJECT}.{DATASET}.target_event_sequences_20220301_20220901`'
LABEL=f'`{PROJECT}.{DATASET}.openworld_wash_labels_v1`'
SQL=f'''
WITH labels AS (
  SELECT DISTINCT LOWER(tx_hash) AS tx_hash
  FROM {LABEL}
), observed AS (
  SELECT
    LOWER(transaction_hash) AS tx_hash,
    MIN(block_timestamp) AS first_timestamp,
    MAX(block_timestamp) AS last_timestamp,
    COUNT(*) AS sequence_rows,
    COUNT(DISTINCT event_family) AS event_families,
    ARRAY_AGG(DISTINCT event_family ORDER BY event_family) AS families
  FROM {TABLE}
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
    AND transaction_hash IS NOT NULL
  GROUP BY tx_hash
)
SELECT
  COUNT(*) AS label_hashes,
  COUNTIF(o.tx_hash IS NOT NULL) AS matched_hashes,
  COUNTIF(o.tx_hash IS NULL) AS unmatched_hashes,
  MIN(o.first_timestamp) AS min_timestamp,
  MAX(o.last_timestamp) AS max_timestamp,
  SUM(IF(o.tx_hash IS NOT NULL, o.sequence_rows, 0)) AS matched_sequence_rows
FROM labels AS l
LEFT JOIN observed AS o USING (tx_hash)
'''
SQL_MONTH=f'''
WITH labels AS (
  SELECT DISTINCT LOWER(tx_hash) AS tx_hash
  FROM {LABEL}
), observed AS (
  SELECT DISTINCT LOWER(transaction_hash) AS tx_hash, DATE_TRUNC(DATE(block_timestamp), MONTH) AS month
  FROM {TABLE}
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
    AND transaction_hash IS NOT NULL
)
SELECT
  month,
  COUNT(*) AS matched_hashes
FROM observed JOIN labels USING (tx_hash)
GROUP BY month ORDER BY month
'''
def rows(result):
    out=[]
    for r in result.get('rows',[]): out.append([x.get('v') for x in r.get('f',[])])
    return out

client=BigQueryClient(PROJECT,'gcloud')
outputs=[]
for name,sql in [('summary',SQL),('monthly',SQL_MONTH)]:
    dry=client.query(sql,dry_run=True,max_bytes=20_000_000_000)
    actual=client.query(sql,dry_run=False,max_bytes=20_000_000_000)
    outputs.append({'name':name,'dry':job_summary(dry),'actual':job_summary(actual),'columns':[f['name'] for f in actual.get('schema',{}).get('fields',[])],'rows':rows(actual)})
result={'experiment_id':'OW-001','label_table':LABEL,'temporal_table':TABLE,'label_policy':'external_evaluation_only','outputs':outputs}
out=Path(__file__).resolve().parents[1]/'results'/'label_overlap_audit.json'
out.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False,default=str))
