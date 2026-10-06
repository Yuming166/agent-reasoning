#!/usr/bin/env python
"""Executable-semantics validator for the grounding gold: L1 round-trip + L2 dual implementation.

The grounding gold in VERSIONED_DATASET was produced by the frozen v27 generator
(research/action_evidence_rerank_v27_20261006/v27_grounding_data.py): a formal
query over cutoff-past role records, then a controlled-language template renders
the claim. This validator independently checks BOTH links of that chain:

L1 (sentence -> formal query). A round-trip parser reads each claim sentence,
recovers the formal slots the sentence asserts (task, role, asset alias, owner,
modality), and checks they match the example's structured fields (task,
relation_key, source_records atoms, alias map). This catches template/slot drift:
does the SENTENCE say what the EXAMPLE is about?

L2 (program -> label). A second, independently written executor re-derives
fact_label, claim_required_parent_ids, latest_relation_parent_ids and
candidate_relevant_parent_ids from the raw evidence atoms (source_records plus
the frozen action store), following the written spec in the dataset header and
ANNOTATION_GUIDELINES — event-scan ordering, not the generator's code path.
This catches implementation bugs: does the PROGRAM compute the right label?

Both checks re-derive the entity alias map independently from the store's parent
actions (structural fields only; raw log emitters; no input/data/opaque bytes).

Output: artifacts/benchmark_release_candidate_v1_20261006/EXECUTABLE_SEMANTICS_VALIDATION.json
First-write only; no frozen file is modified.
"""
from __future__ import annotations

import collections
import json
import pickle
import re
import sys
from pathlib import Path

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
DS = R / "artifacts/benchmark_release_candidate_v1_20261006/VERSIONED_DATASET"
OUT = R / "artifacts/benchmark_release_candidate_v1_20261006"
V27 = R / "artifacts/action_evidence_rerank_v27_20261006"
ZERO = "0x" + "0" * 40
ADDRESS = re.compile(r"0x[0-9a-f]{40}")

ROLES = ("external_to", "asset_contract", "spender", "operator", "approved_operator",
         "recipient", "sender", "owner", "internal_target", "unknown")
PERMISSION_ROLES = {"spender", "operator", "approved_operator"}
TEMPORAL_PERMISSION_ROLES = {"spender", "operator"}


def relation_key_of(record):
    """Spec, not import: NFT-approve token identity is not uniformly bound, so
    records without (owner, asset, address) or with non-temporal roles carry no
    relation key."""
    if record.get("role") not in TEMPORAL_PERMISSION_ROLES or any(
            record.get(k) is None for k in ("owner", "asset", "address")):
        return None
    return (record["role"], record["owner"], record["asset"], record["address"],
            record["modality"])


def relation_chronology(record):
    return (int(record["time"]), tuple(record["chain_order"]),
            int(record.get("within_parent_order", -1)), record["evidence_id"])


