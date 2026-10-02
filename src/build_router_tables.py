#!/usr/bin/env python3
"""P4 router ingredients per snapshot (2022-06-01 train, 2022-07-01 val,
2022-08-01 test):

1. p2_trigger_v2: for each target wallet with outgoing counterparties in the
   30 days BEFORE snapshot, volume-weighted mean of positive lag-1 hourly
   activity correlations with its counterparties (directed spillover proxy).
2. wallet_future_headroom_v1: per wallet, future-30d event mass that the
   global popularity baseline ranks poorly:
     headroom = sum_events (1 - 1/global_pop_rank(counterparty)).
   This is the ceiling a deliberation agent could improve over popularity and
   the ranking target the router learns to predict from as-of features.
"""
import json, os, subprocess, sys, time, urllib.request

GCLOUD = "/storage/gaoym/tools/google-cloud-sdk/bin/gcloud"
PROXY = "http://10.63.0.72:7890"
PROJECT = "ictdata-507912"
SEQ = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
SNAPSHOTS = ["2022-06-01", "2022-07-01", "2022-08-01"]


def token():
    env = {**os.environ, "https_proxy": PROXY, "http_proxy": PROXY}
    return subprocess.run([GCLOUD, "auth", "application-default",
                           "print-access-token"], capture_output=True,
                          text=True, env=env).stdout.strip()


def run(op, tok, sql, dry=False):
    body = json.dumps({"configuration": {"query": {
        "query": sql, "useLegacySql": False, "dryRun": dry}}}).encode()
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"})
    r = json.load(op.open(req, timeout=120))
    if dry:
        if r["status"].get("errors"):
            sys.exit("DRYRUN FAIL: " + json.dumps(r["status"]["errors"])[:2000])
        print("  dryrun OK"); return
    jid = r["jobReference"]["jobId"]
    for _ in range(240):
        time.sleep(6)
        jr = json.load(op.open(urllib.request.Request(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
            headers={"Authorization": "Bearer " + tok}), timeout=120))
        if jr["status"]["state"] == "DONE":
            if jr["status"].get("errorResult"):
                sys.exit("FAILED: " + json.dumps(jr["status"]["errorResult"])[:2000])
            q = jr.get("statistics", {}).get("query", {})
            print(f"  done bytes={q.get('totalBytesBilled')}", flush=True)
            return
    sys.exit("timeout " + jid)


def trigger_body(snap):
    # hourly grid over [snap-30d, snap); lag-1 corr a_h vs b_{h+1}
    return f"""
WITH hourly AS (
  SELECT target_address AS addr,
         TIMESTAMP_TRUNC(block_timestamp, HOUR) AS hr, COUNT(*) AS act
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 30 DAY))
    AND block_timestamp <  TIMESTAMP(DATE '{snap}')
    AND sequence_role='primary'
  GROUP BY 1,2
),
pairs AS (
  SELECT target_address AS a, counterparty_address AS b, COUNT(*) AS vol
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 30 DAY))
    AND block_timestamp <  TIMESTAMP(DATE '{snap}')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
grid AS (
  SELECT TIMESTAMP_ADD(TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 30 DAY)),
                       INTERVAL k HOUR) AS hr,
         TIMESTAMP_ADD(TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 30 DAY)),
                       INTERVAL k+1 HOUR) AS hr_next
  FROM UNNEST(GENERATE_ARRAY(0,719)) AS k
),
panel AS (
  SELECT p.a, p.b, p.vol,
         IFNULL(ha.act,0) AS a_act, IFNULL(hb.act,0) AS b_next
  FROM pairs p CROSS JOIN grid g
  LEFT JOIN hourly ha ON ha.addr=p.a AND ha.hr=g.hr
  LEFT JOIN hourly hb ON hb.addr=p.b AND hb.hr=g.hr_next
),
pc AS (
  SELECT a, b, ANY_VALUE(vol) AS vol,
    CASE WHEN COUNTIF(a_act>0 OR b_next>0) < 24 THEN NULL
         ELSE CORR(a_act, b_next) END AS lag1_corr
  FROM panel GROUP BY a,b
)
SELECT DATE '{snap}' AS snapshot_date, a AS target_address, COUNT(*) AS trigger_pairs,
       SUM(vol) AS trigger_total_vol,
       SAFE_DIVIDE(SUM(IF(lag1_corr>0, lag1_corr*vol, 0)),
                   NULLIF(SUM(IF(lag1_corr>0, vol, 0)),0)) AS trigger_score_p2,
       COUNTIF(lag1_corr>0.3) AS trigger_strong_pairs
FROM pc GROUP BY a, DATE '{snap}'"""


def headroom_body(snap):
    return f"""
WITH fut AS (
  SELECT target_address, counterparty_address, target_sequence_index
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATE '{snap}')
    AND block_timestamp <  TIMESTAMP(DATETIME_ADD(DATE '{snap}', INTERVAL 30 DAY))
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
),
pop AS (
  SELECT counterparty_address AS cand,
         ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS pop_rank
  FROM fut GROUP BY 1
)
SELECT DATE '{snap}' AS snapshot_date, f.target_address,
       COUNT(*) AS fwd_out_events,
       COUNT(DISTINCT f.counterparty_address) AS fwd_out_cps,
       SUM(1.0/p.pop_rank) AS pop_score_sum,
       AVG(1.0/p.pop_rank) AS pop_mrr,
       SUM(1.0 - 1.0/p.pop_rank) AS headroom_sum,
       COUNTIF(p.pop_rank > 100) AS hard_events
FROM fut f JOIN pop p ON p.cand=f.counterparty_address
GROUP BY f.target_address, DATE '{snap}'"""


def main():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY}))
    tok = token()

    trig = ("CREATE OR REPLACE TABLE "
            f"`{PROJECT}.exgraph.p2_trigger_v2` AS\n"
            + "\nUNION ALL\n".join(f"SELECT * FROM ({trigger_body(s)})" for s in SNAPSHOTS))
    print("build p2_trigger_v2 ..."); run(op, tok, trig, dry=True); run(op, tok, trig)

    hd = ("CREATE OR REPLACE TABLE "
          f"`{PROJECT}.exgraph.wallet_future_headroom_v1` AS\n"
          + "\nUNION ALL\n".join(f"SELECT * FROM ({headroom_body(s)})" for s in SNAPSHOTS))
    print("build wallet_future_headroom_v1 ..."); run(op, tok, hd, dry=True); run(op, tok, hd)
    print("done")


if __name__ == "__main__":
    main()
