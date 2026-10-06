#!/usr/bin/env python
"""Release evaluator for eth-actions-benchmark-v1.0.0-candidate.

Adapts the prototype contract (research/benchmark_roles_temporal_v1_20261006/
benchmark_scorer.py) to the real package (VERSIONED_DATASET). Deviations from
the prototype are explicit and registered in SCORER_VALIDATION.json:

  1. Shared first-seen index adapter (FirstSeenDomain): one global sorted
     structure per split-set; per-query legality is O(1)
     (first_seen(address) < cutoff). No per-query full address copies.
  2. fixed_pool track: predictions must rank the COMPLETE frozen reference 50
     (same set, distinct, complete). The prototype demanded pool <= legal
     domain; the real frozen pools are method artifacts whose nominations are
     not all inside the declared first-seen domain, so pool-in-domain is NOT
     required (RELEASE_PROTOCOL.md section 2). Pool-outside-domain counts are
     reported as pool properties, never as prediction failures.
  3. Gold uses target_address (release schema) instead of the prototype's
     target_candidate_id; inactive targets are null by construction.
  4. Grounding evaluates three scopes SEPARATELY (candidate_relevant /
     claim_required / latest_relation); claim_required not_available rows are
     excluded from that scope's exact-set metrics and counted, never filled
     with the candidate-generic set. UNKNOWN is a state, never a parent id.
     Empty-set metrics are undefined (None), not faked as 1.

Local CPU only. No training, no model API calls, no chain/cloud queries.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import json
from collections import Counter
from pathlib import Path

TRACKS = ("retrieval", "fixed_pool")
GROUNDING_SCOPES = ("candidate_relevant_parent_ids", "claim_required_parent_ids",
                    "latest_relation_parent_ids")
UNKNOWN = "UNKNOWN"
EPOCH_MIN, EPOCH_MAX = 10**9, 2 * 10**9  # UTC seconds sanity window (2001-2033)


# ---------------------------------------------------------------- shared index
class FirstSeenDomain:
    """Shared legal-visible-domain D(t) adapter.

    One global first-seen table; a query (wallet, cutoff) never materializes
    its full address list. Membership is first_seen(address) < cutoff, strict.
    """

    def __init__(self, first_seen_seconds: dict):
        bad = [v for v in first_seen_seconds.values()
               if not isinstance(v, int) or not (EPOCH_MIN < v < EPOCH_MAX)]
        if bad:
            raise ValueError(f"first-seen timestamps must be UTC seconds, got e.g. {bad[:3]}")
        self.first_seen = dict(first_seen_seconds)
        self._sorted_ts = sorted(self.first_seen.values())
        self.addresses_sorted_by_ts = sorted(self.first_seen, key=self.first_seen.get)

    def is_legal(self, address, cutoff_seconds):
        fs = self.first_seen.get(address)
        return fs is not None and fs < cutoff_seconds

    def domain_size(self, cutoff_seconds):
        return bisect.bisect_left(self._sorted_ts, cutoff_seconds)

    def illegal_of(self, addresses, cutoff_seconds):
        return [a for a in addresses if not self.is_legal(a, cutoff_seconds)]


# ------------------------------------------------------------------ io helpers
def read_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def unique_by(rows, key):
    out = {}
    for row in rows:
        identity = row.get(key)
        if not isinstance(identity, str) or identity in out:
            raise ValueError(f"duplicate or non-string {key}: {identity!r}")
        out[identity] = row
    return out


def check_epoch_seconds(name, value):
    if not isinstance(value, int) or not (EPOCH_MIN < value < EPOCH_MAX):
        raise ValueError(f"{name} must be integer UTC seconds, got {value!r}")


# -------------------------------------------------------------------- forecast
def validate_prediction_row(pred, domain, cutoff, wallet_id, pool_set):
    """Return (ranked_list, None) if valid, else (None, reason). Fail-closed.

    fixed_pool: a prediction that IS the complete same reference 50 is valid
    regardless of per-address domain legality — pool membership is a frozen
    pool property (method artifact), reported separately, never a prediction
    failure. Any deviation from the pool falls through to legality checks and
    fails as not_complete_same_reference_pool / illegal as usual.
    """
    values = pred.get("ranked_candidate_ids")
    if not isinstance(values, list):
        return None, "missing_or_non_list"
    if not all(isinstance(a, str) for a in values):
        return None, "non_string_address"
    if len(values) > 50:
        return None, "more_than_50"
    if len(values) != len(set(values)):
        return None, "duplicate_addresses"
    if wallet_id in values:
        return None, "self_in_prediction"
    if pool_set is not None:
        if set(values) == pool_set and len(values) == len(pool_set):
            return values, None
        return None, "not_complete_same_reference_pool"
    illegal = domain.illegal_of(values, cutoff)
    if illegal:
        return None, "illegal_or_future_invisible_addresses"
    return values, None


def evaluate_forecast(queries, gold, predictions, domain, track="retrieval",
                      pools=None, reference_pool_is_method_artifact=True):
    """Four-categeory scored evaluation over all qualifying active queries.

    queries: rows with query_id, wallet_id, cutoff_UTC_seconds.
    gold: rows with query_id, window_status, active_eligible_external_attempt,
          target_address (null when inactive), outcome_UTC_seconds.
    predictions: rows with query_id, ranked_candidate_ids (addresses, best
          first, <=50, distinct). Order ties: caller-supplied order; when a
          parallel 'scores' list is supplied it must align and sorts by
          (-score, address) deterministically.
    domain: FirstSeenDomain shared adapter.
    track: retrieval -> <=50 distinct LEGAL addresses;
           fixed_pool -> must be the complete same reference 50.
    pools: {query_id: [50 addresses]} required for fixed_pool.
    """
    if track not in TRACKS:
        raise ValueError(f"unknown track {track}")
    if track == "fixed_pool" and pools is None:
        raise ValueError("fixed_pool requires frozen reference pools")
    qmap = unique_by(queries, "query_id")
    gmap = unique_by(gold, "query_id")
    pmap = unique_by(predictions, "query_id")
    if set(qmap) != set(gmap):
        raise ValueError("query/gold identity mismatch")
    counts = Counter()
    per_query = []
    for identity, q in qmap.items():
        lab = gmap[identity]
        counts["sampled_queries"] += 1
        cutoff = q["cutoff_UTC_seconds"]
        check_epoch_seconds(f"cutoff[{identity}]", cutoff)
        ws = lab["window_status"]
        if ws not in ("complete_relative_to_declared_source", "incomplete", "unknown"):
            raise ValueError(f"unknown window_status {ws!r}")
        if ws != "complete_relative_to_declared_source":
            counts["unqualified_window_queries"] += 1
            per_query.append(dict(query_id=identity, wallet_id=q["wallet_id"],
                                  eligible=False, reason="window_not_certified"))
            continue
        counts["eligible_queries"] += 1
        active = lab["active_eligible_external_attempt"]
        if not isinstance(active, bool):
            raise ValueError("activity must be boolean, not inferred")
        y = lab["target_address"]
        wallet_id = q["wallet_id"]
        pool_set = None
        if track == "fixed_pool":
            pool = pools[identity]["addresses"]
            if (not isinstance(pool, list) or len(pool) != 50
                    or not all(isinstance(a, str) for a in pool)
                    or len(set(pool)) != 50):
                raise ValueError(f"malformed frozen pool for {identity}")
            if wallet_id in pool:
                raise ValueError(f"frozen pool contains the query wallet: {identity}")
            pool_set = set(pool)
            if not reference_pool_is_method_artifact:
                outside = domain.illegal_of(pool, cutoff)
                if outside:
                    raise ValueError("pool outside domain and artifact exemption disabled")
        if active and (not isinstance(y, str) or y == wallet_id):
            raise ValueError(f"invalid eligible external target for {identity}")
        if not active and y is not None:
            raise ValueError(f"inactive query {identity} carries a target")
        p = pmap.get(identity)
        ranked = None
        reason = "missing_prediction"
        if p is not None:
            scores = p.get("scores")
            values = list(p["ranked_candidate_ids"]) if isinstance(p.get("ranked_candidate_ids"), list) else None
            if values is not None and isinstance(scores, list) and len(scores) == len(values) \
                    and all(isinstance(s, (int, float)) for s in scores):
                order = sorted(range(len(values)), key=lambda i: (-scores[i], values[i]))
                values = [values[i] for i in order]
            ranked, reason = validate_prediction_row(p if values is None else
                                                     {**p, "ranked_candidate_ids": values},
                                                     domain, cutoff, wallet_id, pool_set)
        valid = ranked is not None
        counts["valid_predictions"] += int(valid)
        counts["missing_or_invalid_predictions"] += int(not valid)
        if not active:
            counts["inactive_queries"] += 1
            if valid:
                counts["inactive_valid_predictions"] += 1
            per_query.append(dict(query_id=identity, wallet_id=wallet_id, eligible=True,
                                  active=False, valid_prediction=valid, format_reason=reason))
            continue
        counts["active_queries"] += 1
        observable = domain.is_legal(y, cutoff) if isinstance(y, str) else False
        counts["observable_active_targets"] += int(observable)
        rank = ranked.index(y) + 1 if (valid and y in ranked) else None
        h5 = rank is not None and rank <= 5
        h50 = rank is not None
        rr = 1.0 / rank if h5 else 0.0
        counts["hits5"] += int(h5)
        counts["hits50"] += int(h50)
        if not observable:
            category = "target_outside_legal_index"
        elif not valid:
            category = "observable_target_invalid_or_missing_prediction"
        elif rank is None:
            category = "observable_target_outside_proposed50"
        elif not h5:
            category = "target_in50_outside5"
        else:
            category = "target_in5"
        counts[category] += 1
        per_query.append(dict(query_id=identity, wallet_id=wallet_id, eligible=True, active=True,
                              target_observable=observable, valid_prediction=valid, rank=rank,
                              hits5=int(h5), hits50=int(h50), rr5=rr,
                              error_category=category, format_reason=reason))
    active_rows = [r for r in per_query if r.get("active")]
    n = counts["active_queries"]
    eligible = counts["eligible_queries"]
    summary_keys = ("sampled_queries", "unqualified_window_queries", "eligible_queries",
                    "valid_predictions", "missing_or_invalid_predictions",
                    "inactive_queries", "inactive_valid_predictions",
                    "active_queries", "observable_active_targets", "hits5", "hits50",
                    "target_outside_legal_index",
                    "observable_target_invalid_or_missing_prediction",
                    "observable_target_outside_proposed50", "target_in50_outside5",
                    "target_in5")
    summary = {k: counts[k] for k in summary_keys}
    summary.update(
        Top5=(counts["hits5"] / n) if n else None,
        MRR5=(sum(r["rr5"] for r in active_rows) / n) if n else None,
        Recall50=(counts["hits50"] / n) if n else None,
        format_valid_rate=(counts["valid_predictions"] / eligible) if eligible else None,
        sampled_wallets=len({q["wallet_id"] for q in queries}),
        active_wallets=len({r["wallet_id"] for r in active_rows}),
        extra_prediction_queries=sorted(set(pmap) - set(qmap)),
        track=track,
        denominator="all qualifying active queries",
        pooloutside_and_invalid_are_failures=True,
    )
    return dict(summary=summary, per_query=per_query)


def evaluate_activity(preds_by_query, gold, qmap):
    """Activity is evaluated separately: does the method's emptiness signal
    (absent/empty prediction) match inactivity? Not part of the main metric."""
    conf = Counter()
    for identity, lab in gold.items():
        if lab["window_status"] != "complete_relative_to_declared_source":
            continue
        p = preds_by_query.get(identity)
        said_active = bool(p and isinstance(p.get("ranked_candidate_ids"), list)
                           and len(p["ranked_candidate_ids"]) > 0)
        was_active = lab["active_eligible_external_attempt"]
        conf[("active" if was_active else "inactive", "said_active" if said_active else "said_empty")] += 1
    tp = conf[("active", "said_active")]
    tn = conf[("inactive", "said_empty")]
    total = sum(conf.values())
    return dict(confusion={f"gold_{k[0]}_pred_{k[1]}": v for k, v in conf.items()},
                accuracy=(tp + tn) / total if total else None, n=total)


# --------------------------------------------------------------------- pooling
def wallet_bootstrap_intervals(per_query, rows, replicates=2000, seed=27061006):
    """Wallet-cluster paired bootstrap over per-query metric deltas.

    rows must carry wallet_id; per_query is a {query_id: float} delta table
    already restricted to the shared active denominator.
    """
    import random
    by_wallet = {}
    for r in rows:
        by_wallet.setdefault(r["wallet_id"], []).append(r)
    names = sorted(by_wallet)
    rng = random.Random(seed)
    out = {}
    for metric, delta_of in (("hits5", lambda r: float(r["hits5"])),
                             ("rr5", lambda r: r["rr5"])):
        numer = {w: sum(delta_of(r) for r in rs) for w, names_i in [(w, by_wallet[w])]
                 for w in [w]}
        denom = {w: len(by_wallet[w]) for w in names}
        draws = []
        for _ in range(replicates):
            num = den = 0
            for _w in names:
                i = rng.randrange(len(names))
                num += numer[names[i]]
                den += denom[names[i]]
            if den:
                draws.append(num / den)
        point = sum(numer.values()) / sum(denom.values())
        draws.sort()
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        out[metric] = dict(point=point, wallet_bootstrap95=[lo, hi],
                           replicates=replicates, seed=seed,
                           wallets=len(names), active_queries=int(sum(denom.values())))
    return out


def paired_contrast(per_a, per_b, rows, replicates=2000, seed=27061006):
    """rescue/replace/net-hits and paired intervals for A minus B."""
    common = sorted(set(per_a) & set(per_b))
    rowmap = {r["query_id"]: r for r in rows}
    deltas = {q: per_a[q] - per_b[q] for q in common}
    rescues = sum(1 for q in common if rowmap[q]["hits5"] and not
                  (rowmap[q].get("_ref_hits5")))
    # rescue/harm must be computed on hit vectors; caller passes rows augmented
    interval = wallet_bootstrap_intervals(
        None, [{**rowmap[q], "hits5": deltas[q]} for q in common if deltas[q] is not None],
        replicates=replicates, seed=seed)
    return interval


def by_cutoff_summary(per_query, queries):
    cuts = {q["query_id"]: q["cutoff_UTC_seconds"] for q in queries}
    groups = {}
    for r in per_query:
        if not r.get("active"):
            continue
        groups.setdefault(cuts[r["query_id"]], []).append(r)
    out = {}
    for cut, rows in sorted(groups.items()):
        n = len(rows)
        out[cut] = dict(active_queries=n,
                        Top5=sum(r["hits5"] for r in rows) / n,
                        MRR5=sum(r["rr5"] for r in rows) / n,
                        Recall50=sum(r["hits50"] for r in rows) / n)
    return out


def target_concentration_summary(per_query, gold):
    """Sensitivity to target repetition across queries (shared targets)."""
    freq = Counter(lab["target_address"] for lab in gold.values()
                   if lab.get("active_eligible_external_attempt"))
    buckets = {"unique_target": [], "shared_target": []}
    for r in per_query:
        if not r.get("active"):
            continue
        identity_target = None
        buckets["shared_target" if freq_used(gold, r["query_id"], freq) > 1 else "unique_target"].append(r)
    out = {}
    for name, rows in buckets.items():
        n = len(rows)
        out[name] = dict(active_queries=n,
                         Top5=(sum(r["hits5"] for r in rows) / n) if n else None,
                         Recall50=(sum(r["hits50"] for r in rows) / n) if n else None)
    return out


def freq_used(gold, qid, freq):
    lab = gold[qid]
    return freq.get(lab.get("target_address"), 0) if lab.get("target_address") else 0


# -------------------------------------------------------------------- grounding
def evaluate_grounding(gold, predictions):
    """Three separate scopes. UNKNOWN is a state, never a parent id.

    Gold rows: example_id, group_id, wallet_id, fact_label in
    {supported, conflicted, unknown}, plus per-scope parent id lists;
    claim_required_status 'not_available' excludes that scope from exact-set
    metrics and is counted. Empty gold sets -> undefined metrics (None).
    """
    truth = unique_by(gold, "example_id")
    pred = unique_by(predictions, "example_id") if predictions else {}
    classes = ("supported", "conflicted", "unknown")
    confusion = {c: Counter() for c in classes}
    correct = 0
    scope = {s: dict(n_eligible=0, n_not_available=0, n_empty_gold=0, exact=0,
                     tp=0, fp=0, fn=0) for s in GROUNDING_SCOPES}
    invalid = 0
    for identity, g in truth.items():
        if g["fact_label"] not in classes:
            raise ValueError(f"unknown gold fact label {g['fact_label']!r}")
        p = pred.get(identity, {})
        c = p.get("fact_label", "MISSING")
        if c not in classes:
            c = "INVALID"
            invalid += 1
        confusion[g["fact_label"]][c] += 1
        correct += int(c == g["fact_label"])
        for s in GROUNDING_SCOPES:
            gold_ids = g.get(s)
            status = g.get(s.replace("parent_ids", "status"), "available")
            if status == "not_available" or gold_ids is None:
                scope[s]["n_not_available"] += 1
                continue
            if not isinstance(gold_ids, list):
                raise ValueError(f"gold {s} must be list for {identity}")
            if not gold_ids:
                scope[s]["n_empty_gold"] += 1
                continue  # empty-set metrics stay undefined, never faked as 1
            got = p.get(s)
            if not isinstance(got, list):
                scope[s]["fn"] += len(gold_ids)
                continue
            gset, pset = set(gold_ids), set(got)
            if UNKNOWN in pset and UNKNOWN not in gset:
                # UNKNOWN is a state; as a parent id it is always wrong here
                pset = pset - {UNKNOWN}
            scope[s]["n_eligible"] += 1
            scope[s]["exact"] += int(gset == pset)
            scope[s]["tp"] += len(gset & pset)
            scope[s]["fp"] += len(pset - gset)
            scope[s]["fn"] += len(gset - pset)
    n = len(truth)
    f1s = []
    for c in classes:
        t = confusion[c][c]
        fp = sum(confusion[o][c] for o in classes if o != c)
        fn = sum(confusion[c].values()) - t
        f1s.append(2 * t / (2 * t + fp + fn) if (2 * t + fp + fn) else 0.0)
    labels_present = any(confusion[c] for c in classes)
    out = dict(examples=n, groups=len({g["group_id"] for g in gold}),
               wallets=len({g["wallet_id"] for g in gold}),
               fact_accuracy=(correct / n) if n else None,
               fact_macro_F1=(sum(f1s) / 3) if labels_present else None,
               fact_confusion={k: dict(v) for k, v in confusion.items()},
               invalid_or_missing_fact_predictions=invalid,
               metric_not_combined_with_forecasting=True,
               scopes={})
    for s, d in scope.items():
        tp, fp, fn = d["tp"], d["fp"], d["fn"]
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        out["scopes"][s] = dict(d,
            precision=prec, recall=rec,
            F1=(2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else None,
            exact_rate=(d["exact"] / d["n_eligible"]) if d["n_eligible"] else None)
    return out


def binding_tuple_errors(gold, predictions):
    """Per-example report of multi-action binding scope errors: parent ids
    submitted under the wrong scope (e.g. latest ids given as claim_required)."""
    errors = []
    pred = {p["example_id"]: p for p in predictions}
    for g in gold:
        p = pred.get(g["example_id"])
        if not p:
            continue
        latest = set(g.get("latest_relation_parent_ids") or [])
        claim = set(g.get("claim_required_parent_ids") or [])
        got_latest = set(p.get("latest_relation_parent_ids") or []) - {UNKNOWN}
        got_claim = set(p.get("claim_required_parent_ids") or []) - {UNKNOWN}
        if latest and claim and got_latest and got_latest <= claim and not (got_latest & set(
                g.get("latest_relation_parent_ids") or [])):
            errors.append(dict(example_id=g["example_id"], kind="latest_submitted_from_claim_scope"))
        if claim and got_claim and got_claim <= latest and claim != latest:
            errors.append(dict(example_id=g["example_id"], kind="claim_submitted_from_latest_scope"))
    return errors


# -------------------------------------------------------------- contract tests
def contract_tests():
    """Synthetic-only fail-closed contracts. No real data access."""
    T0 = 1700000000  # realistic UTC seconds (sanity window enforced)
    addresses = [f"0x{i:040x}" for i in range(1, 61)]
    first_seen = {a: T0 + i for i, a in enumerate(addresses)}
    domain = FirstSeenDomain(first_seen)
    q = [dict(query_id="q0", wallet_id="W", cutoff_UTC_seconds=T0 + 30)]
    g = [dict(query_id="q0", window_status="complete_relative_to_declared_source",
              active_eligible_external_attempt=True, target_address=addresses[5])]
    results = {}

    def run(preds, track="retrieval", gold=None, pools=None):
        return evaluate_forecast(q, gold or g, preds, domain, track, pools=pools)

    # duplicate ids rejected
    for bad in ([dict(query_id=None)], [dict(query_id="q0"), dict(query_id="q0")]):
        try:
            unique_by(bad, "query_id")
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate ids accepted")
    # missing prediction = failure
    r = run([])["summary"]
    assert r["hits5"] == 0 and r["missing_or_invalid_predictions"] == 1 and r["active_queries"] == 1
    results["missing_prediction_fails"] = True
    # future-invisible address -> invalid, target observable counted
    r = run([dict(query_id="q0", ranked_candidate_ids=[addresses[40]])])["summary"]
    assert r["valid_predictions"] == 0 and r["hits5"] == 0
    assert r["observable_active_targets"] == 1
    assert r["Top5"] == 0.0 and r["format_valid_rate"] == 0.0
    results["future_invisible_address_fails"] = True
    # legal hit ranks correctly (target at position 1)
    r = run([dict(query_id="q0", ranked_candidate_ids=[addresses[5]] + addresses[:4])])
    assert r["summary"]["hits5"] == 1 and r["summary"]["MRR5"] == 1.0
    assert r["per_query"][0]["rank"] == 1
    # position-5 hit gives MRR 1/5
    r = run([dict(query_id="q0", ranked_candidate_ids=addresses[:4] + [addresses[5]])])
    assert r["summary"]["hits5"] == 1 and r["summary"]["MRR5"] == 1 / 5
    assert r["per_query"][0]["rank"] == 5
    results["rank_and_mrr"] = True
    # duplicate address prediction fails
    r = run([dict(query_id="q0", ranked_candidate_ids=[addresses[5]] * 2)])["summary"]
    assert r["valid_predictions"] == 0
    results["duplicate_address_fails"] = True
    # >50 fails
    r = run([dict(query_id="q0", ranked_candidate_ids=addresses[:51])])["summary"]
    assert r["valid_predictions"] == 0
    results["more_than_50_fails"] = True
    # fixed pool: complete same pool required; pool may sit outside domain (artifact)
    pool = addresses[10:60]  # 50 entries; includes cutoff-invisible addresses (artifact)
    pools = {"q0": dict(query_id="q0", addresses=pool)}
    gpool = [dict(g[0], target_address=pool[3])]
    r = run([dict(query_id="q0", ranked_candidate_ids=pool)], "fixed_pool", gpool, pools)["summary"]
    assert r["hits5"] == 1 and r["valid_predictions"] == 1
    r = run([dict(query_id="q0", ranked_candidate_ids=pool[:49] + [addresses[0]])],
            "fixed_pool", gpool, pools)["summary"]
    assert r["valid_predictions"] == 0, "partial/substituted pool accepted"
    results["fixed_pool_complete_same_50"] = True
    results["pool_artifact_outside_domain_allowed"] = True
    # out-of-pool target fails in fixed pool
    gout = [dict(g[0], target_address=addresses[9])]  # legal but outside pool
    r = run([dict(query_id="q0", ranked_candidate_ids=pool)], "fixed_pool", gout, pools)
    assert r["summary"]["hits50"] == 0 and r["per_query"][0]["error_category"] == \
        "observable_target_outside_proposed50"
    results["out_of_pool_target_fails"] = True
    # inactive carries no target; activity evaluated separately
    gact = [dict(g[0], active_eligible_external_attempt=False, target_address=None)]
    r = run([dict(query_id="q0", ranked_candidate_ids=addresses[:3])], gold=gact)["summary"]
    assert r["active_queries"] == 0 and r["inactive_queries"] == 1
    results["inactive_separate"] = True
    # time units: bad epochs rejected
    try:
        FirstSeenDomain({addresses[0]: 10**15})
    except ValueError:
        pass
    else:
        raise AssertionError("microsecond-scale epochs accepted")
    try:
        evaluate_forecast([dict(q[0], cutoff_UTC_seconds=10**15)], g, [], domain)
    except ValueError:
        pass
    else:
        raise AssertionError("microsecond cutoff accepted")
    results["time_units_utc_seconds"] = True
    # empty denominators -> None, not 0/1
    rempty = evaluate_forecast(q, [dict(g[0], window_status="unknown")], [], domain)["summary"]
    assert rempty["Top5"] is None and rempty["MRR5"] is None and rempty["format_valid_rate"] is None
    results["empty_denominator_undefined"] = True
    # extra prediction queries reported
    r = run([dict(query_id="zz", ranked_candidate_ids=[addresses[0]])])["summary"]
    assert r["extra_prediction_queries"] == ["zz"]
    results["extra_predictions_reported"] = True
    # grounding: UNKNOWN state not parent; not_available excluded; empty undefined
    gg = [dict(example_id="e0", group_id="g0", wallet_id="W", fact_label="unknown",
               candidate_relevant_parent_ids=[], claim_required_parent_ids=None,
               claim_required_status="not_available", latest_relation_parent_ids=[]),
          dict(example_id="e1", group_id="g0", wallet_id="W", fact_label="supported",
               candidate_relevant_parent_ids=["p1", "p2"], claim_required_parent_ids=["p1"],
               latest_relation_parent_ids=["p2"])]
    gp = [dict(example_id="e0", fact_label="unknown", candidate_relevant_parent_ids=[UNKNOWN],
               claim_required_parent_ids=[], latest_relation_parent_ids=[]),
          dict(example_id="e1", fact_label="supported", candidate_relevant_parent_ids=["p2", "p1"],
               claim_required_parent_ids=["p1"], latest_relation_parent_ids=["p2"])]
    rg = evaluate_grounding(gg, gp)
    assert rg["scopes"]["candidate_relevant_parent_ids"]["n_empty_gold"] == 1
    assert rg["scopes"]["claim_required_parent_ids"]["n_not_available"] == 1
    assert rg["scopes"]["claim_required_parent_ids"]["exact_rate"] == 1.0
    assert rg["scopes"]["latest_relation_parent_ids"]["exact_rate"] == 1.0
    results["grounding_scopes_and_unknown"] = True
    # an ALL-empty scope stays undefined, never faked as 1
    gempty = [dict(example_id="z0", group_id="gz", wallet_id="W", fact_label="unknown",
                   candidate_relevant_parent_ids=[], claim_required_parent_ids=None,
                   claim_required_status="not_available", latest_relation_parent_ids=[])]
    pempty = [dict(example_id="z0", fact_label="unknown", candidate_relevant_parent_ids=[UNKNOWN],
                   claim_required_parent_ids=[], latest_relation_parent_ids=[])]
    rz = evaluate_grounding(gempty, pempty)
    assert rz["scopes"]["candidate_relevant_parent_ids"]["exact_rate"] is None
    assert rz["scopes"]["candidate_relevant_parent_ids"]["precision"] is None
    assert rz["scopes"]["claim_required_parent_ids"]["n_not_available"] == 1
    assert rz["fact_macro_F1"] == 1 / 3  # macro over 3 classes; single unknown all-correct
    results["grounding_scopes_and_unknown"] = True
    # unknown predicted via UNKNOWN token where gold has real parents = wrong
    gp2 = [dict(gp[0], example_id="e0", candidate_relevant_parent_ids=[UNKNOWN]),
           dict(example_id="e1", fact_label="supported", candidate_relevant_parent_ids=[UNKNOWN],
                claim_required_parent_ids=["p1"], latest_relation_parent_ids=["p2"])]
    rg2 = evaluate_grounding(gg, gp2)
    assert rg2["scopes"]["candidate_relevant_parent_ids"]["exact"] == 0
    assert rg2["scopes"]["candidate_relevant_parent_ids"]["fn"] == 2
    results["unknown_token_not_parent_id"] = True
    # multi-action binding scope errors detectable
    errs = binding_tuple_errors(gg, [dict(example_id="e1", fact_label="supported",
        candidate_relevant_parent_ids=["p1"], claim_required_parent_ids=["p2"],
        latest_relation_parent_ids=["p2"])])
    assert errs and errs[0]["kind"] == "claim_submitted_from_latest_scope"
    results["binding_scope_errors_flagged"] = True
    return dict(status="passed", checks=sorted(results.keys()), real_data_read=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=["selftest"])
    a = ap.parse_args()
    if a.task == "selftest":
        print(json.dumps(contract_tests(), indent=1))


if __name__ == "__main__":
    main()
