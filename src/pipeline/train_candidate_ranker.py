#!/usr/bin/env python3
"""Stage B: learned new-counterparty ranker.

Downloads nc_ranker_samples_v2 (gzip CSV via GCS) into a local working dir,
fits HistGradientBoosting on pair features (global popularity, personal
interaction/recency, 2-hop bridge signal/paths), trains on June, tunes on
July, reports frozen-August pooled MRR / Recall@K per event, plus conditional
metrics against the global-popularity ordering. Writes artifacts to
artifacts/nc_v1/learned_ranker_v1.json and a per-event August score file
used by stage C.
"""
import argparse, glob, json, os, subprocess, sys, time, urllib.parse, urllib.request

import numpy as np
import pandas as pd

GCLOUD = os.environ.get("GCLOUD_BIN", "gcloud")
PROXY = "http://10.63.0.72:7890"
PROJECT = "ictdata-507912"
TABLE = "nc_ranker_samples_v2"
BUCKET = "ictdata-exgraph-artifacts"

FEATS = ["g_rank", "g_cnt", "personal_cnt", "days_since",
         "bridge_paths", "bridge_signal"]


def token():
    env = {**os.environ, "https_proxy": PROXY, "http_proxy": PROXY}
    return subprocess.run([GCLOUD, "auth", "application-default",
                           "print-access-token"], capture_output=True,
                          text=True, env=env).stdout.strip()


