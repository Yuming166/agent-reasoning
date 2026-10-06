#!/usr/bin/env python
"""Training-free retrieval-track baselines for eth-actions-benchmark.

Three baselines score every query's history (strictly timestamp < cutoff, read
only from VERSIONED_DATASET parent actions) and rank candidate addresses:

  frequency     — most frequent historical wallet-initiated external counterpart
  recency       — most recent wallet-initiated external counterpart (ties:
                  later first)
  random_legal  — seeded random sample of the legal visible domain
                  (first_seen < cutoff), seed 20261006

All predictions are emitted through the SAME canonical order rule as the frozen
scorer (descending score, ascending address) and evaluated with the release
benchmark_evaluator on the retrieval track (fail-closed legality gate), on all
three splits. Deterministic; no training, no API, no chain access.

Output (first-write only):
  artifacts/benchmark_release_candidate_v1_20261006/BASELINES_RETRIEVAL.json
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
sys.path.insert(0, str(R / "research/benchmark_release_candidate_v1_20261006"))
from benchmark_evaluator import FirstSeenDomain, evaluate_forecast, read_jsonl  # noqa: E402

DS = R / "artifacts/benchmark_release_candidate_v1_20261006/VERSIONED_DATASET"
OUT = R / "artifacts/benchmark_release_candidate_v1_20261006/BASELINES_RETRIEVAL.json"
K = 50
SEED = 20261006
ZERO = "0x" + "0" * 40


def load_domain():
    rows = []
    with gzip.open(DS / "candidate_index/legal_domain_index.jsonl.gz", "rt") as f:
        header = json.loads(f.readline())
        assert header["schema"] == "legal-domain-first-seen-v1"
        for line in f:
            r = json.loads(line)
            rows.append((r["address"], r["first_seen_UTC_seconds"]))
    return FirstSeenDomain(dict(rows))


def history_counterparts(split):
    """Per (wallet_view, parent) wallet-initiated external counterpart, deduped
    within the parent (multiple external rows of one parent count once), with
    the parent's canonical time. Excludes the wallet itself and ZERO."""
    events = {}  # (wallet, parent) -> (time, set of to_address)
    with gzip.open(DS / f"parent_actions/{split}.jsonl.gz", "rt") as f:
        json.loads(f.readline())
        for line in f:
            p = json.loads(line)
            wallet = p["wallet_view"]
            ext = p["canonical_observed_action"]["external_rows"]
            if not ext:
                continue
            tos = {r["to_address"] for r in ext
                   if r.get("to_address") and r["to_address"] != wallet and r["to_address"] != ZERO
                   and (r.get("from_address") == wallet)}
            if not tos:
                continue
            events[(wallet, p["parent_id"])] = (int(p["time"]), tos)
    per_wallet = {}
    for (wallet, _parent), (t, tos) in events.items():
        per_wallet.setdefault(wallet, []).append((t, tos))
    for wallet in per_wallet:
        per_wallet[wallet].sort()  # ascending time; last element = most recent
    return per_wallet


def frequency_rank(per_wallet_history, wallet, cutoff, domain, n):
    """Score = count of distinct-parent wallet-initiated sends before cutoff.
    Canonical order breaks ties by address."""
    scores, addrs = [], []
    agg = Counter()
    for t, tos in per_wallet_history.get(wallet, ()):
        if t < cutoff:
            for a in tos:
                agg[a] += 1
    items = sorted(agg.items())  # ascending address for deterministic tie-break
    items.sort(key=lambda x: -x[1])
    for a, s in items[:n]:
        if domain.is_legal(a, cutoff):
            addrs.append(a)
            scores.append(float(s))
    return scores, addrs


def recency_rank(per_wallet_history, wallet, cutoff, domain, n):
    """Score = -time of the wallet's most recent wallet-initiated send to the
    address before cutoff (later = better). Canonical tie-break by address."""
    last = {}
    for t, tos in per_wallet_history.get(wallet, ()):
        if t < cutoff:
            for a in tos:
                last[a] = t  # ascending order: overwrite = later
    items = sorted(last.items())
    items.sort(key=lambda x: -x[1])
    out = [(a, -float(t)) for a, t in items[:n] if domain.is_legal(a, cutoff)]
    return [s for _, s in out], [a for a, _ in out]


def random_legal_rank(domain, cutoff, rng, n):
    """Uniform sample of the legal visible domain at this cutoff, ranked by a
    fresh draw (the ranking itself is random). Sampling without replacement:
    prediction lists must hold distinct addresses."""
    hi = domain.domain_size(cutoff)
    if hi == 0:
        return [], []
    k = min(n, hi)
    idx = rng.choice(hi, size=k, replace=False)
    picks = [domain.addresses_sorted_by_ts[i] for i in idx]
    return [0.0] * len(picks), picks


def main():
    domain = load_domain()
    report = {"schema": "baselines-retrieval-v1", "date": "2026-10-06",
              "seed_random_legal": SEED,
              "track": "retrieval", "k": K,
              "note": "training-free baselines; same evaluator and canonical order "
                      "as the frozen scorer; history strictly timestamp < cutoff",
              "baselines": {}}
    for split in ("train", "dev", "test"):
        queries = read_jsonl(DS / f"queries/{split}.jsonl")
        gold = read_jsonl(DS / f"forecast_gold/{split}.jsonl")
        hist = history_counterparts(split)
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
            per_baseline[name] = res["summary"]
        report["baselines"][split] = per_baseline
        print(split, json.dumps({n: per_baseline[n] for n in per_baseline}, default=str)[:400])

    if OUT.exists():
        raise SystemExit(f"exists: {OUT}")
    with open(OUT, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("wrote", OUT.name)


if __name__ == "__main__":
    main()
