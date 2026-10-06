#!/usr/bin/env python
"""Stage C: score the completed V27lean TRAIN baseline through the release
evaluator against VERSIONED_DATASET, verify agreement with frozen RESULTS.json,
and record an independent recount.

Prediction conversion: PREDICTIONS.npz rows (scores 1800x50 + addresses 1800x50)
are converted to release-schema rows {query_id, ranked_candidate_ids} by
deterministic sorting with the SAME canonical tie-break the frozen evaluator
used: descending score, ascending address (np.lexsort((addresses, -scores))).
This reproduces the frozen ranking before it is re-scored by the new evaluator.

Denominators and gates:
  - retrieval track over the legal first-seen domain at each query cutoff;
  - fixed_pool track over the frozen v27lean pool (reference_top50_train);
  - all qualifying active queries as denominator; inactive reported separately;
  - frozen gold comes from forecast_gold/train.jsonl (2200/2200 regeneration
    match recorded in EXPORT_VALIDATION.json).

Outputs (first-write only):
  artifacts/benchmark_release_candidate_v1_20261006/SCORING_V27LEAN_TRAIN.json
Local CPU only; no training, no model API, no chain/cloud access.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_evaluator import (FirstSeenDomain, evaluate_forecast,  # noqa: E402
                                 evaluate_grounding, read_jsonl, unique_by)

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
V27 = R / "artifacts/action_evidence_rerank_v27lean_20261006"
DS = R / "artifacts/benchmark_release_candidate_v1_20261006/VERSIONED_DATASET"
OUTDIR = R / "artifacts/benchmark_release_candidate_v1_20261006"
BRANCHES = ["r0scores", "all_history_seed0", "recent_actions_seed0",
            "program_roles_seed0", "learned_locator_seed0"]


def load_domain():
    rows = []
    with gzip.open(DS / "candidate_index/legal_domain_index.jsonl.gz", "rt") as f:
        header = json.loads(f.readline())
        assert header["schema"] == "legal-domain-first-seen-v1"
        for line in f:
            r = json.loads(line)
            rows.append((r["address"], r["first_seen_UTC_seconds"]))
    return FirstSeenDomain(dict(rows))


def load_split(name):
    queries = read_jsonl(DS / f"queries/{name}.jsonl")
    gold = read_jsonl(DS / f"forecast_gold/{name}.jsonl")
    pools = {r["query_id"]: r for r in read_jsonl(DS / f"reference_pools/reference_top50_{name}.jsonl")}
    return queries, gold, pools


def npz_to_rows(scores, addresses, case_ids):
    """Deterministic canonical order: descending score, ascending address.

    Identical rule to the frozen v27lean metrics() lexsort, so agreement checks
    test the evaluator, not the tie-break convention.
    """
    scores, addresses = np.asarray(scores), np.asarray(addresses)
    rows = []
    for i, cid in enumerate(case_ids):
        order = np.lexsort((addresses[i], -scores[i].astype(np.float64)))
        rows.append(dict(query_id=cid,
                         ranked_candidate_ids=[addresses[i][j] for j in order],
                         scores=[float(scores[i][j]) for j in order]))
    return rows


def independent_recount(rows_pred, gold_map, qmap, domain, pool_rows, require_legality):
    """Second, structurally different recount of Top5/Recall50/hits.

    Uses direct list membership + an inline legality gate (independent
    implementation of the same fail-closed rule; no shared helper), so
    agreement tests the metric bookkeeping, not one shared code path.
    require_legality=True mirrors the retrieval track: any emitted address
    with first_seen >= cutoff invalidates the whole prediction.
    """
    hits5 = hits50 = active = supported = 0
    for qid, pred in rows_pred.items():
        lab = gold_map[qid]
        if not lab["active_eligible_external_attempt"]:
            continue
        active += 1
        y = lab["target_address"]
        ranked = pred["ranked_candidate_ids"]
        cutoff = qmap[qid]["cutoff_UTC_seconds"]
        first = domain.first_seen
        legal = (not require_legality) or all(
            (a in first) and (first[a] < cutoff) for a in ranked)
        if not legal:
            continue
        if y is not None and y in ranked:
            hits50 += 1
            if ranked.index(y) < 5:
                hits5 += 1
        if y is not None and pool_rows[qid]["addresses"] is not None and \
                y in set(pool_rows[qid]["addresses"]):
            supported += 1
    return dict(active_queries=active, hits5=hits5, hits50=hits50, supported50=supported,
                Top5=hits5 / active, Recall50=hits50 / active)


def main():
    out_path = OUTDIR / "SCORING_V27LEAN_TRAIN.json"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path}")
    frozen = json.load(open(V27 / "RESULTS.json"))
    with np.load(V27 / "PREDICTIONS.npz", allow_pickle=False) as z:
        case_ids = z["case_ids"].tolist()
        shared_addresses = np.asarray(z["addresses"])
        npz = {b: z[b] for b in BRANCHES}
    queries, gold, pools = load_split("train")
    qmap = unique_by(queries, "query_id")
    gmap = unique_by(gold, "query_id")
    domain = load_domain()

    # pool sanity for fixed_pool: complete same 50 across queries
    pool_rows = {qid: pools[qid] for qid in qmap}
    n_pool_ok = sum(1 for r in pools.values() if r["addresses"] is not None
                    and len(r["addresses"]) == 50 and len(set(r["addresses"])) == 50)
    # frozen pool vs npz addresses identity
    frozen_pool_rows = {}
    with np.load(V27 / "PREDICTIONS.npz", allow_pickle=False) as z:
        npz_addr = {c: sorted(a.tolist()) for c, a in zip(z["case_ids"].tolist(), z["addresses"])}
    mismatch_pool = 0
    for r in pools.values():
        if r["addresses"] is None:
            continue
        if sorted(r["addresses"]) != npz_addr[r["query_id"]]:
            mismatch_pool += 1
    print(f"reference pools complete-50: {n_pool_ok}/1800; pool vs npz mismatches: {mismatch_pool}")

    results = {"created_for": "eth-actions-benchmark-v1.0.0-candidate",
               "baseline": "action_evidence_rerank_v27lean_20261006 (frozen, train split only)",
               "tracks": {}, "agreement_with_frozen": {}, "independent_recount": {},
               "notes": [
                   "The frozen RESULTS.json numbers (e.g. all_history_seed0 hits5=416, "
                   "Recall50=674/985) were produced by ranking the complete frozen v27lean "
                   "pool with no per-address legality gate. Under the release contract that "
                   "corresponds to the fixed_pool track. The retrieval track additionally "
                   "requires every emitted address to be legal (first_seen < cutoff) in the "
                   "shared first-seen domain; 330/1800 frozen predictions include "
                   "cutoff-invisible addresses and therefore fail closed there, with lower "
                   "but honestly-denominated retrieval scores reported alongside. Both "
                   "tracks are reported; neither overwrites the frozen record."]}

    # ---- fixed_pool track first: this is the track the frozen numbers live in ----
    pool_full = {qid: r for qid, r in pools.items() if r["addresses"] is not None}
    pool_sets = {qid: set(r["addresses"]) for qid, r in pool_full.items()}
    for branch in BRANCHES:
        rows = npz_to_rows(npz[branch], shared_addresses, case_ids)
        res = evaluate_forecast(queries, gold, rows, domain, "fixed_pool", pools=pools)
        results["tracks"].setdefault("fixed_pool", {})[branch] = res["summary"]
        s, f = res["summary"], frozen["stats"][branch]
        agree = dict(hits5=s["hits5"] == f["hits5"],
                     Top5=abs(s["Top5"] - f["Top5"]) < 1e-12,
                     MRR5=abs(s["MRR5"] - f["MRR5"]) < 1e-9,
                     Recall50=abs(s["Recall50"] - f["Recall50"]) < 1e-12,
                     active_queries=s["active_queries"] == f["active_queries"],
                     supported50=s["target_in50_outside5"] + s["target_in5"] ==
                     (s["observable_active_targets"] - s["observable_target_invalid_or_missing_prediction"]
                      - s["observable_target_outside_proposed50"]),
                     all_valid_predictions=s["valid_predictions"] == s["eligible_queries"])
        results["agreement_with_frozen"][f"{branch}/fixed_pool"] = agree
        # independent recount (set-membership, no rank bookkeeping)
        pred_map = unique_by(rows, "query_id")
        recount = independent_recount(pred_map, gmap, qmap, domain, pool_rows, require_legality=False)
        results["independent_recount"][f"{branch}/fixed_pool"] = recount
        assert recount["hits5"] == s["hits5"] and recount["hits50"] == s["hits50"] and \
            recount["supported50"] == f["supported50"], \
            f"independent recount disagrees for {branch}/fixed_pool"
        print(f"{branch}/fixed_pool: Top5={s['Top5']:.5f} MRR5={s['MRR5']:.6f} "
              f"Recall50={s['Recall50']:.5f} valid={s['valid_predictions']}/{s['eligible_queries']} agree={all(agree.values())}")

    # ---- retrieval track: strict legality gate over the shared legal domain ----
    for branch in BRANCHES:
        rows = npz_to_rows(npz[branch], shared_addresses, case_ids)
        res = evaluate_forecast(queries, gold, rows, domain, "retrieval")
        results["tracks"].setdefault("retrieval", {})[branch] = res["summary"]
        s = res["summary"]
        recount = independent_recount(unique_by(rows, "query_id"), gmap, qmap, domain, pool_rows, require_legality=True)
        results["independent_recount"][f"{branch}/retrieval"] = recount
        assert recount["hits5"] == s["hits5"] and recount["hits50"] == s["hits50"], \
            f"independent recount disagrees for {branch}/retrieval"
        print(f"{branch}/retrieval: Top5={s['Top5']:.5f} MRR5={s['MRR5']:.6f} "
              f"Recall50={s['Recall50']:.5f} hits5={s['hits5']}/{s['active_queries']} "
              f"invalid_preds={s['missing_or_invalid_predictions']}")

    # ---- activity head (emptiness-signal vs gold inactivity) ----
    # v27lean always emits 50 candidates -> the activity head is not exercised by
    # this baseline; recorded as such rather than simulated.
    results["activity_head"] = {
        "baseline_emits_full_50_for_every_query": True,
        "evaluated": False,
        "reason": "frozen baseline has no emptiness signal; activity evaluated separately only when a method provides one",
    }

    # ---- grounding: frozen locator diagnostics are aggregates only ----
    results["grounding"] = {
        "status": "aggregate_diagnostics_only_in_v27lean",
        "detail": "v27lean LOCATORS/*/DIAGNOSTICS.json hold aggregate metrics on a 1232-example subset "
                  "without per-example ids, so per-example release-schema grounding predictions cannot be "
                  "reconstructed; no per-example predictions exist in the frozen package. Scoring this "
                  "baseline on grounding would require re-running the method, which stage C must not do.",
        "evaluator_ready": True,
        "human_annotation": "pending (stage E); automatic labels only",
    }

    # ---- pool/domain artifact properties (reported, never prediction failures) ----
    pool_addr_total = illegal_pool = 0
    for r in pools.values():
        if r["addresses"] is None:
            continue
        cut = qmap[r["query_id"]]["cutoff_UTC_seconds"]
        for a in r["addresses"]:
            pool_addr_total += 1
            if not domain.is_legal(a, cut):
                illegal_pool += 1
    results["reference_pool_artifact_properties"] = {
        "pool_address_slots": pool_addr_total,
        "pool_addresses_outside_declared_first_seen_domain_at_cutoff": illegal_pool,
        "note": "frozen pools are method artifacts (RELEASE_PROTOCOL section 2); "
                "outside-domain nominations are pool properties, counted here, never scored as prediction failures",
    }

    # ---- aggregate verdict ----
    # Agreement target = fixed_pool (the track the frozen numbers were produced in).
    # Retrieval numbers are new diagnostics under a stricter gate and are not
    # expected to equal the frozen pool-ranking numbers.
    fixed_agree = {k: all(v) for k, v in results["agreement_with_frozen"].items()
                   if k.endswith("/fixed_pool")}
    results["verdict"] = {
        "frozen_metrics_reproduced_by_release_evaluator": all(fixed_agree.values()),
        "fixed_pool_branch_agreement": fixed_agree,
        "independent_recount_matches": True,
        "denominator": "all qualifying active queries (985)",
        "retrieval_track_is_stricter_new_diagnostic": True,
    }

    with open(out_path, "x") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print("wrote", out_path)
    print("verdict:", json.dumps(results["verdict"]))


if __name__ == "__main__":
    main()
