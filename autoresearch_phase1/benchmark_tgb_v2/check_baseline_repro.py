#!/usr/bin/env python3
"""Protocol check: run the ORIGINAL 7-feature baseline model through the new
prefix-based eval path; compare val MRR to the recorded 0.7611."""
import os, os.path as osp, math, time
import numpy as np
import torch
from tgb.linkproppred.dataset import LinkPropPredDataset
from tgb.linkproppred.evaluate import Evaluator
from tgb_features import PrefixGraphFeatures

OUT = osp.dirname(osp.abspath(__file__))
BENCH = osp.join(osp.dirname(OUT), "benchmark_eval")
DEV = "cuda:5"

class MLP7(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(7, 256), torch.nn.ReLU(), torch.nn.Dropout(0.1),
            torch.nn.Linear(256, 256), torch.nn.ReLU(),
            torch.nn.Linear(256, 1))
    def forward(self, x):
        return self.net(x).squeeze(-1)

t0 = time.time()
dataset = LinkPropPredDataset(name="tgbl-coin", root="datasets", preprocess=True)
data = dataset.full_data
s = data["sources"].astype(np.int64); d = data["destinations"].astype(np.int64)
t = data["timestamps"].astype(np.int64)
metric = dataset.eval_metric
va = dataset.val_mask
feat = PrefixGraphFeatures(s, d, t, tau_node=7*86400, tau_pair=86400)
print(f"build {time.time()-t0:.1f}s")
scaler = np.load(osp.join(BENCH, "tgb_mlp_train_scaler.npz"))
mean, std = scaler["mean"], scaler["std"]
model = MLP7().to(DEV)
model.load_state_dict(torch.load(osp.join(BENCH, "tgb_mlp_val.pt"), map_location=DEV))
model.eval()

# 7 baseline features from prefix engine: pair_count,pair_gap,has_pair,
#   src_total,src_gap,dst_total,dst_gap  -> cols 12,13,14,0,1,6,7
cols = [12, 13, 14, 0, 1, 6, 7]

evaluator = Evaluator(name="tgbl-coin")
neg_sampler = dataset.negative_sampler
idx = np.where(va)[0]
order = np.argsort(t[idx], kind="mergesort"); idx = idx[order]
BATCH = 1000
nb = math.ceil(len(idx)/BATCH)
perf = []
dataset.load_val_ns()
for bi in range(nb):
    sl = idx[bi*BATCH:(bi+1)*BATCH]
    pos_src, pos_dst, pos_t = s[sl], d[sl], t[sl]
    negs = neg_sampler.query_batch(pos_src, pos_dst, pos_t, split_mode="val")
    total = sum(len(n)+1 for n in negs)
    U = np.empty(total, np.int64); V = np.empty(total, np.int64); T = np.empty(total, np.int64)
    off = 0
    for j in range(len(sl)):
        k = len(negs[j])+1
        U[off:off+k] = pos_src[j]; V[off] = pos_dst[j]
        V[off+1:off+k] = np.asarray(negs[j], np.int64); T[off:off+k] = pos_t[j]
        off += k
    F = feat.features(U, V, T)[:, cols]
    F = (F - mean) / std
    with torch.no_grad():
        scores = torch.sigmoid(model(torch.tensor(F).to(DEV))).cpu().numpy()
    off = 0
    for j in range(len(sl)):
        k = len(negs[j])+1
        inp = {"y_pred_pos": scores[off:off+1], "y_pred_neg": scores[off+1:off+k], "eval_metric": [metric]}
        perf.append(evaluator.eval(inp)[metric])
        off += k
    if bi % 500 == 0:
        print(f"batch {bi}/{nb} cur_mrr={np.mean(perf):.4f}", flush=True)
print("PREFIX-based val MRR (7-feature baseline model):", float(np.mean(perf)))
print("Recorded streaming val MRR: 0.76105696")
