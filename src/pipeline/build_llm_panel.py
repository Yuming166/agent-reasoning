#!/usr/bin/env python3
"""Stage D go/no-go step 1: build a stratified paired LLM panel in BigQuery.

Design (pre-registered, leakage-safe):
- snapshots 2022-06-01 (router train), 2022-07-01 (prompt/tune),
  2022-08-01 (frozen go/no-go test); target month = [snap, snap+1m),
  history = [snap-90d, snap), strictly as-of.
- PER_SNAP distinct primary outgoing counterparty-present non-self events per
  snapshot, stratified oversampled over (cp_type x difficulty x activity):
    new:     tail_truth (truth global rank >2000), popular_truth (<=2000)
    repeat:  hard (bridge non-neighbor candidates exist OR truth rank>2000), easy
    activity: high/low vs the per-snapshot median evt_cnt_90d
  Cell quotas are proportional to population (min 1) then deterministically
  topped up to exactly PER_SNAP by FARM_FINGERPRINT hash order.
- candidates per event (~50): observed positive + negatives drawn ONLY from
  pre-snapshot history (no test leakage). new events get 2-hop bridge
  non-neighbors (16) + global top-2000 non-neighbors (16) + global-tail
  rank>2000 non-neighbors (16); repeat events get personal historical
  counterparties (30) + top-2000/tail padding to 49 negatives. Deterministic
  MOD(FARM_FINGERPRINT, k) bounded sampling, deduped, positive excluded.
- truth_g_rank is exposed ONLY for strata/analysis; it MUST NOT be used as a
  candidate/model/router feature (it is the positive's own global rank).

Outputs (partitioned by snapshot_date, clustered by target_address):
  exgraph.llm_panel_events_v1     : sampled events + strata + pop_weight
  exgraph.llm_panel_candidates_v1 : one row per (event, candidate) + as-of feats
Local artifacts: artifacts/llm_panel_v1/*.csv.gz via GCS (small extract).
"""
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

GCLOUD = os.environ.get("GCLOUD_BIN", "gcloud")
PROXY = (os.environ.get("EXGRAPH_HTTP_PROXY")
         or os.environ.get("HTTPS_PROXY")
         or os.environ.get("HTTP_PROXY"))
PROJECT = "ictdata-507912"
DATASET = "exgraph"
BUCKET = "ictdata-exgraph-artifacts"
SEQ = "`ictdata-507912.exgraph.target_event_sequences_20220301_20220901`"
EVENTS = "`ictdata-507912.exgraph.nc_events_v1`"
ASOF = "`ictdata-507912.exgraph.wallet_asof_features_v1`"
SNAPS = ["2022-06-01", "2022-07-01", "2022-08-01"]
T1 = {"2022-06-01": "2022-07-01", "2022-07-01": "2022-08-01",
      "2022-08-01": "2022-09-01", "2022-09-01": "2022-10-01"}
TH = {"2022-06-01": "2022-03-03", "2022-07-01": "2022-04-02",
      "2022-08-01": "2022-05-03", "2022-09-01": "2022-06-03"}
PER_SNAP = 1000


def token():
    env = dict(os.environ)
    if PROXY:
        env.update({"https_proxy": PROXY, "http_proxy": PROXY})
    r = subprocess.run([GCLOUD, "auth", "application-default",
                        "print-access-token"], capture_output=True,
                       text=True, env=env)
    if r.returncode:
        sys.exit(f"token failed: {r.stderr[:300]}")
    return r.stdout.strip()


def opener():
    proxies = {"https": PROXY, "http": PROXY} if PROXY else {}
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))


def submit(op, tok, sql, dry=False):
    body = json.dumps({"configuration": {"query": {
        "query": sql, "useLegacySql": False, "dryRun": dry}}}).encode()
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"})
    return json.load(op.open(req, timeout=180))


def wait(op, tok, jid, tag=""):
    for _ in range(400):
        time.sleep(5)
        try:
            jr = json.load(op.open(urllib.request.Request(
                f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
                headers={"Authorization": "Bearer " + tok}), timeout=120))
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  job-poll retry [{tag}] {e!r}", flush=True)
            time.sleep(5)
            continue
        if jr["status"]["state"] == "DONE":
            if jr["status"].get("errorResult"):
                raise RuntimeError(f"[{tag}] " + json.dumps(jr["status"]["errorResult"])[:2000])
            q = jr.get("statistics", {}).get("query", {})
            print(f"  done [{tag}] bytesBilled={q.get('totalBytesBilled')} cache={q.get('cacheHit')}", flush=True)
            return jr
    raise RuntimeError("timeout " + jid)


