#!/usr/bin/env python3
"""Background pipeline stage A: build learned-candidate-ranker inputs in BQ.

For snapshots 2022-06-01 (train), 2022-07-01 (val), 2022-08-01 (test):
- per-snapshot history edges in the preceding 90d and global popularity ranks;
- for every NEW outgoing event in the snapshot month, one positive (u,true_v)
  + 49 sampled non-neighbor candidates from the month-start top-2000 globally
  popular addresses (deterministic FARM_FINGERPRINT sampling);
- join per-(u,c) features: global hist popularity rank, personal interaction
  count/recency (0 for non-neighbors), 2-hop bridge signal/path count,
  wallet-level as-of features.
Writes nc_ranker_samples_v2 (partitioned by snapshot_date).
"""
import json, os, subprocess, sys, time, urllib.request

GCLOUD = os.environ.get("GCLOUD_BIN", "gcloud")
PROXY = "http://10.63.0.72:7890"
PROJECT = "ictdata-507912"
SEQ = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
SNAPS = ["2022-06-01", "2022-07-01", "2022-08-01"]
NCAND = 50  # 1 positive + 49 negatives per event


def token():
    env = {**os.environ, "https_proxy": PROXY, "http_proxy": PROXY}
    return subprocess.run([GCLOUD, "auth", "application-default",
                           "print-access-token"], capture_output=True,
                          text=True, env=env).stdout.strip()


def run(op, tok, sql, dry=False, tag=""):
    body = json.dumps({"configuration": {"query": {
        "query": sql, "useLegacySql": False, "dryRun": dry}}}).encode()
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"})
    r = json.load(op.open(req, timeout=120))
    if dry:
        if r["status"].get("errors"):
            sys.exit(f"DRYRUN FAIL {tag}: " + json.dumps(r["status"]["errors"])[:2000])
        print(f"  dryrun OK [{tag}]", flush=True)
        return
    jid = r["jobReference"]["jobId"]
    for _ in range(300):
        time.sleep(6)
        jr = json.load(op.open(urllib.request.Request(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
            headers={"Authorization": "Bearer " + tok}), timeout=120))
        if jr["status"]["state"] == "DONE":
            if jr["status"].get("errorResult"):
                sys.exit(f"FAILED [{tag}]: " + json.dumps(jr["status"]["errorResult"])[:2000])
            q = jr.get("statistics", {}).get("query", {})
            print(f"  done [{tag}] bytes={q.get('totalBytesBilled')}", flush=True)
            return
    sys.exit("timeout " + jid)


SNAP_T1 = {
    "2022-06-01": "2022-07-01", "2022-07-01": "2022-08-01",
    "2022-08-01": "2022-09-01",
}
SNAP_TH = {
    "2022-06-01": "2022-03-03", "2022-07-01": "2022-04-02",
    "2022-08-01": "2022-05-03",
}


