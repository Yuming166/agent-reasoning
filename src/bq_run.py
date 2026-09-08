#!/usr/bin/env python3
"""Run a BigQuery SQL file or inline query via REST + ADC through the proxy.
Usage: bq_run.py <sql_file> [--dry] [--json-out path]
Prints result rows as TSV. Keeps traffic to metadata/results only.
"""
import argparse, json, os, subprocess, sys, time, urllib.request

GCLOUD = "/storage/gaoym/tools/google-cloud-sdk/bin/gcloud"
PROXY = "http://10.63.0.72:7890"
PROJECT = "ictdata-507912"


def token() -> str:
    env = {**os.environ, "https_proxy": PROXY, "http_proxy": PROXY}
    r = subprocess.run([GCLOUD, "auth", "application-default",
                        "print-access-token"], capture_output=True, text=True, env=env)
    if r.returncode:
        sys.exit(f"token failed: {r.stderr[:300]}")
    return r.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="sql file; default reads stdin")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    sql = open(args.sql).read() if args.sql else sys.stdin.read()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY}))
    tok = token()
    body = json.dumps({"configuration": {"query": {
        "query": sql, "useLegacySql": False, "dryRun": args.dry}}}).encode()
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=body, headers={"Authorization": "Bearer " + tok,
                            "Content-Type": "application/json"})
    r = json.load(op.open(req, timeout=120))
    if args.dry:
        if r["status"].get("errors"):
            print("DRYRUN ERRORS:", json.dumps(r["status"]["errors"])[:1500])
            sys.exit(1)
        print("dryrun OK")
        return
    jid = r["jobReference"]["jobId"]
    for _ in range(180):
        time.sleep(6)
        jr = json.load(op.open(urllib.request.Request(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
            headers={"Authorization": "Bearer " + tok}), timeout=120))
        st = jr["status"]["state"]
        if st == "DONE":
            if jr["status"].get("errorResult"):
                print("FAILED:", json.dumps(jr["status"]["errorResult"])[:1500])
                sys.exit(1)
            q = jr.get("statistics", {}).get("query", {})
            print(f"# done bytesBilled={q.get('totalBytesBilled')} cache={q.get('cacheHit')}", file=sys.stderr)
            break
    # fetch first page of results
    res = json.load(op.open(urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries/{jid}?maxResults=1000",
        headers={"Authorization": "Bearer " + tok}), timeout=120))
    cols = [f["name"] for f in res["schema"]["fields"]]
    print("\t".join(cols))
    for row in res.get("rows", []):
        print("\t".join(x["v"] for x in row["f"]))
    print(f"# totalRows={res.get('totalRows')} returned={len(res.get('rows',[]))}", file=sys.stderr)


if __name__ == "__main__":
    main()
