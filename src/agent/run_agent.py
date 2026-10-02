#!/usr/bin/env python3
"""Stage D step 2: run cheap vs deliberation (full counterfactual FSM vs
no-CF one-shot) on the frozen panel and log measured cost per event.

Arms:
  cheap         : frozen June-trained HistGBM structured ranker, no LLM
  delib_full    : OBSERVE_HISTORY -> RUN_COUNTERFACTUAL_MASK -> UPDATE -> STOP
                  (two real LLM calls; counterfactual operator)
  delib_nocf    : one-shot LLM ranking (same model/context, no mask operator)

Every LLM output is parsed strictly; failures are scored by a conservative
rule (fall back to cheap ordering) and counted, never dropped. Results are
appended incrementally so interrupted runs are resumable.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.data import EVENT_KEY, PANEL_DIR  # noqa: E402
from agent.llm_client import DEFAULT_MODEL, chat  # noqa: E402
from agent.serialize import (SYSTEM_FULL, SYSTEM_NOCF, fuse_prompt,  # noqa: E402
                             nocf_prompt, render_candidate_table, step1_prompt,
                             step2_mask_prompt)


def parse_json_lenient(text):
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\{.*\}", t, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def cid_to_idx(cid, display):
    if cid is None:
        return None
    m = re.search(r"(\d+)", str(cid))
    if not m:
        return None
    k = int(m.group(1))
    for row in display:
        if row["cid"] == k:
            return row["idx"]
    return None


def cheap_rank(cands):
    order = cands.sort_values("cheap_score", ascending=False).reset_index(drop=True)
    return order


def cheap_tie_ranks(cands):
    """Competition ranks with average positions for exact score ties."""
    order = cands.sort_values(["cheap_score", "candidate_address"],
                              ascending=[False, True]).reset_index(drop=True)
    ranks = order.cheap_score.rank(method="average", ascending=False).to_numpy()
    return order, ranks


def cheap_rr_for_addr(order, ranks, addr):
    hit = order.index[order.candidate_address == addr]
    if len(hit) == 0:
        return 0.0, float(len(order) + 1), False
    i = int(hit[0])
    r = float(ranks[i])
    return 1.0 / r, r, True


def rr_of(cands, chosen_addr):
    if chosen_addr is None:
        return None
    order = cands.sort_values("cheap_score", ascending=False).reset_index(drop=True)
    hit = order.index[order.candidate_address == chosen_addr]
    if len(hit) == 0:
        # chosen candidate not in pool: worst rank = pool size + 1 penalty
        return 1.0 / (len(order) + 1)
    rank = int(hit[0]) + 1
    return 1.0 / rank, rank


def _idx_of(parsed, key, display):
    return cid_to_idx(parsed.get(key) if parsed else None, display)


def audited_chat(messages, model, max_tokens):
    """Call chat while retaining only a non-secret error class for reruns."""
    try:
        out = chat(messages, model=model, max_tokens=max_tokens)
        if not isinstance(out, dict):
            return {"content": "", "usage": {}, "model": model,
                    "error": "InvalidClientResponse"}
        return out
    except Exception as exc:  # keep one event record instead of dropping it
        return {"content": "", "usage": {}, "model": model,
                "error": type(exc).__name__}


def response_status(response, parsed, required_key, mapped_idx):
    """Classify a persisted rerun response without retaining its content."""
    if response.get("error"):
        return "client_or_transport_error"
    if not response.get("content"):
        return "empty_response"
    if parsed is None:
        return "unparseable_json_or_nonobject"
    if required_key not in parsed:
        return "missing_required_field"
    if mapped_idx is None:
        return "unknown_or_invalid_candidate_id"
    return "ok"


def stage_audit(response, parsed, required_key, mapped_idx, elapsed):
    usage = response.get("usage") or {}
    return {
        "status": response_status(response, parsed, required_key, mapped_idx),
        "client_error": int(bool(response.get("error"))),
        "content_nonempty": int(bool(response.get("content"))),
        "response_model": str(response.get("model") or ""),
        "finish_reason": str(response.get("finish_reason") or ""),
        "reasoning_nonempty": int(bool(response.get("reasoning_nonempty"))),
        "usage_prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "usage_completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "usage_total_tokens": int(usage.get("total_tokens", 0) or 0),
        "latency_s": round(float(elapsed), 3),
    }


def run_one_event(args_tuple):
    if len(args_tuple) == 5:
        ev, cands, model, run_nocf, max_tokens = args_tuple
        audit_details = False
    else:
        ev, cands, model, run_nocf, max_tokens, audit_details = args_tuple
    key = {"snapshot_date": ev.snapshot_date,
           "target_address": ev.target_address,
           "target_sequence_index": ev.target_sequence_index}
    display, table_text = render_candidate_table(cands)
    wall0 = time.time()
    calls, latency = 0, 0.0
    tok = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    audit = {}

    def add_usage(u):
        for k in tok:
            tok[k] += int((u or {}).get(k, 0) or 0)

    # STEP 1 OBSERVE_HISTORY -> STOP_AND_PREDICT
    t = time.time()
    s1 = audited_chat([
        {"role": "system", "content": SYSTEM_FULL},
        {"role": "user", "content": step1_prompt(ev, cands, table_text)},
    ], model=model, max_tokens=max_tokens)
    latency += time.time() - t
    calls += 1
    add_usage(s1.get("usage"))
    p1 = parse_json_lenient(s1.get("content", ""))
    obs_idx = _idx_of(p1, "pred_cid", display)
    if audit_details:
        audit["step1"] = stage_audit(s1, p1, "pred_cid", obs_idx, time.time() - t)

    # STEP 2 RUN_COUNTERFACTUAL_MASK (independent; no observation answer)
    t = time.time()
    s2 = audited_chat([
        {"role": "system", "content": SYSTEM_FULL},
        {"role": "user", "content": step2_mask_prompt(ev, cands, table_text, p1 or {})},
    ], model=model, max_tokens=max_tokens)
    latency += time.time() - t
    calls += 1
    add_usage(s2.get("usage"))
    p2 = parse_json_lenient(s2.get("content", ""))
    mask_idx = _idx_of(p2, "masked_pred_cid", display)
    if audit_details:
        audit["step2"] = stage_audit(s2, p2, "masked_pred_cid", mask_idx, time.time() - t)

    # cheap order used as the fusion tie-breaker
    order_pre = cheap_rank(cands).reset_index(drop=True)
    def cheap_pos(idx):
        if idx is None:
            return None
        addr = cands.iloc[idx].candidate_address
        hit = order_pre.index[order_pre.candidate_address == addr]
        return int(hit[0]) + 1 if len(hit) else None

    # STEP 3 UPDATE_BELIEF fusion (small adjudication call)
    belief_shift, mask_sensitive, full_idx = None, None, None
    if obs_idx is not None and mask_idx is not None:
        mask_sensitive = int(mask_idx != obs_idx)
        t = time.time()
        s3 = audited_chat([
            {"role": "system", "content": SYSTEM_FULL},
            {"role": "user", "content": fuse_prompt(
                cheap_pos(obs_idx), cheap_pos(mask_idx),
                (p1 or {}).get("pred_cid"), (p1 or {}).get("confidence"),
                (p2 or {}).get("masked_pred_cid"), (p2 or {}).get("masked_confidence"))},
        ], model=model, max_tokens=300)
        latency += time.time() - t
        calls += 1
        add_usage(s3.get("usage"))
        p3 = parse_json_lenient(s3.get("content", ""))
        if audit_details:
            audit["step3"] = stage_audit(s3, p3, "final_pred_cid",
                                          _idx_of(p3, "final_pred_cid", display),
                                          time.time() - t)
        belief_shift = (p3 or {}).get("belief_shift")
        mask_sensitive = (p3 or {}).get("mask_sensitive", mask_sensitive)
        full_idx = _idx_of(p3, "final_pred_cid", display)
    elif audit_details:
        audit["step3"] = {
            "status": "skipped_prior_stage_parse", "client_error": 0,
            "content_nonempty": 0, "usage_prompt_tokens": 0,
            "usage_completion_tokens": 0, "usage_total_tokens": 0,
            "latency_s": 0.0,
        }
    # deterministic fallback (no extra LLM): agree->that; disagree->masked
    if full_idx is None:
        if mask_idx is not None:
            full_idx = mask_idx
        elif obs_idx is not None:
            full_idx = obs_idx
    steps_ok = int(obs_idx is not None and mask_idx is not None and full_idx is not None)
    full_addr = cands.iloc[full_idx].candidate_address if full_idx is not None else None

    # no-CF ablation arm (single-shot, same model/context)
    nocf_addr, nocf_usage, nocf_ok = None, {}, False
    if run_nocf:
        t = time.time()
        s4 = audited_chat([
            {"role": "system", "content": SYSTEM_NOCF},
            {"role": "user", "content": nocf_prompt(ev, cands, table_text)},
        ], model=model, max_tokens=max_tokens)
        latency += time.time() - t
        calls += 1
        nocf_usage = s4.get("usage") or {}
        add_usage(nocf_usage)
        p4 = parse_json_lenient(s4.get("content", ""))
        ni = _idx_of(p4, "pred_cid", display)
        if audit_details:
            audit["step4"] = stage_audit(s4, p4, "pred_cid", ni, time.time() - t)
        if ni is not None:
            nocf_addr = cands.iloc[ni].candidate_address
            nocf_ok = True

    latency += max(0.0, time.time() - wall0 - latency)
    # Scoring uses average competition ranks for exact cheap-score ties: the
    # frozen ranker cannot distinguish zero-feature unknown candidates, so a
    # deterministic CSV ordering would be an arbitrary tie-break.
    tie_order, tie_ranks = cheap_tie_ranks(cands)
    truth = ev.counterparty_address
    cheap_rr, cheap_rank_pos, truth_supported = cheap_rr_for_addr(
        tie_order, tie_ranks, truth)

    def addr_rank(addr):
        if addr is None:
            return None, None
        rr, rank, _ = cheap_rr_for_addr(tie_order, tie_ranks, addr)
        return rank, rr

    def idx_rank(i):
        if i is None:
            return None
        addr = cands.iloc[i].candidate_address
        r, _ = addr_rank(addr)
        return r

    full_rank, full_rr = addr_rank(full_addr)
    nocf_rank, nocf_rr = addr_rank(nocf_addr)
    obs_rank_pos = idx_rank(obs_idx)
    mask_rank_pos = idx_rank(mask_idx)
    result = {
        **key,
        "cp_type": ev.cp_type, "stratum": ev.stratum, "activity": ev.activity,
        "pop_weight": float(ev.pop_weight), "pool_n": int(len(cands)),
        "truth_in_pool": int(truth_supported),
        "cheap_rank": cheap_rank_pos, "cheap_rr": cheap_rr,
        "obs_rank": obs_rank_pos,
        "mask_rank": mask_rank_pos,
        "full_rank": full_rank, "full_rr": full_rr,
        "full_parse_ok": steps_ok,
        "belief_shift": belief_shift, "mask_sensitive": mask_sensitive,
        "nocf_rank": nocf_rank, "nocf_rr": nocf_rr,
        "nocf_parse_ok": int(nocf_ok) if run_nocf else None,
        "llm_calls": calls,
        "prompt_tokens": tok["prompt_tokens"],
        "completion_tokens": tok["completion_tokens"],
        "total_tokens": tok["total_tokens"],
        "nocf_total_tokens": nocf_usage.get("total_tokens"),
        "latency_s": round(latency, 3),
        "model": model,
    }
    if audit_details:
        result.update({
            "audit_step1_status": audit["step1"]["status"],
            "audit_step2_status": audit["step2"]["status"],
            "audit_step3_status": audit["step3"]["status"],
            "audit_step4_status": audit.get("step4", {}).get("status", "skipped_no_nocf"),
            "audit_step1_client_error": audit["step1"]["client_error"],
            "audit_step2_client_error": audit["step2"]["client_error"],
            "audit_step3_client_error": audit["step3"]["client_error"],
            "audit_step4_client_error": audit.get("step4", {}).get("client_error", 0),
            "audit_step1_response_model": audit["step1"].get("response_model", ""),
            "audit_step2_response_model": audit["step2"].get("response_model", ""),
            "audit_step3_response_model": audit["step3"].get("response_model", ""),
            "audit_step4_response_model": audit.get("step4", {}).get("response_model", ""),
            "audit_step1_finish_reason": audit["step1"].get("finish_reason", ""),
            "audit_step2_finish_reason": audit["step2"].get("finish_reason", ""),
            "audit_step3_finish_reason": audit["step3"].get("finish_reason", ""),
            "audit_step4_finish_reason": audit.get("step4", {}).get("finish_reason", ""),
            "audit_step1_reasoning_nonempty": audit["step1"].get("reasoning_nonempty", 0),
            "audit_step2_reasoning_nonempty": audit["step2"].get("reasoning_nonempty", 0),
            "audit_step3_reasoning_nonempty": audit["step3"].get("reasoning_nonempty", 0),
            "audit_step4_reasoning_nonempty": audit.get("step4", {}).get("reasoning_nonempty", 0),
            "audit_step1_total_tokens": audit["step1"]["usage_total_tokens"],
            "audit_step2_total_tokens": audit["step2"]["usage_total_tokens"],
            "audit_step3_total_tokens": audit["step3"]["usage_total_tokens"],
            "audit_step4_total_tokens": audit.get("step4", {}).get("usage_total_tokens", 0),
            "audit_step1_latency_s": audit["step1"]["latency_s"],
            "audit_step2_latency_s": audit["step2"]["latency_s"],
            "audit_step3_latency_s": audit["step3"]["latency_s"],
            "audit_step4_latency_s": audit.get("step4", {}).get("latency_s", 0.0),
            "audit_full_internal_fallback": int(steps_ok == 0 and full_idx is not None),
            "audit_nocf_internal_fallback": int(run_nocf and not nocf_ok and nocf_addr is not None),
        })
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="2022-07-01")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-nocf", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=700)
    ap.add_argument("--out", required=True)
    ap.add_argument("--panel-file", default=os.path.join(PANEL_DIR, "panel_scored.csv.gz"),
                    help="Scored candidate file; defaults to frozen v1")
    ap.add_argument("--events-dir", default=None,
                    help="Optional separate events export directory; default uses metadata in panel file")
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--audit-details", action="store_true",
                    help="persist per-step status/error-class/usage/latency fields without response text")
    args = ap.parse_args()

    d = pd.read_csv(args.panel_file)
    ev_df = d[EVENT_KEY + ["counterparty_address", "cp_type", "stratum", "activity",
                           "evt_cnt_90d", "cp_entropy_90d", "cp_new_rate_30d",
                           "active_days_90d" if "active_days_90d" in d.columns else "evt_cnt_90d",
                           "pop_weight", "truth_g_rank"]].drop_duplicates(EVENT_KEY)
    if "active_days_90d" not in ev_df.columns:
        ev_df["active_days_90d"] = 0
    if args.events_dir:
        import glob
        ev_files = sorted(glob.glob(os.path.join(args.events_dir, "events", "*.csv.gz")))
        ev_df = pd.concat([pd.read_csv(f) for f in ev_files], ignore_index=True)
    d = d[d.snapshot_date == args.snapshot].copy()
    ev_df = ev_df[ev_df.snapshot_date == args.snapshot]

    # deterministic event selection: hash-ordered, stratified if limit small
    sel = ev_df.sort_values(["stratum", "activity", "target_sequence_index"])
    if args.limit < len(sel):
        # take evenly across strata
        per = max(1, args.limit // sel.groupby(["stratum", "activity"]).ngroups)
        sel = sel.groupby(["stratum", "activity"], group_keys=False).head(per)
        sel = sel.head(args.limit)
    keys = set(zip(sel.snapshot_date, sel.target_address, sel.target_sequence_index))
    done_keys = set()
    write_header = True
    if os.path.exists(args.out) and os.path.getsize(args.out) > 0:
        old = pd.read_csv(args.out, usecols=EVENT_KEY)
        done_keys = set(zip(old.snapshot_date, old.target_address, old.target_sequence_index))
        write_header = False
        print(f"resume: found {len(done_keys)} completed events", flush=True)
    d["_k"] = list(zip(d.snapshot_date, d.target_address, d.target_sequence_index))
    d = d[d._k.isin(keys)].drop(columns="_k")

    tasks = []
    ev_rows = {(r.snapshot_date, r.target_address, r.target_sequence_index): r
               for r in sel.itertuples()}
    for key, g in d.groupby(EVENT_KEY, sort=False):
        tkey = tuple(key)
        if tkey not in ev_rows or tkey in done_keys:
            continue
        evrow = ev_rows[tkey]
        tasks.append((evrow, g.reset_index(drop=True), args.model,
                      not args.no_nocf, args.max_tokens, args.audit_details))
    print(f"events={len(tasks)} model={args.model} workers={args.workers} nocf={not args.no_nocf} audit_details={args.audit_details}", flush=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    done = 0
    t_start = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for out in ex.map(run_one_event, tasks):
            pd.DataFrame([out]).to_csv(
                args.out, mode="a", header=write_header, index=False)
            write_header = False
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} elapsed={time.time()-t_start:.0f}s", flush=True)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