def run_sql(op, tok, sql, tag, dry=False):
    r = submit(op, tok, sql, dry=dry)
    if dry:
        if r["status"].get("errors"):
            raise RuntimeError(f"DRYRUN {tag}: " + json.dumps(r["status"]["errors"])[:2000])
        print(f"  dryrun OK [{tag}]", flush=True)
        return
    return wait(op, tok, r["jobReference"]["jobId"], tag)


def events_select_sql(snap, *, SEQ=SEQ, ASOF=ASOF, EVENTS=EVENTS,
                      NATIVE_EVENTS=False, T1S=None, THS=None):
    """Per-snapshot stratified event sample.

    Event-level strata use only cheap as-of quantities (cp_type, the
    positive's pre-snapshot global rank, 90d activity). Bridge richness is
    expensive for the whole population, so it is realized only for sampled
    events at candidate-build time. 8 cells (cp_type x difficulty x activity)
    get a fixed quota of 125 each = 1000; any undersized cell is filled by
    deterministic global hash order so totals are exact.
    """
    frozen_ev = f"""
ev AS (
  SELECT e.u, e.v, e.target_sequence_index, e.block_timestamp, e.cp_type
  FROM {EVENTS} e, params p
  WHERE e.block_timestamp >= p.t0 AND e.block_timestamp < p.t1
),"""
    native_ev = f"""
base_events AS (
  SELECT target_address AS u, counterparty_address AS v,
         target_sequence_index, block_timestamp
  FROM {SEQ}
  WHERE block_timestamp >= TIMESTAMP('{(THS or TH)[snap]} 00:00:00+00:00')
    AND block_timestamp <  TIMESTAMP('{(T1S or T1)[snap]} 00:00:00+00:00')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2,3,4
),
tagged AS (
  SELECT *, LAG(block_timestamp) OVER (
    PARTITION BY u,v ORDER BY block_timestamp,target_sequence_index) AS prev_ts
  FROM base_events
),
ev AS (
  SELECT u,v,target_sequence_index,block_timestamp,
         IF(prev_ts IS NOT NULL AND
            prev_ts >= TIMESTAMP_SUB(block_timestamp, INTERVAL 90 DAY),
            'repeat','new') AS cp_type
  FROM tagged, params p
  WHERE block_timestamp >= p.t0 AND block_timestamp < p.t1
),"""
    return f"""
WITH params AS (
  SELECT TIMESTAMP('{snap} 00:00:00+00:00') AS t0,
         TIMESTAMP('{(THS or TH)[snap]} 00:00:00+00:00') AS th,
         TIMESTAMP('{(T1S or T1)[snap]} 00:00:00+00:00') AS t1
),
gpop AS (
  SELECT counterparty_address AS c,
         ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS g_rank
  FROM {SEQ}, params p
  WHERE block_timestamp >= p.th AND block_timestamp < p.t0
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1
),
med AS (
  SELECT APPROX_QUANTILES(evt_cnt_90d, 2)[OFFSET(1)] AS med_evt
  FROM {ASOF} WHERE snapshot_date = DATE '{snap}'
),
{native_ev if NATIVE_EVENTS else frozen_ev}
enr AS (
  SELECT ev.*,
         IFNULL(g.g_rank, 99999) AS truth_g_rank,
         IFNULL(a.evt_cnt_90d, 0) AS evt_cnt_90d,
         IFNULL(a.cp_entropy_90d, 0) AS cp_entropy_90d,
         IFNULL(a.cp_new_rate_30d, 0) AS cp_new_rate_30d,
         IFNULL(a.active_days_90d, 0) AS active_days_90d
  FROM ev
  LEFT JOIN gpop g ON g.c = ev.v
  LEFT JOIN {ASOF} a
    ON a.snapshot_date = DATE '{snap}' AND a.target_address = ev.u
),
cell AS (
  SELECT enr.*,
    CASE WHEN evt_cnt_90d >= med_evt THEN 'high' ELSE 'low' END AS activity,
    CASE WHEN cp_type='new' THEN
           CASE WHEN truth_g_rank > 2000 THEN 'new_tail' ELSE 'new_popular' END
         ELSE CASE WHEN truth_g_rank > 2000 THEN 'repeat_hard' ELSE 'repeat_easy' END
    END AS stratum,
    MOD(ABS(FARM_FINGERPRINT(
      CONCAT(CAST(target_sequence_index AS STRING),'|',u,'|',v))), 1000000) AS hsh
  FROM enr CROSS JOIN med
),
pop AS (
  SELECT stratum, activity, COUNT(*) AS pop_n
  FROM cell GROUP BY 1,2
),
ranked AS (
  SELECT cell.*,
         ROW_NUMBER() OVER (PARTITION BY stratum, activity
                            ORDER BY hsh, block_timestamp) AS rn_cell
  FROM cell
),
picked AS (
  SELECT r.* FROM ranked r WHERE r.rn_cell <= 125
),
overflow AS (
  SELECT c.*,
         ROW_NUMBER() OVER (ORDER BY
           MOD(ABS(FARM_FINGERPRINT(CONCAT('topup|',
             CAST(c.target_sequence_index AS STRING),'|',c.u,'|',c.v))),1000000))
           AS rn_topup
  FROM cell c
  LEFT JOIN picked k
    ON k.target_sequence_index=c.target_sequence_index AND k.u=c.u AND k.v=c.v
  WHERE k.u IS NULL
),
combined AS (
  SELECT u,v,target_sequence_index,block_timestamp,cp_type,truth_g_rank,evt_cnt_90d,cp_entropy_90d,cp_new_rate_30d,active_days_90d,activity,stratum,hsh FROM picked
  UNION ALL
  SELECT u,v,target_sequence_index,block_timestamp,cp_type,truth_g_rank,evt_cnt_90d,cp_entropy_90d,cp_new_rate_30d,active_days_90d,activity,stratum,hsh FROM overflow, (SELECT COUNT(*) AS np FROM picked) z
  WHERE rn_topup <= 1000 - z.np
)
SELECT DATE '{snap}' AS snapshot_date,
       u AS target_address, v AS counterparty_address,
       target_sequence_index, block_timestamp, cp_type, truth_g_rank,
       CAST(NULL AS INT64) AS bridge_candidate_n,
       combined.evt_cnt_90d, combined.cp_entropy_90d, combined.cp_new_rate_30d,
       combined.active_days_90d, combined.activity, combined.stratum, combined.hsh,
       p.pop_n * 1.0 / COUNT(*) OVER (PARTITION BY combined.stratum, combined.activity)
         AS pop_weight
FROM combined
JOIN pop p ON p.stratum=combined.stratum AND p.activity=combined.activity
"""

