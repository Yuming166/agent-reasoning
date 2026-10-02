#!/usr/bin/env python3
"""TGB tgbl-coin-v2 EdgeBank baseline (official heuristic, numpy-only).

Adapted from TGB official example examples/linkproppred/tgbl-coin/edgebank.py
(commit 3b83e5c), minus the unused torch_geometric import. Uses the official
LinkPropPredDataset, official NegativeEdgeSampler and official Evaluator on the
official fixed split -> MRR on val/test is directly comparable to the TGB
leaderboard "Heuristic (LocalRecencyLocalPopularity) 0.774" entry.

Run with .venv-cuda (py-tgb 2.3.0 installed; no torch_geometric needed).
"""
import timeit, math, os, os.path as osp, json, sys
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


from tgb.linkproppred.evaluate import Evaluator
from tgb.utils.utils import set_random_seed
from tgb.linkproppred.dataset import LinkPropPredDataset
from tgb_edgebank_predictor_official import EdgeBankPredictor

SEED = 1
BATCH_SIZE = 200
K_VALUE = 10
TIME_WINDOW_RATIO = 0.15
DATA = "tgbl-coin"
OUT_DIR = osp.dirname(osp.abspath(__file__))

def test(data, test_mask, neg_sampler, edgebank, evaluator, metric, split_mode):
    num_batches = math.ceil(len(data['sources'][test_mask]) / BATCH_SIZE)
    perf_list = []
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(data['sources'][test_mask]))
        pos_src, pos_dst, pos_t = (
            data['sources'][test_mask][start_idx:end_idx],
            data['destinations'][test_mask][start_idx:end_idx],
            data['timestamps'][test_mask][start_idx:end_idx],
        )
        neg_batch_list = neg_sampler.query_batch(pos_src, pos_dst, pos_t, split_mode=split_mode)
        for idx, neg_batch in enumerate(neg_batch_list):
            query_src = np.array([int(pos_src[idx]) for _ in range(len(neg_batch) + 1)])
            query_dst = np.concatenate([np.array([int(pos_dst[idx])]), neg_batch])
            y_pred = edgebank.predict_link(query_src, query_dst)
            input_dict = {"y_pred_pos": np.array([y_pred[0]]), "y_pred_neg": np.array(y_pred[1:]),
                          "eval_metric": [metric]}
            perf_list.append(evaluator.eval(input_dict)[metric])
        edgebank.update_memory(pos_src, pos_dst, pos_t)
        if batch_idx % 2000 == 0:
            print(f"  {split_mode} batch {batch_idx}/{num_batches} cur_mrr={np.mean(perf_list):.4f}", flush=True)
    return float(np.mean(perf_list))

set_random_seed(SEED)

for mem_mode in ["unlimited", "fixed_time_window"]:
    t_start = timeit.default_timer()
    dataset = LinkPropPredDataset(name=DATA, root="datasets", preprocess=True)
    data = dataset.full_data
    metric = dataset.eval_metric
    train_mask = dataset.train_mask
    val_mask = dataset.val_mask
    test_mask = dataset.test_mask

    hist_src = np.concatenate([data['sources'][train_mask]])
    hist_dst = np.concatenate([data['destinations'][train_mask]])
    hist_ts = np.concatenate([data['timestamps'][train_mask]])

    edgebank = EdgeBankPredictor(hist_src, hist_dst, hist_ts, memory_mode=mem_mode,
                                 time_window_ratio=TIME_WINDOW_RATIO)
    evaluator = Evaluator(name=DATA)
    neg_sampler = dataset.negative_sampler

    # val
    dataset.load_val_ns()
    val_mrr = test(data, val_mask, neg_sampler, edgebank, evaluator, metric, "val")
    print(f"EdgeBank-{mem_mode} val MRR: {val_mrr:.4f}", flush=True)

    # test (memory continues from val; official streaming)
    dataset.load_test_ns()
    test_mrr = test(data, test_mask, neg_sampler, edgebank, evaluator, metric, "test")
    print(f"EdgeBank-{mem_mode} test MRR: {test_mrr:.4f}", flush=True)

    res = {"model": "EdgeBank", "memory_mode": mem_mode, "data": DATA, "seed": SEED,
           "metric": metric, "val_mrr": val_mrr, "test_mrr": test_mrr,
           "total_time_s": round(timeit.default_timer() - t_start, 2),
           "leaderboard_reference": "Heuristic(LocalRecencyLocalPopularity) MRR 0.774 (2026-01-20, tgb.complexdatalab.com)"}
    with open(osp.join(OUT_DIR, f"tgb_edgebank_{mem_mode}_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2), flush=True)
