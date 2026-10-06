#!/usr/bin/env python
"""Stage C diagnostics: wallet-cluster paired bootstrap CIs (rescue/replace),
per-cutoff breakdowns and target-concentration sensitivity for the fixed_pool
scoring of the frozen V27lean TRAIN baseline. Same bootstrap recipe as the
frozen v27lean evaluator (2000 replicates, seed 27061006, complete-wallet
resampling, active-query-weighted ratio) so numbers are directly comparable
to RESULTS.json primary_comparisons.

Writes (first-write only): SCORING_V27LEAN_TRAIN_DIAGNOSTICS.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_evaluator import read_jsonl, unique_by  # noqa: E402
import score_v27lean_train as S  # noqa: E402

PRIMARY_PAIRS = (("program_roles", "all_history"),
                 ("learned_locator", "all_history"),
                 ("learned_locator", "program_roles"))


def wallet_bootstrap(per_query_delta, samples, names, indices, denom):
    """Frozen recipe: complete-wallet resampling from ONE shared pre-generated
    sample matrix (2000 x wallets), active-query-weighted ratio; identical to
    the frozen WalletBootstrap so paired contrasts share the same resamples."""
    numer = np.asarray([per_query_delta[ix].sum() for ix in indices])
    usable_denom = denom[samples].sum(1)
    usable = usable_denom > 0
    draws = numer[samples].sum(1)[usable] / usable_denom[usable]
    point = numer.sum() / denom.sum()
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return dict(difference=float(point), wallet_bootstrap95=[float(lo), float(hi)],
                replicates=int(usable.sum()))


def main():
    out_path = S.OUTDIR / "SCORING_V27LEAN_TRAIN_DIAGNOSTICS.json"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path}")
    frozen = json.load(open(S.V27 / "RESULTS.json"))
    queries, gold, pools = S.load_split("train")
    gmap = unique_by(gold, "query_id")
    with np.load(S.V27 / "PREDICTIONS.npz", allow_pickle=False) as z:
        case_ids = z["case_ids"].tolist()
        wallets = np.asarray(z["wallets"])
        cutoffs = np.asarray(z["cutoffs"])
        shared_addresses = np.asarray(z["addresses"])
        npz = {b: z[b] for b in S.BRANCHES}

    # canonical fixed_pool rankings (identical recipe to frozen evaluator)
    ranked = {}
    for branch in S.BRANCHES:
        rows = S.npz_to_rows(npz[branch], shared_addresses, case_ids)
        ranked[branch] = {r["query_id"]: r["ranked_candidate_ids"] for r in rows}

    # hit vectors over ACTIVE queries (canonical query order)
    active_mask = np.asarray([gmap[c]["active_eligible_external_attempt"] for c in case_ids])
    hits = {}
    rr5 = {}
    for branch in S.BRANCHES:
        h = np.zeros(len(case_ids), bool)
        r5 = np.zeros(len(case_ids))
        for i, cid in enumerate(case_ids):
            if not active_mask[i]:
                continue
            y = gmap[cid]["target_address"]
            rk = ranked[branch][cid].index(y) + 1 if y in ranked[branch][cid] else None
            h[i] = rk is not None and rk <= 5
            r5[i] = 1.0 / rk if h[i] else 0.0
        hits[branch] = h
        rr5[branch] = r5

    # wallet clustering frozen recipe; ONE shared resample matrix (frozen rule)
    names = sorted(set(wallets.tolist()))
    indices = [np.flatnonzero((wallets == w) & active_mask) for w in names]
    CFG_SEED, CFG_REP = 27061006, 2000
    rng = np.random.default_rng(CFG_SEED)
    samples = rng.integers(len(names), size=(CFG_REP, len(names)))
    denom = np.asarray([len(ix) for ix in indices])

    def contrast(cand, ref):
        rescue = active_mask & hits[cand] & ~hits[ref]
        harm = active_mask & hits[ref] & ~hits[cand]
        delta_h = hits[cand].astype(float) - hits[ref].astype(float)
        delta_m = rr5[cand] - rr5[ref]
        return dict(
            rescues=int(rescue.sum()), harms=int(harm.sum()),
            net_hits=int(rescue.sum() - harm.sum()),
            Top5=wallet_bootstrap(delta_h, samples, names, indices, denom),
            MRR5=wallet_bootstrap(delta_m, samples, names, indices, denom))

    contrasts = {f"{c}_minus_{r}": contrast(f"{c}_seed0", f"{r}_seed0") for c, r in PRIMARY_PAIRS}
    versus_r0 = {a: contrast(f"{a}_seed0", "r0scores") for a in
                 ("all_history", "recent_actions", "program_roles", "learned_locator")}

    # agreement vs frozen primary_comparisons / versus_R0
    agree = {}
    for name, got in contrasts.items():
        f = frozen["primary_comparisons"][name]
        agree[f"primary/{name}"] = dict(
            rescues=got["rescues"] == f["Top5"]["rescues"],
            harms=got["harms"] == f["Top5"]["harms"],
            net_hits=got["net_hits"] == f["Top5"]["net_hits"],
            Top5_diff_close=abs(got["Top5"]["difference"] - f["Top5"]["difference"]) < 1e-9,
            Top5_ci_close=all(abs(a - b) < 1e-6 for a, b in
                              zip(got["Top5"]["wallet_bootstrap95"], f["Top5"]["wallet_bootstrap95"])),
            MRR5_diff_close=abs(got["MRR5"]["difference"] - f["MRR5"]["difference"]) < 1e-9)
    for arm, got in versus_r0.items():
        f = frozen["versus_R0"][arm]
        agree[f"versus_R0/{arm}"] = dict(
            rescues=got["rescues"] == f["Top5"]["rescues"],
            harms=got["harms"] == f["Top5"]["harms"],
            net_hits=got["net_hits"] == f["Top5"]["net_hits"],
            Top5_diff_close=abs(got["Top5"]["difference"] - f["Top5"]["difference"]) < 1e-9)

    # per-cutoff breakdown (canonical: fixed_pool all_history)
    per_cutoff = {}
    for cut in sorted(set(cutoffs.tolist())):
        m = (cutoffs == cut) & active_mask
        n = int(m.sum())
        per_cutoff[cut] = dict(active_queries=n,
                               Top5=float(hits["all_history_seed0"][m].mean()),
                               MRR5=float(rr5["all_history_seed0"][m].mean()),
                               Recall50=float((ranked["all_history_seed0"] and 0) or 0))
        rec = sum(1 for i in np.flatnonzero(m)
                  if gmap[case_ids[i]]["target_address"] in ranked["all_history_seed0"][case_ids[i]])
        per_cutoff[cut]["Recall50"] = rec / n

    # target-concentration sensitivity
    freq = {}
    for c in case_ids:
        lab = gmap[c]
        if lab["active_eligible_external_attempt"]:
            y = lab["target_address"]
            freq[y] = freq.get(y, 0) + 1
    buckets = {"unique_target": [], "shared_target": []}
    for i, cid in enumerate(case_ids):
        if not active_mask[i]:
            continue
        y = gmap[cid]["target_address"]
        buckets["shared_target" if freq[y] > 1 else "unique_target"].append(i)
    concentration = {}
    for name, idxs in buckets.items():
        n = len(idxs)
        idxs = np.asarray(idxs)
        rec = sum(1 for i in idxs
                  if gmap[case_ids[i]]["target_address"] in ranked["all_history_seed0"][case_ids[i]])
        concentration[name] = dict(active_queries=n,
                                   Top5=float(hits["all_history_seed0"][idxs].mean()) if n else None,
                                   Recall50=(rec / n) if n else None,
                                   distinct_targets=len({gmap[case_ids[i]]["target_address"] for i in idxs}))

    # duplicate/shared-label report (protocol section 5)
    total_future_events = len({(gmap[c]["tx_hash"]) for c in case_ids
                               if gmap[c]["active_eligible_external_attempt"]})
    duplicate_targets = sum(1 for y, k in freq.items() if k > 1)

    result = dict(
        created_for="eth-actions-benchmark-v1.0.0-candidate",
        scope="fixed_pool scoring of frozen v27lean TRAIN baseline; nominal development intervals",
        bootstrap=dict(replicates=CFG_REP, seed=CFG_SEED, shared_resample_matrix=True, resampling="complete sampled wallets; active-query-weighted ratio",
                       interpretation="shared targets/calendar events remain dependent; no multiplicity adjustment; not stable-efficacy evidence"),
        primary_comparisons=contrasts,
        versus_R0=versus_r0,
        agreement_with_frozen=agree,
        per_cutoff_all_history=per_cutoff,
        target_concentration_all_history=concentration,
        label_reporting=dict(active_queries=int(active_mask.sum()),
                             distinct_future_tx_hashes=total_future_events,
                             target_addresses_reused_across_queries=duplicate_targets,
                             note="shared targets are reported per protocol section 5; wallet-cluster bootstrap is the paired inference unit"),
    )
    result["verdict"] = dict(
        rescue_harm_and_ci_reproduced=all(all(v.values()) for v in agree.values()),
        any_disagreement={k: v for k, v in agree.items() if not all(v.values())})
    with open(out_path, "x") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print("wrote", out_path)
    print("verdict:", json.dumps(result["verdict"]))
    for k, v in agree.items():
        if not all(v.values()):
            print("DISAGREE", k, v)


if __name__ == "__main__":
    main()
