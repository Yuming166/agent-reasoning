"""Call local Qwen3.5-4B chat to produce structured behavioral summaries.

Protocol (frozen): temperature=0, max_tokens=700, reasoning_effort NOT sent
(AGENTS.md / README constraint). Every response is appended to a disk JSONL
cache so the run is resumable; already-cached addresses are skipped.

Output fields per wallet: raw text, parsed JSON, parse_ok, token usage,
latency, timestamp. Parse yield and call counts are aggregated into
results/call_stats_20220901.json.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

SYSTEM_PROMPT = (
    "You are a careful blockchain behavioral analyst. Given an Ethereum wallet's "
    "as-of behavioral profile (90-day lookback ending 2022-09-01 plus monthly "
    "snapshots), produce a concise structured behavioral summary. Use ONLY the "
    "information present in the profile. Do NOT invent specific transactions, "
    "counterparty identities, token names, or future outcomes that are not given. "
    "Mark anything uncertain explicitly. This is an internal representation task, "
    "not a recommendation."
)

USER_TEMPLATE = """{profile}

Task: produce a structured behavioral summary of this wallet.

Return STRICT JSON with EXACTLY these keys:
- "behavior_pattern": string, one sentence describing the dominant behavioral pattern.
- "interaction_object_types": array of strings, the kinds of counterparties / token behavior evidenced by the profile (e.g. "native value transfers", "broad multi-token transfers", "concentrated single-token use", "hub-like high-degree behavior", "many one-off counterparties").
- "state_transitions": string, how behavior changed across the monthly snapshots (or "no clear transition" if stable).
- "anomalies": array of strings, anything unusual (burstiness, extreme concentration, sudden activity change, missing USD pricing, etc.); use [] if none.
- "uncertainty": string, which conclusions are uncertain or lack evidence.
- "regime_change": boolean, whether there is evidence of a regime change in the lookback.
- "activity_regime": string, one of "very_low","low","medium","high","very_high".
- "confidence": string, one of "low","medium","high".

Do not output anything besides the JSON object."""


def call_chat(prompt_text: str) -> dict:
    payload = {
        "model": config.CHAT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(profile=prompt_text)},
        ],
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS,
    }
    # AGENTS.md / README: omit reasoning_effort for this Qwen/vLLM deployment
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        config.CHAT_BASE + "/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(config.MAX_RETRIES):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=config.TIMEOUT_S) as r:
                out = json.loads(r.read().decode())
            usage = out.get("usage", {})
            return {
                "raw": out["choices"][0]["message"]["content"],
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "latency_s": round(time.time() - t0, 2),
            }
        except Exception as e:  # noqa: BLE001
            last = repr(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"chat failed after {config.MAX_RETRIES} attempts: {last}")


def extract_json(text: str):
    """Best-effort JSON extraction from possibly fenced/noisy output."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.removeprefix("json").strip()
    try:
        return json.loads(t)
    except Exception:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except Exception:
                return None
    return None


def main() -> None:
    # load profiles in sample order
    profiles = []
    for line in open(config.PROFILES_JSONL, encoding="utf-8"):
        profiles.append(json.loads(line))

    # existing cache for resume
    done = {}
    if config.SUMMARIES_JSONL.exists():
        for line in open(config.SUMMARIES_JSONL, encoding="utf-8"):
            r = json.loads(line)
            done[r["target_address"]] = r
    todo = [p for p in profiles if p["target_address"] not in done]

    print(f"[summarize] total={len(profiles)} cached={len(done)} todo={len(todo)}")
    calls = 0
    fail = 0
    fh = open(config.SUMMARIES_JSONL, "a", encoding="utf-8")
    try:
        for i, p in enumerate(todo, 1):
            try:
                out = call_chat(p["profile_text"])
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"[{i}/{len(todo)}] FAIL {p['target_address']}: {e}", flush=True)
                continue
            parsed = extract_json(out["raw"])
            rec = {
                "target_address": p["target_address"],
                "target_exgraph_node_id": p["target_exgraph_node_id"],
                "activity_tier": p["activity_tier"],
                "traj_cluster": p["traj_cluster"],
                "net_cov": p["net_cov"],
                "raw": out["raw"],
                "parsed": parsed,
                "parse_ok": parsed is not None,
                "prompt_tokens": out["prompt_tokens"],
                "completion_tokens": out["completion_tokens"],
                "latency_s": out["latency_s"],
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            calls += 1
            if not rec["parse_ok"]:
                fail += 1
            if i % 10 == 0 or not rec["parse_ok"]:
                print(f"[{i}/{len(todo)}] calls={calls} parse_fail_total={fail} last={p['target_address'][:12]}", flush=True)
    finally:
        fh.close()

    # aggregate stats
    rows = []
    for line in open(config.SUMMARIES_JSONL, encoding="utf-8"):
        rows.append(json.loads(line))
    n_ok = sum(1 for r in rows if r["parse_ok"])
    stats_path = config.RESULTS / "call_stats_20220901.json"
    if calls > 0 or not stats_path.exists():
        stats = {
            "phase": "chat",
            "model": config.CHAT_MODEL,
            "endpoint": config.CHAT_BASE,
            "protocol": {"temperature": config.TEMPERATURE, "max_tokens": config.MAX_TOKENS,
                         "reasoning_effort": "omitted"},
            "n_profiles": len(profiles),
            "n_cached_at_first_run": len(done) - calls,
            "n_new_calls": calls,
            "n_total_rows": len(rows),
            "n_parse_ok": n_ok,
            "parse_yield": round(n_ok / len(rows), 4) if rows else None,
            "n_failed_calls": fail,
            "total_prompt_tokens": sum(r["prompt_tokens"] or 0 for r in rows),
            "total_completion_tokens": sum(r["completion_tokens"] or 0 for r in rows),
            "cache_path": str(config.SUMMARIES_JSONL),
        }
        stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print("[resume] no new chat calls; existing call_stats preserved")
    print(f"[ok] summaries cache -> {config.SUMMARIES_JSONL}")


if __name__ == "__main__":
    main()
