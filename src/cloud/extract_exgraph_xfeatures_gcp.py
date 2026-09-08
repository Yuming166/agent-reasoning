#!/usr/bin/env python3
"""Run INSIDE a GCP VM (e.g. us-central1 highmem spot). Google Drive -> GCE
and GCE -> BigQuery/GCS stay on Google's internal network; no jump-host traffic.

Steps:
  1. gdown the 34.8 GiB `ethereum_with_twitter_features.pkl` (Drive file id
     1q3KX_b3M2wImFvFMP-15CcPKdVOeuSw-) to a RAM/tmp disk path.
  2. Load with DGL; recover node_id -> address from edge data
     (from_address/to_address); export per-node:
       ethereum_features (8-d), X part of combined features (last 16-d),
       non-zero-X flag, and address.
  3. Write a compact Parquet/CSV to GCS, then (optionally) load into BigQuery
     ictdata-507912.exgraph.eth_node_x_features_v1.
  4. Print a small JSON manifest; delete the pkl afterwards.

Memory: 34.8 GiB pickle + DGL overhead -> use a 104+ GB RAM VM (n2-highmem-16).
The script never ships the raw file anywhere.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time

DRIVE_ID = "1q3KX_b3M2wImFvFMP-15CcPKdVOeuSw-"
LOCAL_PKL = "/tmp/ethereum_with_twitter_features.pkl"


def sh(cmd: str, check: bool = True) -> str:
    print("+", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and r.returncode != 0:
        sys.exit(f"command failed ({r.returncode}): {cmd}\n{r.stderr[-2000:]}")
    return r.stdout + r.stderr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcs-out", default="gs://ictdata-exgraph/eth_node_x_features_v1/")
    ap.add_argument("--bq-table", default="ictdata-507912.exgraph.eth_node_x_features_v1")
    ap.add_argument("--keep-pkl", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    manifest: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    sh("pip install -q gdown dgl torch pyarrow pandas google-cloud-bigquery")
    if not os.path.exists(LOCAL_PKL):
        sh(f"gdown --id {DRIVE_ID} -O {LOCAL_PKL}")  # GCE<->Drive is in-Google
    manifest["pkl_bytes"] = os.path.getsize(LOCAL_PKL)

    import pickle, numpy as np, pandas as pd, torch, dgl  # noqa
    with open(LOCAL_PKL, "rb") as f:
        g = pickle.load(f)
    n = g.num_nodes()
    manifest.update(num_nodes=n, num_edges=g.num_edges(),
                    ndata_keys=sorted(g.ndata.keys()),
                    edata_keys=sorted(g.edata.keys()))

    # --- recover node_id -> address from edge data ---------------------------
    src, dst = g.edges()
    addr = np.full(n, None, dtype=object)
    ed = g.edata
    fk = next((k for k in ("from_address", "from") if k in ed), None)
    tk = next((k for k in ("to_address", "to") if k in ed), None)
    if fk is None or tk is None:
        sys.exit(f"no address edge fields found; edata={list(ed.keys())}")
    fa = np.asarray(ed[fk]).astype(str); ta = np.asarray(ed[tk]).astype(str)
    addr[src.numpy()] = fa; addr[dst.numpy()] = ta
    manifest["nodes_with_address"] = int((addr != None).sum())

    # --- features -------------------------------------------------------------
    comb = np.asarray(g.ndata["ethereum_twitter_combined_features"], dtype=np.float32)
    ethf = np.asarray(g.ndata["ethereum_features"], dtype=np.float32)
    xpart = comb[:, ethf.shape[1]:]  # trailing 16 dims = X (semantic+structure)
    x_nonzero = (np.abs(xpart).sum(axis=1) > 0)
    manifest.update(combined_dim=comb.shape[1], eth_dim=ethf.shape[1],
                    x_dim=xpart.shape[1], nodes_with_x_features=int(x_nonzero.sum()))

    df = pd.DataFrame({
        "eth_node_id": np.arange(n, dtype=np.int64),
        "ethereum_address": addr,
        "has_x_features": x_nonzero,
    })
    for i in range(ethf.shape[1]):
        df[f"eth_f{i}"] = ethf[:, i]
    for i in range(xpart.shape[1]):
        df[f"x_f{i}"] = xpart[:, i]
    df = df[df["ethereum_address"].notna()].copy()
    df["ethereum_address"] = df["ethereum_address"].str.lower()

    out_parquet = "/tmp/eth_node_x_features_v1.parquet"
    df.to_parquet(out_parquet, index=False)
    manifest["parquet_rows"] = len(df)
    manifest["parquet_bytes"] = os.path.getsize(out_parquet)

    sh(f"gsutil -m cp {out_parquet} {args.gcs_out}")
    sh(f"bq load --source_format=PARQUET --replace --autodetect "
       f"{args.bq_table} {args.gcs_out}eth_node_x_features_v1.parquet")
    if not args.keep_pkl:
        os.remove(LOCAL_PKL)
    manifest["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