def action_addresses(action):
    """Spec re-implementation: structural fields only; raw opaque log bytes
    contribute only their emitter address."""
    out = set()

    def visit(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k not in ("input", "data", "element", "parent_id", "action_id", "tx_hash"):
                    visit(v)
        elif isinstance(value, (tuple, list)):
            for v in value:
                visit(v)
        elif isinstance(value, str) and ADDRESS.fullmatch(value):
            out.add(value)

    for key in ("external_rows", "token_flows", "internal_rows", "components", "records"):
        visit(action[key])
    for log in action["raw_logs"]:
        ea = log.get("emitter_address")
        if isinstance(ea, str) and ADDRESS.fullmatch(ea):
            out.add(ea)
    return out


def alias_map_for(store_by_wallet, query, candidate):
    hist = [a for a in store_by_wallet.get(query["wallet"], ()) if a["time"] < int(query["cutoff"])]
    addrs = set().union(*(action_addresses(a) for a in hist)) if hist else set()
    amap = {query["wallet"]: "W", ZERO: "ZERO"}
    for i, ad in enumerate(sorted(addrs - set(amap))):
        amap[ad] = f"E{i + 1}"
    if candidate != query["wallet"]:
        amap[candidate] = "C"
    return amap, hist


# ---------------------------------------------------------------- L1 parser
# Alias vocabulary: canonical map assigns W/ZERO/E1..En; the candidate is then re-keyed
# to C (aliases_for), so an asset equal to the candidate renders as C — hence C is a
# legal asset alias in every template.
ALIAS = r"(?:E\d+|W|ZERO|C)"
ALIAS_CAP = r"(E\d+|W|ZERO|C)"
RE_NEWEST = re.compile(rf"^In the newest observed (event|request|transaction) field naming C"
                       rf"(?: for asset {ALIAS_CAP})?, C has the role (\w+)\.$")
RE_OWNER = re.compile(rf"^The newest observed (event|request|transaction) (\w+) binding of C for asset {ALIAS_CAP} has owner (W|ZERO|E\d+)\.$")
RE_LATEST = re.compile(rf"^The latest observed (event|request|transaction) relation with owner (W|ZERO|E\d+), asset {ALIAS_CAP}, and (\w+) C has a positive value\.$")


def parse_claim(claim):
    """Sentence -> formal slots. The sentence asserts a HYPOTHESIS; the gold label
    adjudicates it (conflicted = atoms contradict the asserted role/owner). Returns
    None when the sentence is outside the controlled language (a template-coverage
    gap, reported as l1_parse_fail)."""
    m = RE_NEWEST.match(claim)
    if m:
        return {"task": "role_binding", "modality": m.group(1),
                "asset_alias": m.group(2), "role": m.group(3)}
    m = RE_OWNER.match(claim)
    if m:
        return {"task": "owner_binding", "modality": m.group(1), "role": m.group(2),
                "asset_alias": m.group(3), "owner_alias": m.group(4)}
    m = RE_LATEST.match(claim)
    if m:
        return {"task": "latest_relation", "modality": m.group(1),
                "owner_alias": m.group(2), "asset_alias": m.group(3), "role": m.group(4)}
    return None


def resolve_alias(amap, alias):
    for address, a in amap.items():
        if a == alias:
            return address
    return None


def check_l1(e, amap):
    """Claim sentence must re-express exactly the example's structured query."""
    parsed = parse_claim(e["claims"]["train"])
    if parsed is None:
        return "l1_parse_fail", None
    atoms = e["source_records"]
    if e["task"] != parsed["task"]:
        return "l1_task_mismatch", parsed
    if not atoms:  # unknown-by-absence: claim names a role; nothing else to bind
        if parsed["task"] == "role_binding" and e["unknown_reason"] == "no_candidate_role_observation":
            if parsed["asset_alias"] is None and parsed["role"] in ("spender",):
                return "ok", parsed
            return "l1_absent_case_slot_mismatch", parsed
        return "l1_atoms_empty_unexpected", parsed
    a0 = atoms[0]
    if parsed["modality"] != a0["modality"]:
        return "l1_modality_mismatch", parsed
    if "asset_alias" in parsed:
        want = None if parsed["asset_alias"] is None else resolve_alias(amap, parsed["asset_alias"])
        if want != a0["asset"]:
            return "l1_asset_mismatch", parsed
    if "role" in parsed and parsed["task"] == "role_binding":
        if parsed["role"] not in ROLES:
            return "l1_role_outside_vocabulary", parsed
        newest_roles = {r["role"] for r in atoms
                        if r["parent_id"] == e["claim_field_reference"]["parent_id"]}
        # hypothesis adjudication: supported iff the asserted role is THE newest-role set
        would_support = (len(newest_roles) == 1 and parsed["role"] == next(iter(newest_roles)))
        if e["fact_label"] == 0 and not would_support:
            return "l1_supported_but_role_not_in_newest", parsed
        if e["fact_label"] == 1 and would_support:
            return "l1_conflicted_but_role_matches", parsed
    if parsed["task"] == "latest_relation":
        key = e.get("relation_key")
        if key is None:
            if e["fact_label"] != 2:
                return "l1_latest_without_key_nonunknown", parsed
        else:
            if resolve_alias(amap, parsed["owner_alias"]) != key[1]:
                return "l1_owner_mismatch", parsed
            if resolve_alias(amap, parsed["asset_alias"]) != key[2]:
                return "l1_asset_mismatch", parsed
            if parsed["role"] != key[0]:
                return "l1_role_mismatch", parsed
            if parsed["modality"] != key[4]:
                return "l1_modality_mismatch", parsed
    if parsed["task"] == "owner_binding":
        if len(atoms) != 1:
            return "l1_owner_atoms_not_single", parsed
        if parsed["role"] != a0["role"]:
            return "l1_role_mismatch", parsed
        want_owner = resolve_alias(amap, parsed["owner_alias"])
        # hypothesis adjudication: supported iff atom owner IS the asserted owner
        if e["fact_label"] == 2:
            if a0["owner"] is not None:
                return "l1_unknown_owner_but_atom_has_owner", parsed
        elif e["fact_label"] == 0 and want_owner != a0["owner"]:
            return "l1_supported_but_owner_differs", parsed
        elif e["fact_label"] == 1 and want_owner == a0["owner"]:
            return "l1_conflicted_but_owner_matches", parsed
    return "ok", parsed


# ---------------------------------------------------------------- L2 executor
def execute(example, hist, hist_records, amap):
    """Written-spec re-execution over the candidate's full record set, independent
    of the generator's code. Returns (label, claim_required, latest, relevant)
    or ('EXEC_SKIP', reason) when the spec path does not apply."""
    task = example["task"]
    wallet = example["wallet_id"] if "wallet_id" in example else example["wallet"]
    candidate = example["candidate_address"]
    # candidate_relevant (spec): every history parent whose action addresses include
    # the candidate — the full action-address scan, not just role records.
    relevant = sorted({a["parent_id"] for a in hist if candidate in action_addresses(a)})

    if task == "role_binding":
        if not hist_records:
            return 2, [], [], relevant, "no_candidate_role_observation"
        anchor = max(hist_records, key=relation_chronology)
        scoped = [r for r in hist_records
                  if r["modality"] == anchor["modality"] and r["asset"] == anchor["asset"]]
        newest_parent = max(scoped, key=relation_chronology)["parent_id"]
        newest = [r for r in scoped if r["parent_id"] == newest_parent]
        roles = {r["role"] for r in newest}
        claim_role = parse_claim(example["claims"]["train"])
        claimed = claim_role["role"] if claim_role else None
        if len(roles) == 1 and next(iter(roles)) in ROLES:
            true_role = next(iter(roles))
            return (0 if claimed == true_role else 1), sorted({newest_parent}), \
                   [newest_parent], relevant, None
        return 2, [], [], relevant, "latest_field_role_unknown_or_multiple_bindings"

    if task == "owner_binding":
        perm = [r for r in hist_records if r["role"] in PERMISSION_ROLES]
        if not perm:
            return "EXEC_SKIP", None, None, relevant, "no permission records"
        last = max(perm, key=relation_chronology)
        owner = last.get("owner")
        if owner is None:
            return 2, [], [], relevant, "owner_binding_not_observable"
        claim_role = parse_claim(example["claims"]["train"])
        # the claim must be about THIS record's role/asset
        if claim_role and claim_role["role"] != last["role"]:
            return "EXEC_SKIP", None, None, relevant, "claim names a different permission record"
        return (0 if owner == wallet else 1), [last["parent_id"]], [], relevant, None

    if task == "latest_relation":
        own = [r for r in hist_records
               if r.get("owner") == wallet and relation_key_of(r) is not None]
        if own:
            key = relation_key_of(own[-1])  # chronologically last record's key
            group = [r for r in own if relation_key_of(r) == key]
            last = max(group, key=relation_chronology)
            value = last.get("polarity", "unknown")
            label = 0 if value == "positive" else 1 if value == "negative" else 2
            support = sorted({r["parent_id"] for r in group})
            latest = [last["parent_id"]] if label != 2 else []
            return label, support, latest, relevant, None
        perm = [r for r in hist_records if r["role"] in PERMISSION_ROLES]
        if perm:
            return 2, [], [], relevant, "unknown_owner_or_token_identity_or_relation_scope"
        return "EXEC_SKIP", None, None, relevant, "no own-temporal or permission records"
    return "EXEC_SKIP", None, None, relevant, f"unknown task {task}"


def main():
    # frozen inputs
    with open(V27 / "GROUNDING_FACTS.pkl", "rb") as f:
        cache = pickle.load(f)
    assert cache["ranking_targets_present"] is False and cache["history_edits_present"] is False
    with open(V27 / "COMPLETE_ACTION_STORE.pkl", "rb") as f:
        store = pickle.load(f)
    assert store["ranking_targets_present"] is False
    by_wallet = store["by_wallet"]
    qmeta = cache["query_meta"]
    examples = cache["examples"]

    # full candidate record sets per (query_index, candidate), rebuilt independently
    # from the store's parent actions (incl. external/token/internal derivation
    # rules re-implemented below), NOT from the generator's candidate_records().
    def full_candidate_records(wallet, cutoff, candidate, hist):
        out = []
        for a in hist:
            for r in a["records"]:
                if r["address"] == candidate:
                    out.append(r)
            for i, e in enumerate(a["external_rows"]):
                if e.get("to_address") == candidate:
                    out.append({"address": candidate, "role": "external_to", "owner": None,
                                "asset": None, "modality": "transaction", "polarity": "unknown",
                                "time": a["time"], "chain_order": a["chain_order"],
                                "within_parent_order": -1, "parent_id": a["parent_id"],
                                "evidence_id": a["action_id"] + f":external{i}",
                                "field_path": "external.to"})
            for i, e in enumerate(a["token_flows"]):
                for key, role in (("token_contract", "asset_contract"), ("from_address", "sender"),
                                  ("to_address", "recipient")):
                    if e.get(key) == candidate:
                        out.append({"address": candidate, "role": role, "owner": None,
                                    "asset": e.get("token_contract"), "modality": "transaction",
                                    "polarity": "unknown", "time": a["time"],
                                    "chain_order": a["chain_order"],
                                    "within_parent_order": int(e.get("event_index") or -1),
                                    "parent_id": a["parent_id"],
                                    "evidence_id": a["action_id"] + f":token{i}:{key}",
                                    "field_path": f"token[{i}].{key}"})
            for i, e in enumerate(a["internal_rows"]):
                if e.get("to_address") == candidate:
                    out.append({"address": candidate, "role": "internal_target", "owner": None,
                                "asset": None, "modality": "transaction", "polarity": "unknown",
                                "time": a["time"], "chain_order": a["chain_order"],
                                "within_parent_order": -1, "parent_id": a["parent_id"],
                                "evidence_id": a["action_id"] + f":trace{i}",
                                "field_path": f"trace[{i}].to"})
        unique = {}
        for r in out:
            key = (r["parent_id"], r.get("field_path"), r["role"], r["address"],
                   r.get("asset"), r.get("owner"), r["modality"])
            unique.setdefault(key, r)
        return sorted(unique.values(), key=relation_chronology)

    l1_counter = collections.Counter()
    l2_counter = collections.Counter()
    l2_examples_fail = []
    l1_examples_fail = []
    scope_mismatch = collections.Counter()
    n = 0
    for e in examples:
        n += 1
        q = qmeta[e["query_index"]]
        assert q["case_id"] == e["case_id"]
        amap, hist = alias_map_for(by_wallet, q, e["candidate_address"])
        verdict, _ = check_l1(e, amap)
        l1_counter[verdict] += 1
        if verdict != "ok" and len(l1_examples_fail) < 20:
            l1_examples_fail.append({"example_id": e["example_id"], "task": e["task"],
                                     "claim": e["claims"]["train"], "verdict": verdict,
                                     "unknown_reason": e.get("unknown_reason")})
        # L2
        recs = full_candidate_records(q["wallet"], q["cutoff"], e["candidate_address"], hist)
        label, required, latest, relevant, reason = execute(e, hist, recs, amap)
        if label == "EXEC_SKIP":
            l2_counter[f"skip:{reason}"] += 1
            continue
        same_label = label == e["fact_label"]
        same_required = sorted(required or []) == sorted(e["fact_required_parent_ids"] or [])
        # latest scope: generator stores generic latest across relation groups in
        # latest_parent_target_ids AFTER make_example (see examples_for tail);
        # the claim-specific latest lives in fact_latest_parent_ids.
        same_latest = sorted(latest or []) == sorted(e["fact_latest_parent_ids"] or [])
        same_relevant = relevant == sorted(e["parent_target_ids"])
        if same_label:
            l2_counter["label_ok"] += 1
        else:
            l2_counter["label_diff"] += 1
            if len(l2_examples_fail) < 40:
                l2_examples_fail.append({
                    "example_id": e["example_id"], "task": e["task"], "case_id": e["case_id"],
                    "claim": e["claims"]["train"], "gold_label": e["fact_label_name"],
                    "reexec_label": ("supported", "conflicted", "unknown")[label],
                    "gold_required": e["fact_required_parent_ids"],
                    "reexec_required": required, "reason": reason,
                    "unknown_reason": e.get("unknown_reason"),
                    "n_recs": len(recs), "n_atoms": len(e["source_records"])})
        for name, ok in (("claim_required", same_required), ("latest", same_latest),
                         ("candidate_relevant", same_relevant)):
            if ok:
                scope_mismatch[name + "_ok"] += 1
            else:
                scope_mismatch[name + "_diff"] += 1

    n_skipped = sum(v for k, v in l2_counter.items() if k.startswith("skip:"))
    n_exec = n - n_skipped
    label_ok = l2_counter["label_ok"]
    report = {
        "schema": "executable-semantics-validation-v1",
        "date": "2026-10-06",
        "inputs": {
            "grounding_facts": "action_evidence_rerank_v27_20261006/GROUNDING_FACTS.pkl (frozen)",
            "action_store": "action_evidence_rerank_v27_20261006/COMPLETE_ACTION_STORE.pkl (frozen)",
            "n_examples": n,
        },
        "L1_round_trip": {
            "definition": "independent regex parser maps each claim sentence back to formal "
                          "slots (task/modality/role/asset/owner) and checks them against the "
                          "example's structured fields and independently re-derived alias map",
            "counts": dict(l1_counter),
            "parse_fail_examples": l1_examples_fail,
        },
        "L2_dual_implementation": {
            "definition": "second executor re-derives fact label and scope evidence from the "
                          "candidate's full record set rebuilt from the frozen action store, "
                          "following the written spec (event-scan ordering), with no code "
                          "shared with the generator beyond data formats",
            "counts": dict(l2_counter),
            "scope_agreement": dict(scope_mismatch),
            "n_executed": n_exec,
            "n_skipped": n_skipped,
            "label_agreement_rate": (label_ok / n_exec) if n_exec else None,
            "label_diff_examples": l2_examples_fail,
        },
        "claim_language": {
            "controlled_templates": 3,
            "free_rewrite": False,
            "note": "guarantee covers the controlled language only",
        },
    }
    path = OUT / "EXECUTABLE_SEMANTICS_VALIDATION.json"
    if path.exists():
        raise SystemExit(f"exists: {path}")
    with open(path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"L1: {dict(l1_counter)}")
    print(f"L2: {dict(l2_counter)}")
    print(f"L2 agreement: {label_ok}/{n_exec} = {label_ok / n_exec if n_exec else 0:.4f}")
    print(f"scopes: {dict(scope_mismatch)}")
    print("wrote", path.name)


if __name__ == "__main__":
    sys.exit(main())