def candidates_sql(snap, *, SEQ=SEQ, THS=None, EVENT_TABLE=None,
                    ADD_UNKNOWN_NEGATIVES=False):
    evtab = f"`{PROJECT}.{DATASET}.{EVENT_TABLE}`" if EVENT_TABLE else f"`{PROJECT}.{DATASET}.llm_panel_events_v1`"
    old_table = f"`{PROJECT}.{DATASET}.target_event_sequences_20220301_20220901`"
    unknown_ctes = ""
    unknown_segment = ""
    unknown_union = ""
    if ADD_UNKNOWN_NEGATIVES:
        unknown_ctes = f'''
known_addr AS (
  SELECT DISTINCT address FROM (
    SELECT target_address AS address FROM {old_table}
    WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00:00')
      AND block_timestamp < TIMESTAMP('{snap} 00:00:00+00:00')
    UNION DISTINCT
    SELECT counterparty_address FROM {old_table}
    WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00:00')
      AND block_timestamp < TIMESTAMP('{snap} 00:00:00+00:00')
  ) WHERE address IS NOT NULL
),
unknown_pool AS (
  SELECT k.address AS c
  FROM known_addr k LEFT JOIN gpop g ON g.c=k.address
  WHERE g.c IS NULL
),
unknown_samp AS (
  SELECT c FROM unknown_pool
  WHERE MOD(ABS(FARM_FINGERPRINT(c)), 200) = 0
),
'''
        unknown_segment = '''
seg_unknown_tail AS (
  SELECT u, target_sequence_index, c, 40 AS src_rank, 'unknown_tail' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, t.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               'unknown|',CAST(e.target_sequence_index AS STRING),'|',e.u,'|',t.c))),1000000)) AS rn
    FROM ev e CROSS JOIN unknown_samp t
    LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
    WHERE h.c IS NULL AND t.c <> e.v AND t.c <> e.u)
  WHERE rn <= 3
),
'''
        unknown_union = "UNION ALL SELECT * FROM seg_unknown_tail"
    return f"""
WITH params AS (
  SELECT TIMESTAMP('{snap} 00:00:00+00:00') AS t0,
         TIMESTAMP('{(THS or TH)[snap]} 00:00:00+00:00') AS th
),
gpop AS (
  SELECT counterparty_address AS c,
         ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS g_rank,
         COUNT(*) AS g_cnt
  FROM {SEQ}, params p
  WHERE block_timestamp >= p.th AND block_timestamp < p.t0
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1
),
top2000 AS (SELECT c, g_rank, g_cnt FROM gpop WHERE g_rank <= 2000),
tail AS (SELECT c, g_rank, g_cnt FROM gpop WHERE g_rank > 2000),
tail_samp AS (   -- t-only deterministic prefilter: ~1/200 of tail, bounds join cost
  SELECT c, g_rank, g_cnt FROM tail
  WHERE MOD(ABS(FARM_FINGERPRINT(c)), 200) = 0),
{unknown_ctes}hist AS (
  SELECT target_address AS u, counterparty_address AS c,
         COUNT(*) AS h_cnt, MAX(block_timestamp) AS h_last
  FROM {SEQ}, params p
  WHERE block_timestamp >= p.th AND block_timestamp < p.t0
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2
),
od AS (SELECT u, COUNT(DISTINCT c) AS outdeg FROM hist GROUP BY 1),
br AS (
  SELECT e1.u, e2.c,
         COUNT(*) AS bridge_paths,
         SUM(1.0/d.outdeg) AS bridge_signal
  FROM hist e1 JOIN hist e2 ON e2.u = e1.c
  JOIN od d ON d.u = e1.c
  LEFT JOIN hist dn ON dn.u=e1.u AND dn.c=e2.c
  WHERE e1.u <> e2.c AND dn.c IS NULL
  GROUP BY 1,2
),
ev AS (
  SELECT target_address AS u, counterparty_address AS v,
         target_sequence_index, cp_type
  FROM {evtab} WHERE snapshot_date = DATE '{snap}'
),
new_ev AS (SELECT * FROM ev WHERE cp_type='new'),
rep_ev AS (SELECT * FROM ev WHERE cp_type='repeat'),
pos AS (
  SELECT u, target_sequence_index, v AS c, 90 AS src_rank, 'positive' AS cand_source
  FROM ev
),
seg_new_bridge AS (
  SELECT u, target_sequence_index, c, 10 AS src_rank, 'new_bridge' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, b.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               CAST(e.target_sequence_index AS STRING),'|',e.u,'|',b.c))),1000000)) AS rn
    FROM new_ev e JOIN br b ON b.u=e.u
    WHERE b.c <> e.v)
  WHERE rn <= 16
),
seg_new_top AS (
  SELECT u, target_sequence_index, c, 20 AS src_rank, 'new_top2000' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, t.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               'top|',CAST(e.target_sequence_index AS STRING),'|',e.u,'|',t.c))),1000000)) AS rn
    FROM new_ev e CROSS JOIN top2000 t
    LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
    WHERE h.c IS NULL AND t.c <> e.v)
  WHERE rn <= 16
),
seg_new_tail AS (
  SELECT u, target_sequence_index, c, 30 AS src_rank, 'new_tail' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, t.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               'tail|',CAST(e.target_sequence_index AS STRING),'|',e.u,'|',t.c))),1000000)) AS rn
    FROM new_ev e CROSS JOIN tail_samp t
    LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
    WHERE h.c IS NULL AND t.c <> e.v)
  WHERE rn <= 16
),
seg_rep_personal AS (
  SELECT u, target_sequence_index, c, 10 AS src_rank, 'repeat_personal' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, h.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY h.h_cnt DESC, h.h_last DESC) AS rn
    FROM rep_ev e JOIN hist h ON h.u=e.u
    WHERE h.c <> e.v)
  WHERE rn <= 30
),
seg_rep_top AS (
  SELECT u, target_sequence_index, c, 20 AS src_rank, 'repeat_top2000' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, t.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               'rtop|',CAST(e.target_sequence_index AS STRING),'|',e.u,'|',t.c))),1000000)) AS rn
    FROM rep_ev e CROSS JOIN top2000 t
    LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
    WHERE h.c IS NULL AND t.c <> e.v)
  WHERE rn <= 16
),
seg_rep_tail AS (
  SELECT u, target_sequence_index, c, 30 AS src_rank, 'repeat_tail' AS cand_source
  FROM (
    SELECT e.u, e.target_sequence_index, t.c,
           ROW_NUMBER() OVER (
             PARTITION BY e.u, e.target_sequence_index
             ORDER BY MOD(ABS(FARM_FINGERPRINT(CONCAT(
               'rtail|',CAST(e.target_sequence_index AS STRING),'|',e.u,'|',t.c))),1000000)) AS rn
    FROM rep_ev e CROSS JOIN tail_samp t
    LEFT JOIN hist h ON h.u=e.u AND h.c=t.c
    WHERE h.c IS NULL AND t.c <> e.v)
  WHERE rn <= 3
),
{unknown_segment}allc AS (
  SELECT * FROM pos
  UNION ALL SELECT * FROM seg_new_bridge
  UNION ALL SELECT * FROM seg_new_top
  UNION ALL SELECT * FROM seg_new_tail
  UNION ALL SELECT * FROM seg_rep_personal
  UNION ALL SELECT * FROM seg_rep_top
  UNION ALL SELECT * FROM seg_rep_tail
  {unknown_union}
),
dedup AS (
  SELECT u, target_sequence_index, c, cand_source,
         ROW_NUMBER() OVER (
           PARTITION BY u, target_sequence_index, c ORDER BY src_rank) AS dn
  FROM allc
),
clean AS (
  SELECT u, target_sequence_index, c,
         IF(cand_source='positive', 1, 0) AS label, cand_source
  FROM dedup WHERE dn = 1
)
SELECT DATE '{snap}' AS snapshot_date,
       cl.u AS target_address, cl.target_sequence_index, cl.c AS candidate_address,
       cl.label, cl.cand_source,
       IFNULL(g.g_rank, 99999) AS g_rank,
       IFNULL(g.g_cnt, 0) AS g_cnt,
       IFNULL(hh.h_cnt, 0) AS personal_cnt,
       IFNULL(DATE_DIFF(DATE '{snap}', DATE(hh.h_last), DAY), 999) AS days_since,
       IFNULL(br.bridge_paths, 0) AS bridge_paths,
       IFNULL(br.bridge_signal, 0) AS bridge_signal
FROM clean cl
LEFT JOIN gpop g ON g.c=cl.c
LEFT JOIN hist hh ON hh.u=cl.u AND hh.c=cl.c
LEFT JOIN br ON br.u=cl.u AND br.c=cl.c
"""