def snapshot_sql(snap):
    return f"""
WITH params AS (
  SELECT TIMESTAMP('{snap} 00:00:00+00:00') AS t0,
         TIMESTAMP('{SNAP_TH[snap]} 00:00:00+00:00') AS th,
         TIMESTAMP('{SNAP_T1[snap]} 00:00:00+00:00') AS t1
),
hist AS (
  SELECT target_address AS u, counterparty_address AS c,
         COUNT(*) AS h_cnt, MAX(block_timestamp) AS h_last
  FROM {SEQ}, params p
  WHERE block_timestamp >= p.th AND block_timestamp < p.t0
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
gpop AS (
  SELECT c, ROW_NUMBER() OVER (ORDER BY h_cnt_sum DESC) AS g_rank,
         h_cnt_sum AS g_cnt
  FROM (
    SELECT counterparty_address AS c, COUNT(*) AS h_cnt_sum
    FROM {SEQ}, params p
    WHERE block_timestamp >= p.th AND block_timestamp < p.t0
      AND sequence_role='primary' AND direction='outgoing'
      AND counterparty_present AND NOT self_transaction
    GROUP BY 1)
),
top2000 AS (SELECT c, g_rank, g_cnt FROM gpop WHERE g_rank <= 2000),
new_ev AS (
  SELECT e.target_address AS u, e.counterparty_address AS v,
         e.target_sequence_index, e.block_timestamp
  FROM {SEQ} e, params p
  WHERE e.block_timestamp >= p.t0 AND e.block_timestamp < p.t1
    AND e.sequence_role='primary' AND e.direction='outgoing'
    AND e.counterparty_present AND NOT e.self_transaction
    AND NOT EXISTS (
      SELECT 1 FROM {SEQ} h, params pp
      WHERE h.target_address = e.target_address
        AND h.counterparty_address = e.counterparty_address
        AND h.direction='outgoing' AND h.sequence_role='primary'
        AND h.counterparty_present AND NOT h.self_transaction
        AND h.block_timestamp >= TIMESTAMP('2022-03-01')
        AND h.block_timestamp < e.block_timestamp
        AND h.block_timestamp >= TIMESTAMP_SUB(e.block_timestamp, INTERVAL 90 DAY))
  GROUP BY 1,2,3,4
),
pos AS (
  SELECT u, v AS c, target_sequence_index, 1 AS label FROM new_ev
),
neg AS (
  SELECT e.u, t.c AS c, e.target_sequence_index, 0 AS label
  FROM new_ev e
  CROSS JOIN top2000 t
  LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
  WHERE h.c IS NULL
    AND MOD(ABS(FARM_FINGERPRINT(CONCAT(e.target_sequence_index, '|', e.u, '|', t.c))), 40) = 0
),
samp AS (
  SELECT u, c, target_sequence_index, label FROM pos
  UNION ALL
  SELECT u, c, target_sequence_index, label FROM neg
),
br AS (   -- 2-hop non-neighbor bridge candidates for this snapshot
  SELECT e1.u AS u, e2.c AS c, COUNT(*) AS bridge_paths,
         SUM(1.0/d.od) AS bridge_signal
  FROM hist e1
  JOIN hist e2 ON e2.u = e1.c
  JOIN (SELECT u AS du, COUNT(*) AS od FROM hist GROUP BY 1) d ON d.du=e1.c
  LEFT JOIN hist dn ON dn.u=e1.u AND dn.c=e2.c
  WHERE e1.u <> e2.c AND dn.c IS NULL
  GROUP BY 1,2
)
SELECT DATE '{snap}' AS snapshot_date, s.u, s.c, s.target_sequence_index,
       s.label,
       IFNULL(g.g_rank, 99999) AS g_rank,
       IFNULL(g.g_cnt, 0) AS g_cnt,
       IFNULL(hh.h_cnt, 0) AS personal_cnt,
       IFNULL(DATE_DIFF(DATE '{snap}', DATE(hh.h_last), DAY), 999) AS days_since,
       IFNULL(br.bridge_paths, 0) AS bridge_paths,
       IFNULL(br.bridge_signal, 0) AS bridge_signal
FROM samp s
LEFT JOIN gpop g ON g.c=s.c
LEFT JOIN hist hh ON hh.u=s.u AND hh.c=s.c
LEFT JOIN br ON br.u=s.u AND br.c=s.c"""


def main():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY}))
    tok = token()
    parts = [f"SELECT * FROM ({snapshot_sql(s)})" for s in SNAPS]
    ddl = (f"CREATE OR REPLACE TABLE `{PROJECT}.exgraph.nc_ranker_samples_v2`\n"
           "PARTITION BY snapshot_date AS\n" + "\nUNION ALL\n".join(parts))
    run(op, tok, ddl, dry=True, tag="ranker samples")
    run(op, tok, ddl, tag="ranker samples")

    q = """SELECT snapshot_date, label, COUNT(*) AS n,
                  COUNT(DISTINCT CONCAT(u,'|',CAST(target_sequence_index AS STRING))) AS events
           FROM `ictdata-507912.exgraph.nc_ranker_samples_v2`
           GROUP BY 1,2 ORDER BY 1,2"""
    # quick verification query via jobs API
    body = json.dumps({"configuration": {"query": {"query": q, "useLegacySql": False}}}).encode()
    r = json.load(op.open(urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"}), timeout=120))
    jid = r["jobReference"]["jobId"]
    for _ in range(60):
        time.sleep(5)
        jr = json.load(op.open(urllib.request.Request(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
            headers={"Authorization": "Bearer " + tok}), timeout=120))
        if jr["status"]["state"] == "DONE":
            print("verification job finished",
                  jr["status"].get("errorResult", "OK"), flush=True)
            break


if __name__ == "__main__":
    main()
