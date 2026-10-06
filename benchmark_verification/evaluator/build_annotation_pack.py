#!/usr/bin/env python
"""Stage E part 1: blind annotation pack builder.

Builds the 20-wallet pilot pack (priority) plus the UNEXECUTED budget plan
(200 random core + up to 80 difficulty-layer wallets). Everything a human
annotator sees is history-only: program answers (forecast target, grounding
parent ids, fact labels), predictions and future windows are never included.
Difficulty layers use ONLY history structure/missingness/binding rules
(SEMANTIC_COVERAGE predefined_difficulty_layers), never method wins/losses.

Outputs (first-write only) under ANNOTATION_PACK/:
  pilot20/{wallet_list.json, groundings_to_annotate.jsonl, forecast_windows_to_annotate.jsonl}
  BUDGET_PLAN_200CORE_80CHALLENGE.json (unexecuted, wallet lists only)
Human-judgment fields are EMPTY placeholders; nothing is filled.
"""
from __future__ import annotations

import gzip
import json
import random
from pathlib import Path

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
DS = R / "artifacts/benchmark_release_candidate_v1_20261006/VERSIONED_DATASET"
OUTDIR = R / "artifacts/benchmark_release_candidate_v1_20261006/ANNOTATION_PACK"


def read_jsonl(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def iter_gz(p):
    with gzip.open(p, "rt") as f:
        for line in f:
            yield json.loads(line)


def wallet_of(qid):
    # query_id format: v19_<cutoff>_<wallet>
    return qid.split("_", 2)[2]


def main():
    if OUTDIR.exists():
        raise SystemExit("exists")
    (OUTDIR / "pilot20").mkdir(parents=True)

    queries = read_jsonl(DS / "queries/train.jsonl")
    grounding = read_jsonl(DS / "grounding_gold/train.jsonl")
    grounding = grounding[1:]  # header row
    qmap = {q["query_id"]: q for q in queries}

    wallets = sorted({q["wallet_id"] for q in queries})
    rng = random.Random(20261006)  # frozen pilot draw seed
    pilot = sorted(rng.sample(wallets, 20))
    with open(OUTDIR / "pilot20/wallet_list.json", "x") as f:
        json.dump({"draw": "20 wallets uniform without replacement from 600 TRAIN wallets",
                   "seed": 20261006, "wallets": pilot}, f, indent=1)

    # grounding examples of pilot wallets, with gold fields STRIPPED
    kept = stripped = 0
    with open(OUTDIR / "pilot20/groundings_to_annotate.jsonl", "x") as f:
        for g in grounding:
            if g["wallet_id"] not in pilot:
                continue
            kept += 1
            # blind row: history refs + claims + candidate; NO gold scope lists,
            # NO fact_label; the annotator fills judgment fields (left empty)
            f.write(json.dumps({
                "example_id": g["example_id"], "group_id": g["group_id"],
                "case_id": g["case_id"], "cutoff_UTC_seconds": g["cutoff_UTC_seconds"],
                "task": g["task"], "candidate_address": g["candidate_address"],
                "claims": g["claims"],
                "history_parent_refs": qmap[g["case_id"]]["history_parent_refs"],
                "entity_alias_map": qmap[g["case_id"]]["entity_alias_map"],
                "annotation_fields": {
                    "annotator_1_raw_judgment": None,
                    "annotator_2_raw_judgment": None,
                    "per_scope_parent_ids_by_human": {
                        "candidate_relevant_parent_ids": None,
                        "claim_required_parent_ids": None,
                        "latest_relation_parent_ids": None},
                    "fact_label_by_human": None,
                    "dispute_adjudication": None,
                    "agreement_computation": None,
                    "all_fields_empty_until_humans_fill_them": True,
                },
                "human_status": "pending",
            }, ensure_ascii=False) + "\n")

    # forecast windows for pilot wallets: history-only; the human lists qualifying
    # outgoing external attempts in the FOLLOWING 7 days from materials THEY are
    # given in a separate, access-controlled step (not in this pack).
    n_fw = 0
    with open(OUTDIR / "pilot20/forecast_windows_to_annotate.jsonl", "x") as f:
        for q in queries:
            if q["wallet_id"] not in pilot:
                continue
            n_fw += 1
            f.write(json.dumps({
                "query_id": q["query_id"], "wallet_id": q["wallet_id"],
                "cutoff": q["cutoff"], "cutoff_UTC_seconds": q["cutoff_UTC_seconds"],
                "window_end_exclusive_UTC_seconds": q["cutoff_UTC_seconds"] + 7 * 86400,
                "instruction": "从独立提供的窗口源材料中列出合格 outgoing external attempt(定义见 "
                               "ANNOTATION_GUIDELINES);本包不含任何未来数据",
                "annotation_fields": {
                    "annotator_1_raw_list": None, "annotator_2_raw_list": None,
                    "dispute_adjudication": None, "agreement_computation": None,
                    "all_fields_empty_until_humans_fill_them": True},
                "human_status": "pending",
            }, ensure_ascii=False) + "\n")

    # ---------- UNEXECUTED budget plan: 200 core + up to 80 challenge ----------
    rng2 = random.Random(20261007)
    rest = [w for w in wallets if w not in set(pilot)]
    core = sorted(rng2.sample(rest, 200))
    # difficulty layers from history structure ONLY (train split)
    # layer A: multi-parent claim-required structure (>=2 grounding examples in a
    #          group with multi-action claims implied by task==role_binding groups)
    # layer B: missing-semantics (wallet has parents with raw_transaction null and
    #          external rows present)
    # layer C: rare/candidate-heavy (wallet with the most grounding examples)
    from collections import Counter, defaultdict
    gex = Counter(g["wallet_id"] for g in grounding)
    miss_wallets = set()
    n_tx_null_seen = Counter()
    for v in iter_gz(DS / "action_views/train.jsonl.gz"):
        rp = v.get("structured_facts", {}).get("request_packet", {})
        if isinstance(rp, dict) and rp.get("state") == "unknown_missing_raw_transaction":
            n_tx_null_seen[v["wallet"]] += 1
    miss_wallets = {w for w, c in n_tx_null_seen.items() if c >= 5}
    challenge_pool = sorted(set(gex) & (miss_wallets | {w for w, _ in gex.most_common(120)}))
    challenge = sorted(rng2.sample(challenge_pool, min(80, len(challenge_pool)))) if challenge_pool else []
    with open(OUTDIR / "BUDGET_PLAN_200CORE_80CHALLENGE.json", "x") as f:
        json.dump({
            "status": "unexecuted_budget_option",
            "core200_draw": {"seed": 20261007, "wallets": core},
            "challenge_up_to_80_draw": {"seed": 20261007,
                "layer_rule": "wallets having grounding examples AND (>=5 parents with "
                              "unknown_missing_raw_transaction OR top-120 grounding-example counts); "
                              "history structure/missingness only, never method outcomes",
                "layer_counts": {"missing_semantics_wallets": len(miss_wallets),
                                  "challenge_pool": len(challenge_pool)},
                "wallets": challenge},
            "natural_rare_layer_policy": "稀有层不足时全取并如实报告;不用合成样例冒充自然样本",
            "execution": "not started; requires human resources before any run",
        }, f, indent=1, ensure_ascii=False)

    print(f"pilot20: {len(pilot)} wallets, grounding rows {kept}, forecast windows {n_fw}; "
          f"budget plan: core {len(core)}, challenge {len(challenge)} (unexecuted)")


if __name__ == "__main__":
    main()