def union_ctas(select_fn, table, snaps=SNAPS):
    parts = [f"SELECT * FROM ({select_fn(s)})" for s in snaps]
    return (f"CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.{table}`\n"
            "PARTITION BY snapshot_date\nCLUSTER BY target_address AS\n"
            + "\nUNION ALL\n".join(parts))


def query_rows(op, tok, sql, tag):
    r = submit(op, tok, sql)
    jr = wait(op, tok, r["jobReference"]["jobId"], tag)
    # fetch results page
    jid = r["jobReference"]["jobId"]
    for attempt in range(6):
        try:
            res = json.load(op.open(urllib.request.Request(
                f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries/{jid}?maxResults=1000",
                headers={"Authorization": "Bearer " + tok}), timeout=120))
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 5:
                raise
            print(f"  result-fetch retry [{tag}] {e!r}", flush=True)
            time.sleep(2 * (attempt + 1))
    cols = [f["name"] for f in res["schema"]["fields"]]
    rows = [[x["v"] for x in row["f"]] for row in res.get("rows", [])]
    return cols, rows, res.get("totalRows")


def submit_job(op, tok, configuration):
    body = json.dumps({"configuration": configuration}).encode()
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"})
    return json.load(op.open(req, timeout=180))


def export_table(op, tok, table, prefix):
    configuration = {"extract": {
        "sourceTable": {"projectId": PROJECT, "datasetId": DATASET, "tableId": table},
        "destinationUri": f"gs://{BUCKET}/{prefix}*.csv.gz",
        "destinationFormat": "CSV", "compression": "GZIP", "printHeader": True}}
    r = submit_job(op, tok, configuration)
    wait(op, tok, r["jobReference"]["jobId"], f"extract {table}")


