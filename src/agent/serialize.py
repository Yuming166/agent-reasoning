"""Serialize one panel event into compact, auditable behavioral language.

Everything shown to the LLM is pre-snapshot and label-free: addresses are
anonymized to C0..Ck, and candidates are presented in a FIXED random (hash)
order so position cannot cue the truth. The output JSON schema is strict.
"""
import hashlib
import json

SOURCE_HINT = {
    "new_bridge": "reachable over a 2-hop on-chain path (u->z->c)",
    "new_top2000": "globally popular address the wallet has not interacted with",
    "new_tail": "rare/long-tail address the wallet has not interacted with",
    "repeat_top2000": "globally popular address the wallet has not interacted with",
    "repeat_tail": "rare long-tail address the wallet has not interacted with",
    "repeat_personal": "the wallet's own historical counterparty",
    "unknown_tail": "inactive/very-long-tail address with no observed global outgoing activity in the prior 90d",
    "positive": "",  # rendered identically to negatives; source hidden
}


def _hash_order(cands):
    def h(x):
        return int(hashlib.sha256(str(x).encode()).hexdigest()[:12], 16)
    return sorted(range(len(cands)), key=lambda i: h(cands.iloc[i]["candidate_address"]))


def render_candidate_table(cands):
    """Return (list of dict in display order with cid, table_text)."""
    order = _hash_order(cands.reset_index(drop=True))
    rows, shown = [], []
    for cid, i in enumerate(order):
        r = cands.iloc[i]
        rows.append({"cid": cid, "idx": i,
                     "candidate_address": r.candidate_address})
        src = SOURCE_HINT.get(r.cand_source, "candidate")
        personal = ("yes" if r.personal_cnt > 0 else "no")
        bridge = int(r.bridge_paths)
        lines = [
            f"C{cid}:",
            f"global_inbound_90d={int(r.g_cnt)} (popularity rank {int(r.g_rank) if r.g_rank<900000 else '>200k'})",
            f"wallet_prior_interactions={int(r.personal_cnt)} (days since last={int(r.days_since) if r.days_since<900 else 'never'})",
            f"two_hop_bridge_paths={bridge}",
        ]
        if src:
            lines.append(f"retrieval_hint={src}")
        shown.append(" ".join(lines))
    return rows, "\n".join(shown)


def wallet_context(ev):
    cp_type = "new (not transacted with in the prior 90 days)" if ev.cp_type == "new" \
        else "repeat (seen in the wallet's prior history)"
    return (
        f"- wallet activity (last 90d, pre-snapshot): {int(ev.evt_cnt_90d)} outgoing events, "
        f"active on {int(ev.active_days_90d)} days\n"
        f"- distinct counterparties 90d entropy={float(ev.cp_entropy_90d):.2f}; "
        f"new-counterparty rate (30d)={float(ev.cp_new_rate_30d):.2f}\n"
        f"- the target transaction is with a {cp_type} counterparty"
    )


SYSTEM_FULL = """You are a deterministic on-chain behavior analyzer in a budgeted
multi-agent system. You must operate ONLY through the listed step operators and
emit strict JSON. Do not invent external facts about the anonymized addresses
(C0..Ck); use only the provided pre-snapshot evidence. Each step must cite the
candidate IDs it uses.
Operators: OBSERVE_HISTORY, RUN_COUNTERFACTUAL_MASK, VERIFY_TIMESTAMP,
UPDATE_BELIEF, STOP_AND_PREDICT."""

SYSTEM_NOCF = """You are a deterministic on-chain behavior analyzer. Rank the
anonymized candidate next counterparties using only the provided pre-snapshot
evidence. Emit strict JSON with one prediction; do not invent external facts."""


def step1_prompt(ev, cands, table_text):
    return f"""STEP OBSERVE_HISTORY then STOP_AND_PREDICT (no mask yet).

Wallet under analysis (anonymized; as-of evidence only):
{wallet_context(ev)}

Candidates for the wallet's NEXT outgoing counterparty (anonymized, randomized order):
{table_text}

Task: predict which single candidate is most likely to be the next
counterparty, using popularity, personal recency/frequency, and 2-hop paths.

Respond with ONLY a JSON object of exactly this shape:
{{"steps":["OBSERVE_HISTORY","STOP_AND_PREDICT"],
  "evidence_cids":["C3","C7"],
  "pred_cid":"C?","confidence":0.0-1.0,
  "reason":"<=30 words grounded in the shown fields"}}"""


def step2_mask_prompt(ev, cands, table_text, step1):
    # Counterfactual call is deliberately INDEPENDENT: it does not receive the
    # observation-stage prediction, so masked_pred_cid is a genuine
    # counterfactual ranking rather than an anchored copy.
    return f"""STEP RUN_COUNTERFACTUAL_MASK then VERIFY_TIMESTAMP then
STOP_AND_PREDICT. Independently rank the candidates.

Counterfactual operator: mask the focal wallet's OWN behavioral history
(activity counts, personal frequency/recency). Global popularity and 2-hop
bridge paths remain, because they do not depend on the focal wallet. Use only
evidence that survives the mask.

Candidates (same anonymized set, randomized):
{table_text}

Respond with ONLY a JSON object of exactly this shape:
{{"steps":["RUN_COUNTERFACTUAL_MASK","VERIFY_TIMESTAMP","STOP_AND_PREDICT"],
  "masked_pred_cid":"C?",
  "masked_confidence":0.0-1.0,
  "masked_evidence_cids":["C?"],
  "reason":"<=30 words on what evidence remains after the mask"}}"""


def fuse_prompt(r_obs, r_mask, obs_cid, obs_conf, mask_cid, mask_conf):
    """UPDATE_BELIEF fusion prompt. Ranks are precomputed cheap-rank
    positions (1=best) for the two stage candidates."""
    return f"""STEP UPDATE_BELIEF then STOP_AND_PREDICT. Fuse two independent
rankings of the SAME evidence base:
- OBSERVE_HISTORY prediction: C{obs_cid} (confidence {obs_conf})
- RUN_COUNTERFACTUAL_MASK prediction (wallet history removed): C{mask_cid} (confidence {mask_conf})
- cheap structured-ranker positions (lower=better): observe candidate = {r_obs}, masked candidate = {r_mask}

Decision rule: if the two LLM stages agree, keep that candidate. If they
disagree, choose the candidate supported by the majority of (observe LLM,
masked LLM, cheap ranker); if all three conflict, prefer the candidate whose
evidence survives the mask (global popularity or 2-hop paths). Output only
JSON:
{{"final_pred_cid":"C?","belief_shift":"same|reinforce|weaken|flip",
  "mask_sensitive":true_or_false,"reason":"<=25 words"}}
"""


def nocf_prompt(ev, cands, table_text):
    return f"""Rank candidates for the wallet's NEXT outgoing counterparty from
the provided pre-snapshot evidence only.

Wallet:
{wallet_context(ev)}

Candidates (anonymized, randomized order):
{table_text}

Respond with ONLY a JSON object:
{{"pred_cid":"C?","confidence":0.0-1.0,"evidence_cids":["C?"],"reason":"<=30 words"}}"""