def submit(op, tok, body):
    req = urllib.request.Request(
        f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return json.load(op.open(req, timeout=120))


def wait(op, tok, jid):
    for _ in range(300):
        time.sleep(5)
        jr = json.load(op.open(urllib.request.Request(
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/jobs/{jid}",
            headers={"Authorization": "Bearer " + tok}), timeout=120))
        if jr["status"]["state"] == "DONE":
            if jr["status"].get("errorResult"):
                raise RuntimeError(jr["status"]["errorResult"])
            return jr


def export_and_download(op, tok, workdir):
    os.makedirs(workdir, exist_ok=True)
    prefix = "nc_ranker_samples_v2/"
    body = {"configuration": {"extract": {
        "sourceTable": {"projectId": PROJECT, "datasetId": "exgraph", "tableId": TABLE},
        "destinationUri": f"gs://{BUCKET}/{prefix}*.csv.gz",
        "destinationFormat": "CSV", "compression": "GZIP", "printHeader": True}}}
    r = submit(op, tok, body)
    wait(op, tok, r["jobReference"]["jobId"])
    listing = json.load(op.open(urllib.request.Request(
        f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o?prefix={prefix}",
        headers={"Authorization": "Bearer " + tok}), timeout=120))
    paths = []
    for item in listing.get("items", []):
        fn = os.path.join(workdir, item["name"].split("/")[-1])
        data = op.open(urllib.request.Request(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{urllib.parse.quote(item['name'], safe='')}?alt=media",
            headers={"Authorization": "Bearer " + tok}), timeout=600).read()
        open(fn, "wb").write(data)
        paths.append(fn)
        print("  downloaded", fn, len(data), flush=True)
    return paths


def pooled_metrics(df, score_col, klist=(1, 5, 10)):
    df = df.sort_values(["snapshot_date", "u", "target_sequence_index", score_col],
                        ascending=[True, True, True, False])
    # rank = position within event group
    df = df.copy()
    df["r"] = df.groupby(["snapshot_date", "u", "target_sequence_index"]).cumcount() + 1
    pos = df[df.label == 1]
    out = {"n_events": int(len(pos))}
    out["MRR"] = float((1.0 / pos.r).mean())
    for k in klist:
        out[f"Recall@{k}"] = float((pos.r <= k).mean())
    return out, pos[["snapshot_date", "u", "target_sequence_index", "r"]].rename(
        columns={"r": score_col + "_rank"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/tmp/ranker")
    args = ap.parse_args()
    from sklearn.ensemble import HistGradientBoostingClassifier
    op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": PROXY}))
    tok = token()
    if not glob.glob(os.path.join(args.workdir, "*.csv.gz")):
        export_and_download(op, tok, args.workdir)
    print("loading...", flush=True)
    df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(args.workdir, "*.csv.gz")))],
                   ignore_index=True)
    print("rows", len(df), df.snapshot_date.value_counts().to_dict(), flush=True)
    for c in FEATS:
        df[c] = df[c].replace([np.inf, -np.inf], np.nan).fillna(0)
    tr = df[df.snapshot_date == "2022-06-01"]
    va = df[df.snapshot_date == "2022-07-01"]
    te = df[df.snapshot_date == "2022-08-01"]

    # tune on July
    best = None
    for lr in (0.03, 0.05, 0.1):
        for leaves in (15, 31, 63):
            m = HistGradientBoostingClassifier(max_iter=300, learning_rate=lr,
                max_leaf_nodes=leaves, min_samples_leaf=50, l2_regularization=1.0,
                random_state=7)
            m.fit(tr[FEATS], tr.label)
            va2 = va.copy(); va2["s"] = m.predict_proba(va[FEATS])[:, 1]
            mm, _ = pooled_metrics(va2, "s")
            if best is None or mm["MRR"] > best[0]:
                best = (mm["MRR"], lr, leaves)
    _, lr, leaves = best
    print("best val:", best, flush=True)
    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=lr,
        max_leaf_nodes=leaves, min_samples_leaf=50, l2_regularization=1.0,
        random_state=7)
    model.fit(pd.concat([tr, va])[FEATS], pd.concat([tr, va]).label)

    # frozen august: score learned model and baselines
    out = te.copy()
    out["s_learned"] = model.predict_proba(te[FEATS])[:, 1]
    out["s_global"] = -te.g_rank.astype(float)          # lower rank better
    out["s_bridge"] = te.bridge_signal.astype(float)
    res = {"tune": {"val_MRR": best[0], "lr": lr, "max_leaf_nodes": leaves}}
    ranks = {}
    for col, nm in [("s_learned", "learned"), ("s_global", "global"),
                    ("s_bridge", "bridge_only")]:
        mm, pos = pooled_metrics(out[["snapshot_date", "u", "target_sequence_index",
                                      "label", col]], col)
        res[nm] = mm
        ranks[nm] = pos
    # paired: learned vs global rank on each event
    j = ranks["learned"].merge(ranks["global"], on=["snapshot_date", "u", "target_sequence_index"])
    j["lr"] = j["s_learned_rank"]; j["gr"] = j["s_global_rank"]
    res["paired_learned_vs_global"] = {
        "learned_wins": int((j.lr < j.gr).sum()),
        "global_wins": int((j.gr < j.lr).sum()),
        "ties": int((j.lr == j.gr).sum()),
        "mean_rank_learned": float(j.lr.mean()),
        "mean_rank_global": float(j.gr.mean())}
    # feature importance via permutation (MRR drop)
    rng = np.random.default_rng(0)
    base = res["learned"]["MRR"]
    imp = {}
    for c in FEATS:
        Xc = te[FEATS].copy()
        Xc[c] = rng.permutation(Xc[c].to_numpy())
        tmp = te[["snapshot_date", "u", "target_sequence_index", "label"]].copy()
        tmp["s_p"] = model.predict_proba(Xc)[:, 1]
        mm, _ = pooled_metrics(tmp, "s_p")
        imp[c] = base - mm["MRR"]
    res["permutation_MRR_drop"] = dict(sorted(imp.items(), key=lambda kv: -kv[1]))

    os.makedirs("artifacts/nc_v1", exist_ok=True)
    json.dump(res, open("artifacts/nc_v1/learned_ranker_v1.json", "w"), indent=2)
    # save learned positive ranks for stage C
    j.to_csv("artifacts/nc_v1/aug_event_ranks_learned_vs_global.csv", index=False)
    print(json.dumps({k: v for k, v in res.items() if isinstance(v, dict) and "MRR" in v}, indent=2))


if __name__ == "__main__":
    main()