def download_prefix(op, tok, prefix, dest):
    os.makedirs(dest, exist_ok=True)
    listing = json.load(op.open(urllib.request.Request(
        f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o?prefix={urllib.parse.quote(prefix)}",
        headers={"Authorization": "Bearer " + tok}), timeout=120))
    paths = []
    for item in listing.get("items", []):
        name = item["name"]
        if name.endswith("/"):
            continue
        data = op.open(urllib.request.Request(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{urllib.parse.quote(name, safe='')}?alt=media",
            headers={"Authorization": "Bearer " + tok}), timeout=600).read()
        fn = os.path.join(dest, name.split("/")[-1])
        open(fn, "wb").write(data)
        paths.append(fn)
        print("  downloaded", fn, len(data), flush=True)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--dest", default="artifacts/llm_panel_v1")
    args = ap.parse_args()

    op = opener()
    tok = token()
    ev_ddl = union_ctas(events_select_sql, "llm_panel_events_v1")
    cand_ddl = union_ctas(candidates_sql, "llm_panel_candidates_v1")

    if args.build:
        run_sql(op, tok, ev_ddl, "llm panel events", dry=args.dry_run)
        run_sql(op, tok, cand_ddl, "llm panel candidates", dry=args.dry_run)
        if args.dry_run:
            return

    if args.verify:
        q1 = """SELECT snapshot_date, cp_type, stratum, activity,
                       COUNT(*) AS n_events,
                       ROUND(AVG(truth_g_rank),1) AS avg_truth_rank,
                       ROUND(AVG(pop_weight),3) AS avg_weight
                FROM `ictdata-507912.exgraph.llm_panel_events_v1`
                GROUP BY 1,2,3,4 ORDER BY 1,2,3,4"""
        cols, rows, total = query_rows(op, tok, q1, "verify strata")
        print("\t".join(cols))
        for r in rows:
            print("\t".join(r))
        q2 = """SELECT snapshot_date,
                       COUNT(DISTINCT CONCAT(CAST(target_sequence_index AS STRING),'|',target_address)) AS events,
                       COUNT(*) AS cand_rows,
                       ROUND(COUNT(*)*1.0/COUNT(DISTINCT CONCAT(CAST(target_sequence_index AS STRING),'|',target_address)),2) AS avg_pool,
                       SUM(label) AS positives,
                       SUM(IF(label=1 AND g_rank>2000,1,0)) AS pos_outside_top2000
                FROM `ictdata-507912.exgraph.llm_panel_candidates_v1`
                GROUP BY 1 ORDER BY 1"""
        cols, rows, _ = query_rows(op, tok, q2, "verify pool")
        print("\t".join(cols))
        for r in rows:
            print("\t".join(r))
        q3 = """SELECT cand_source, COUNT(*) n,
                       ROUND(AVG(g_rank),1) avg_rank
                FROM `ictdata-507912.exgraph.llm_panel_candidates_v1`
                WHERE snapshot_date=DATE '2022-08-01'
                GROUP BY 1 ORDER BY 1"""
        cols, rows, _ = query_rows(op, tok, q3, "verify source aug")
        print("\t".join(cols))
        for r in rows:
            print("\t".join(r))

    if args.export:
        export_table(op, tok, "llm_panel_events_v1", "llm_panel_v1/events/")
        export_table(op, tok, "llm_panel_candidates_v1", "llm_panel_v1/candidates/")
        p1 = download_prefix(op, tok, "llm_panel_v1/events/", args.dest + "/events")
        p2 = download_prefix(op, tok, "llm_panel_v1/candidates/", args.dest + "/candidates")
        manifest = {"events_files": p1, "candidates_files": p2,
                    "per_snapshot": PER_SNAP,
                    "note": "stratified paired LLM panel v1; truth_g_rank is analysis-only"}
        os.makedirs(args.dest, exist_ok=True)
        with open(os.path.join(args.dest, "llm_panel_v1_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        print("export complete:", len(p1), "event files,", len(p2), "candidate files")


if __name__ == "__main__":
    main()
