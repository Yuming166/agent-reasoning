#!/usr/bin/env python3
"""Official-protocol heuristic baselines on EX-Graph Ethereum Link Prediction.

Protocol (graph-level external validation, official split pkls):
  - Graph topology: official LP graph edges (extracted from
    /storage/gaoym/ethereum_with_twitter_features.pkl, 1,709,575 nodes /
    13,170,869 edges) minus positive validation/test edges -> "training
    topology" (matches paper's "remove val/test links" for training).
  - Split: official pkls in vendor/EX-Graph-repo/ethereum_link_prediction/
    (train 842,821 / val 111,582 / test 201,780 positive edges each with an
    equal number of official negatives).
  - Scorers: Common Neighbors, Adamic-Adar, Resource Allocation, Jaccard,
    Preferential Attachment (undirected neighborhood).
  - Metrics: AUC-ROC and Average Precision (AP) on official val/test sets.
    Compared against paper Table 5 self-reported AUC (0.72-0.89).

Notes: this is graph-level validation only; our 27,613 wallets cannot be
mapped into the LP node id space (no released address->LP-node map).
"""
import os, pickle, time, json
import numpy as np
import scipy.sparse as sp
from sklearn.metrics import roc_auc_score, average_precision_score

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SPLIT = os.path.join(os.path.dirname(os.path.dirname(BASE)), "vendor", "EX-Graph-repo", "ethereum_link_prediction")

def load_split(name):
    with open(os.path.join(SPLIT, f"{name}_edge_indices.pkl"), "rb") as f:
        t = pickle.load(f)
    return t.numpy()  # (2, N) int64

def main():
    t0 = time.time()
    edges = np.load(os.path.join(DATA, "exgraph_lp_edges.npz"))
    esrc, edst = edges["src"], edges["dst"]
    n_nodes = 1_709_575
    full = np.unique(np.stack([esrc, edst], axis=1), axis=0)
    print(f"[{time.time()-t0:.1f}s] full edges unique={len(full)} (raw={len(esrc)}) nodes={n_nodes}", flush=True)

    pos_tr = load_split("positive_train")
    neg_tr = load_split("negative_train")
    pos_va = load_split("positive_validation")
    neg_va = load_split("negative_validation")
    pos_te = load_split("positive_test")
    neg_te = load_split("negative_test")
    print(f"[{time.time()-t0:.1f}s] splits: train {pos_tr.shape[1]}, val {pos_va.shape[1]}, test {pos_te.shape[1]}", flush=True)

    # --- audit split vs graph ---
    full_set = set(map(tuple, full.tolist()))
    def overlap(pairs, name):
        pairs_set = set(map(tuple, pairs.T.tolist()))
        return len(pairs_set & full_set)
    audit = {
        "pos_train_in_full_graph": overlap(pos_tr, "pos_train"),
        "pos_val_in_full_graph": overlap(pos_va, "pos_val"),
        "pos_test_in_full_graph": overlap(pos_te, "pos_test"),
        "neg_train_in_full_graph": overlap(neg_tr, "neg_train"),
        "neg_val_in_full_graph": overlap(neg_va, "neg_val"),
        "neg_test_in_full_graph": overlap(neg_te, "neg_test"),
    }
    print("AUDIT split-vs-graph:", json.dumps(audit), flush=True)

    # --- training topology: full graph minus positive val/test edges ---
    removed = set(map(tuple, np.concatenate([pos_va, pos_te], axis=1).T.tolist()))
    keep = np.array([tuple(e) not in removed for e in full], dtype=bool)
    tr_top = full[keep]
    print(f"[{time.time()-t0:.1f}s] training-topology edges={len(tr_top)} (removed {len(full)-len(tr_top)})", flush=True)

    # --- undirected CSR adjacency ---
    both = np.concatenate([tr_top, tr_top[:, ::-1]], axis=0)  # symmetric
    A = sp.csr_matrix((np.ones(len(both)), (both[:, 0], both[:, 1])), shape=(n_nodes, n_nodes))
    A.sum_duplicates()
    print(f"[{time.time()-t0:.1f}s] CSR built nnz={A.nnz}", flush=True)

    nbrs = [A.indices[A.indptr[i]:A.indptr[i+1]] for i in range(n_nodes)]
    deg = np.diff(A.indptr).astype(np.float64)
    log_deg = np.log(np.maximum(deg, 1.0))
    inv_deg = 1.0 / np.maximum(deg, 1.0)

    def score_pairs(pairs, method):
        """Return scores for an (2,N) array of node pairs."""
        u = pairs[0]; v = pairs[1]
        n = len(u)
        out = np.zeros(n, dtype=np.float64)
        for i in range(n):
            nu = nbrs[u[i]]; nv = nbrs[v[i]]
            if len(nu) == 0 or len(nv) == 0:
                continue
            common = np.intersect1d(nu, nv, assume_unique=True)
            if len(common) == 0:
                continue
            if method == "CN":
                out[i] = len(common)
            elif method == "AA":
                out[i] = (1.0 / log_deg[common]).sum()
            elif method == "RA":
                out[i] = inv_deg[common].sum()
            elif method == "Jaccard":
                out[i] = len(common) / (deg[u[i]] + deg[v[i]] - len(common))
            else:
                raise ValueError(method)
        return out

    def pa_scores(pairs):
        return deg[pairs[0]] * deg[pairs[1]]

    methods = ["CN", "AA", "RA", "Jaccard"]
    results = {}
    for split_name, pos, neg in [("val", pos_va, neg_va), ("test", pos_te, neg_te)]:
        for method in methods + ["PA"]:
            ts = time.time()
            if method == "PA":
                spos = pa_scores(pos); sneg = pa_scores(neg)
            else:
                spos = score_pairs(pos, method); sneg = score_pairs(neg, method)
            y = np.concatenate([np.ones(len(spos)), np.zeros(len(sneg))])
            s = np.concatenate([spos, sneg])
            auc = float(roc_auc_score(y, s))
            ap = float(average_precision_score(y, s))
            support = float(np.mean(s > 0))
            results[f"{split_name}_{method}"] = {"AUC": auc, "AP": ap, "support_frac": support,
                                                  "time_s": round(time.time() - ts, 2)}
            print(f"[{time.time()-t0:.1f}s] {split_name} {method}: AUC={auc:.4f} AP={ap:.4f} support={support:.3f}", flush=True)

    # --- persistence ---
    out = {
        "benchmark": "EX-Graph Ethereum Link Prediction (official split, graph-level external validation)",
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0; EX-Graph paper Table 5 (ICLR 2024)",
        "paper_table5_auc": {"DeepWalk": 0.72, "GCN": 0.76, "GraphSAGE_woX": 0.84, "APPNP_withX": 0.89},
        "graph": {"nodes": int(n_nodes), "full_edges": int(len(full)), "training_topology_edges": int(len(tr_top))},
        "split_sizes": {"train_pos": int(pos_tr.shape[1]), "val_pos": int(pos_va.shape[1]), "test_pos": int(pos_te.shape[1])},
        "audit_split_vs_graph": audit,
        "results": results,
        "notes": [
            "graph-level external validation only; 27,613-wallet mapping into LP node space unavailable",
            "undirected neighborhood used for heuristics",
            "training topology = official graph edges minus official positive val/test edges (no future leakage)",
        ],
    }
    out_path = os.path.join(BASE, "exgraph_lp_heuristics_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved {out_path}", flush=True)

if __name__ == "__main__":
    main()
