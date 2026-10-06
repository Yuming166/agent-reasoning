#!/usr/bin/env python
"""Error-analysis tables for the retrieval-track baselines (G2.2).

Stratifies the four error categories by wallet concentration and target
popularity, per split and per baseline, using the same release evaluator
per-query output as BASELINES_RETRIEVAL.json. Read-only over VERSIONED_DATASET
and the legal-domain index; deterministic; writes one new artifact.

Output (first-write only):
  artifacts/benchmark_release_candidate_v1_20261006/ERROR_ANALYSIS_RETRIEVAL.json
"""
from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
sys.path.insert(0, str(R / "research/benchmark_release_candidate_v1_20261006"))
from benchmark_evaluator import FirstSeenDomain, evaluate_forecast, read_jsonl  # noqa: E402
from run_retrieval_baselines import (  # noqa: E402
    DS, K, SEED, frequency_rank, history_counterparts, load_domain,
    random_legal_rank, recency_rank)

OUT = R / "artifacts/benchmark_release_candidate_v1_20261006/ERROR_ANALYSIS_RETRIEVAL.json"


def quintile_label(rank_value, edges):
    for i, e in enumerate(edges):
        if rank_value <= e:
            return i
    return len(edges) - 1


def main():
    domain = load_domain()
    report = {"schema": "error-analysis-retrieval-v1", "date": "2026-10-06",
              "seed_random_legal": SEED, "track": "retrieval", "k": K,
              "note": "four-category errors stratified by target popularity "
                      "(prior-wallet counterpart rank) and by wallet history size; "
                      "same evaluator per-query output as BASELINES_RETRIEVAL.json",
              "splits": {}}
    for split in ("train", "dev", "test"):
        queries = read_jsonl(DS / f"queries/{split}.jsonl")
        gold = read_jsonl(DS / f"forecast_gold/{split}.jsonl")
        hist = history_counterparts(split)
        # target popularity: how many OTHER sampled wallets transacted with the
        # target before their own cutoff (cross-wallet prior frequency). Computed
        # from this split's history only (cutoff-safe: uses each sender's own
        # pre-cutoff parents).
        send_edges = collections.Counter()  # counterparty -> distinct wallets
        wallet_of_edge = collections.defaultdict(set)
        for wallet, seq in hist.items():
            for t, tos in seq:
                for a in tos:
                    wallet_of_edge[a].add(wallet)
        for a in wallet_of_edge:
            send_edges[a] = len(wallet_of_edge[a])
        gmap = {g["query_id"]: g for g in gold}
        targets = {}
        for q in queries:
            g = gmap[q["query_id"]]
            if g["active_eligible_external_attempt"] and g.get("target_address"):
                targets[q["query_id"]] = g["target_address"]
        pop_values = sorted(send_edges.get(t, 0) for t in set(targets.values()))
        qs = np.quantile(pop_values, [0.2, 0.4, 0.6, 0.8]) if pop_values else []
        # per-wallet history size strata
        hsize = {w: len(s) for w, s in hist.items()}
        hsizes = sorted(hsize.get(q["wallet_id"], 0) for q in queries)
        hq = np.quantile(hsizes, [0.2, 0.4, 0.6, 0.8]) if hsizes else []

        rng = np.random.default_rng(SEED)
        per_baseline = {}
        for name in ("frequency", "recency", "random_legal"):
            preds = []
            for q in queries:
                cutoff = q["cutoff_UTC_seconds"]
                if name == "frequency":
                    scores, addrs = frequency_rank(hist, q["wallet_id"], cutoff, domain, K)
                elif name == "recency":
                    scores, addrs = recency_rank(hist, q["wallet_id"], cutoff, domain, K)
                else:
                    scores, addrs = random_legal_rank(domain, cutoff, rng, K)
                preds.append(dict(query_id=q["query_id"], ranked_candidate_ids=addrs,
                                  scores=scores))
            res = evaluate_forecast(queries, gold, preds, domain, track="retrieval")
            # stratify per-query categories
            strat_pop = collections.Counter()
            strat_wallet = collections.Counter()
            for row in res["per_query"]:
                if not row.get("active") or row.get("error_category") is None:
                    continue
                cat = row["error_category"]
                t = targets.get(row["query_id"])
                if t is None:
                    continue
                pop_q = quintile_label(send_edges.get(t, 0), qs)
                strat_pop[f"pop_q{pop_q}|{cat}"] += 1
                wq = quintile_label(hsize.get(row["wallet_id"], 0), hq)
                strat_wallet[f"hist_q{wq}|{cat}"] += 1
            per_baseline[name] = {
                "summary": res["summary"],
                "by_target_popularity_quintile": dict(strat_pop),
                "by_wallet_history_size_quintile": dict(strat_wallet),
                "target_popularity_quintile_edges(distinct_wallets)": [float(x) for x in qs],
                "wallet_history_quintile_edges(parents)": [float(x) for x in hq],
            }
        report["splits"][split] = per_baseline
        print(split, "done")

    if OUT.exists():
        raise SystemExit(f"exists: {OUT}")
    with open(OUT, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
