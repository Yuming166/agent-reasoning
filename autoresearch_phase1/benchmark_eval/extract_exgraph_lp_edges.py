#!/usr/bin/env python3
"""Extract only the edge arrays from the official EX-Graph LP DGL pickle.

Loads /storage/gaoym/ethereum_with_twitter_features.pkl (37.3 GB, DGL graph,
1,709,575 nodes / 13,170,869 edges) with dgl (present in .venv-35gb) and dumps
compact (src, dst) arrays to research/benchmark_eval/data/exgraph_lp_edges.npz.

This is a read-only extraction; the source pickle is not modified.
"""
import pickle, time, os
import numpy as np

SRC = "/storage/gaoym/ethereum_with_twitter_features.pkl"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exgraph_lp_edges.npz")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

t0 = time.time()
with open(SRC, "rb") as f:
    G = pickle.load(f)
print(f"[{time.time()-t0:.1f}s] loaded DGL graph: nodes={G.num_nodes()} edges={G.num_edges()}", flush=True)

src, dst = G.edges()
src = src.numpy().astype(np.int64)
dst = dst.numpy().astype(np.int64)
print(f"[{time.time()-t0:.1f}s] edges(): src dtype={src.dtype} n={len(src)}", flush=True)

np.savez_compressed(OUT, src=src, dst=dst)
print(f"[{time.time()-t0:.1f}s] saved {OUT} ({os.path.getsize(OUT)} bytes)", flush=True)
