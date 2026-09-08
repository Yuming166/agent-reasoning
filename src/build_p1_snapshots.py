#!/usr/bin/env python3
"""Build event-driven P1 bridge occlusion tables for router train/val/test
snapshots (2022-06-01 train, 2022-07-01 validation, 2022-08-01 test).

For snapshot S, 90-day history [S-90d, S) and test month [S, S+30d):
  w bridges event u->v if history has u->w (incoming) and w->v (outgoing).

Writes:
  ictdata-507912.exgraph.p1_bridge_events_v2 (partitioned by snapshot_date)
  ictdata-507912.exgraph.p1_wallet_icf_v2    (per-wallet I_cf per snapshot)
"""
import json, os, subprocess, sys, time, urllib.request

GCLOUD = "/storage/gaoym/tools/google-cloud-sdk/bin/gcloud"
PROXY = "http://10.63.0.72:7890"
PROJECT = "ictdata-507912"
SEQ = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
SNAPSHOTS = ["2022-06-01", "2022-07-01", "2022-08-01"]


def token() -> str:
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
        print("  dryrun OK")
        return
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


def bridge_body(snap: str) -> str:
    return f"""
WITH hist_in AS (
  SELECT target_address AS w, counterparty_address AS u
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 90 DAY))
    AND block_timestamp <  TIMESTAMP(DATE '{snap}')
    AND sequence_role='primary' AND direction='incoming'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
hist_out AS (
  SELECT target_address AS w, counterparty_address AS v
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATETIME_SUB(DATE '{snap}', INTERVAL 90 DAY))
    AND block_timestamp <  TIMESTAMP(DATE '{snap}')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
outdeg AS (SELECT w, COUNT(*) AS w_outdeg FROM hist_out GROUP BY 1),
test AS (
  SELECT CONCAT(target_address,'|',counterparty_address,'|',
                CAST(target_sequence_index AS STRING)) AS event_key,
         target_address AS u, counterparty_address AS v, target_sequence_index
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP(DATE '{snap}')
    AND block_timestamp <  TIMESTAMP(DATETIME_ADD(DATE '{snap}', INTERVAL 30 DAY))
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
)
SELECT t.event_key, t.u, t.v, t.target_sequence_index,
       hi.w AS bridge_w, od.w_outdeg
FROM test t
JOIN hist_in hi ON hi.u = t.u
JOIN hist_out ho ON ho.w = hi.w AND ho.v = t.v
JOIN outdeg od ON od.w = hi.w
GROUP BY 1,2,3,4,5,6"""


def main() -> None:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY}))
    tok = token()
    parts = [
        f"SELECT DATE '{s}' AS snapshot_date, q.* FROM ({bridge_body(s)}) q"
        for s in SNAPSHOTS]
    ddl = (f"CREATE OR REPLACE TABLE `{PROJECT}.exgraph.p1_bridge_events_v2`\n"
           "PARTITION BY snapshot_date AS\n" + "\nUNION ALL\n".join(parts))
    print("build p1_bridge_events_v2 ...")
    run(op, tok, ddl, dry=True)
    run(op, tok, ddl)

    icf = f"""
CREATE OR REPLACE TABLE `{PROJECT}.exgraph.p1_wallet_icf_v2` AS
WITH weighted AS (
  SELECT snapshot_date, event_key, bridge_w, 1.0/MAX(w_outdeg) AS wsig
  FROM `{PROJECT}.exgraph.p1_bridge_events_v2`
  GROUP BY snapshot_date, event_key, bridge_w
),
evt_tot AS (
  SELECT snapshot_date, event_key, SUM(wsig) AS evt_sig
  FROM weighted GROUP BY 1,2
)
SELECT w.snapshot_date, w.bridge_w AS target_address,
       COUNT(*) AS bridges_events,
       SUM(w.wsig / e.evt_sig) AS icf_score_p1,
       SUM(w.wsig) AS icf_raw_signal
FROM weighted w JOIN evt_tot e USING(snapshot_date, event_key)
GROUP BY 1,2;"""
    print("build p1_wallet_icf_v2 ...")
    run(op, tok, icf, dry=True)
    run(op, tok, icf)
    print("all P1 snapshot tables built.")


if __name__ == "__main__":
    main()
