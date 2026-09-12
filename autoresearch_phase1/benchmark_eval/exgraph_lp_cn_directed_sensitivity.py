#!/usr/bin/env python3
"""Directed-neighborhood sensitivity check for Common Neighbors on EX-Graph LP.

Uses out-neighbor (directed) adjacency on the training topology and evaluates
the official test/val split. Mirrors exgraph_lp_heuristics.py but only for CN.
"""
import os, pickle, time, json
import numpy as np
import scipy.sparse as sp
from sklearn.metrics import roc_auc_score, average_precision_score

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SPLIT = os.path.join(os.path.dirname(os.path.dirname(BASE)), "vendor", "EX-Graph-repo", "ethereum_link_prediction")
N = 1_709_575

def load_split(name):
    with open(os.path.join(SPLIT, f"{name}_edge_indices.pkl"), "rb") as f:
        return pickle.load(f).numpy()

def main():
    t0 = time.time()
    edges = np.load(os.path.join(DATA, "exgraph_lp_edges.npz"))
    full = np.unique(np.stack([edges["src"], edges["dst"]], axis=1), axis=0)
    pos_va = load_split("positive_validation"); pos_te = load_split("positive_test")
    removed = set(map(tuple, np.concatenate([pos_va, pos_te], axis=1).T.tolist()))
    keep = np.array([tuple(e) not in removed for e in full], dtype=bool)
    tr_top = full[keep]
    A = sp.csr_matrix((np.ones(len(tr_top)), (tr_top[:, 0], tr_top[:, 1])), shape=(N, N))
    A.sum_duplicates()
    nbrs = [A.indices[A.indptr[i]:A.indptr[i+1]] for i in range(N)]
    print(f"[{time.time()-t0:.1f}s] directed CSR nnz={A.nnz}", flush=True)

    for split_name, pos, neg in [("val", pos_va, load_split("negative_validation")),
                                 ("test", pos_te, load_split("negative_test"))]:
        out = np.zeros(pos.shape[1]); nn = len(pos[0])
        for i in range(nn):
            nu = nbrs[pos[0][i]]; nv = nbrs[pos[1][i]]
            if len(nu) and len(nv):
                out[i] = len(np.intersect1d(nu, nv, assume_unique=True))
        on = np.zeros(neg.shape[1])
        for i in range(len(neg[0])):
            nu = nbrs[neg[0][i]]; nv = nbrs[neg[1][i]]
            if len(nu) and len(nv):
                on[i] = len(np.intersect1d(nu, nv, assume_unique=True))
        y = np.concatenate([np.ones(len(out)), np.zeros(len(on))]); s = np.concatenate([out, on])
        res = {"AUC": float(roc_auc_score(y, s)), "AP": float(average_precision_score(y, s)),
               "support_frac": float(np.mean(s > 0)), "time_s": round(time.time()-t0, 2)}
        print(f"[{time.time()-t0:.1f}s] directed CN {split_name}: {res}", flush=True)
        with open(os.path.join(BASE, f"exgraph_lp_cn_directed_{split_name}.json"), "w") as f:
            json.dump(res, f, indent=2)

if __name__ == "__main__":
    main()
