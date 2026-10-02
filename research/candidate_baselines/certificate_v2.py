"""Strict offline event certificates. No network or partition discovery here."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

KINDS = {"ordered_path", "shared_token_wedge", "repeat_interaction"}
FAMILIES = {"external_tx", "token_transfer", "internal_trace"}
CAPS = dict(path_peers=64, wallet_events_per_peer=8, peer_tail=256,
            wallet_tokens=32, token_actor_tail=8, proofs_per_kind=4)
BASE_NAMES = ["own_out", "log_out_tx", "last_out_decay", "log_in_tx", "bidirectional",
              "log_global_tx", "log_global_30d_tx", "log_global_7d_tx", "log_age_days",
              "log_wallet_out_tx", "log_wallet_peers", "wallet_entropy"]
CERT_NAMES = ["valid", "log_path_tx", "log_path_peers", "path_recency", "log_path_span",
              "log_wedge_tokens", "log_wedge_tx", "wedge_recency", "log_repeat_tx",
              "repeat_recency", "log_independent_tx", "log_proofs"]
EXTRA_GROUPS = {"native": [0, 1, 2], "burst": [3, 4], "failure": [5, 6],
                "token": [7, 8, 9, 10], "trace": [11, 12], "role": [13, 14]}
EXTRA_NAMES = ["native_log_value_offset", "native_exact_repeat_log", "native_present",
               "wallet_burst_7_30", "candidate_burst_7_30", "pair_failed_frac", "pair_failure_known_frac",
               "token_out_frac", "token_in_frac", "same_token_balance_mean", "log_pair_token_n",
               "internal_frac", "trace_depth_mean", "observed_contract", "log_hub_degree"]


def stable_id(e):
    keys = ("transaction_hash", "event_family", "event_index", "trace_address_json",
            "from_address", "to_address", "token_contract_address", "value_lossless", "quantity")
    return hashlib.sha256(json.dumps([e.get(k, "") for k in keys], separators=(",", ":")).encode()).hexdigest()[:32]


def roles_for(kind):
    return {"ordered_path": ["wallet_to_peer", "peer_to_candidate"],
            "shared_token_wedge": ["wallet_token_event", "candidate_token_event"],
            "repeat_interaction": ["wallet_candidate_event", "wallet_candidate_event"]}[kind]


def verify(proof, lookup):
    """Resolve immutable IDs; distrust serialized event attributes and claimed validity."""
    reasons = []
    kind = proof.get("kind")
    if kind not in KINDS:
        return False, ["unknown_kind"]
    events = []
    for supplied in proof.get("events", []):
        real = lookup(supplied.get("event_id"))
        if real is None:
            reasons.append("event_not_in_ledger")
            continue
        if supplied != real:
            reasons.append("event_attributes_differ")
        if stable_id(real) != real["event_id"]:
            reasons.append("event_identity_mismatch")
        if real["timestamp"] >= proof["cutoff_ts"]:
            reasons.append("future_or_cutoff_event")
        # Independent of integer timestamps, so a resolution bug cannot pass
        # both the history filter and verifier unnoticed.
        if 'block_timestamp' in real:
            iso = datetime.fromisoformat(real['block_timestamp'])
            if int(iso.timestamp()) != real['timestamp']:
                reasons.append('timestamp_unit_mismatch')
            if iso.timestamp() >= proof['cutoff_ts']:
                reasons.append('future_or_cutoff_calendar_event')
        if not real["transaction_hash"] or real["block_number"] < 0 or real["transaction_index"] < 0:
            reasons.append("missing_chain_position")
        if real["event_family"] not in FAMILIES:
            reasons.append("unknown_family")
        events.append(real)
    if len(events) != 2:
        return False, reasons + ["need_two_events"]
    a, b = events
    if proof.get("roles") != roles_for(kind):
        reasons.append("bad_roles")
    if a["transaction_hash"] == b["transaction_hash"]:
        reasons.append("same_transaction_not_independent")
    w, c = proof["wallet"], proof["candidate"]
    if w == c:
        reasons.append("self_candidate")
    if kind == "ordered_path":
        p = proof.get("peer")
        if not p or p in (w, c) or (a["from_address"], a["to_address"], b["from_address"], b["to_address"]) != (w, p, p, c):
            reasons.append("wrong_directed_connection")
        if (a["block_number"], a["transaction_index"]) >= (b["block_number"], b["transaction_index"]) or a["timestamp"] > b["timestamp"]:
            reasons.append("wrong_chain_order")
    elif kind == "shared_token_wedge":
        token = proof.get("token")
        if not token or a["token_contract_address"] != token or b["token_contract_address"] != token:
            reasons.append("wrong_token")
        if a["event_family"] not in ("token", "token_transfer") or b["event_family"] not in ("token", "token_transfer"):
            reasons.append("wedge_not_token_events")
        if w not in (a["from_address"], a["to_address"]) or c not in (b["from_address"], b["to_address"]):
            reasons.append("wedge_wrong_actor")
    else:
        if any({e["from_address"], e["to_address"]} != {w, c} for e in events):
            reasons.append("repeat_wrong_endpoints")
    return not reasons, sorted(set(reasons))


def certificate_features(proofs, cutoff_ts):
    """Only feed independently validated proofs here; support counted by tx sets."""
    by = {k: [p for p in proofs if p["kind"] == k] for k in KINDS}
    def tx(ps):
        return {e["transaction_hash"] for p in ps for e in p["events"]}
    def rec(ps):
        return max((math.exp(-(cutoff_ts - max(e["timestamp"] for e in p["events"])) / (86400 * 90)) for p in ps), default=0.)
    paths, wedges, repeats = (by[k] for k in ("ordered_path", "shared_token_wedge", "repeat_interaction"))
    span = max((abs(p["events"][1]["timestamp"] - p["events"][0]["timestamp"]) / 86400 for p in paths), default=0.)
    return [float(bool(proofs)), math.log1p(len(tx(paths))), math.log1p(len({p["peer"] for p in paths})), rec(paths), math.log1p(span),
            math.log1p(len({p["token"] for p in wedges})), math.log1p(len(tx(wedges))), rec(wedges),
            math.log1p(len(tx(repeats))), rec(repeats), math.log1p(len(tx(proofs))), math.log1p(len(proofs))]
