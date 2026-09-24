#!/usr/bin/env python3
"""Collect structured Level-1 decision-state hypotheses from an approved LLM endpoint.

The script never reads the evaluation-only outcome table. It only consumes the
frozen as-of prompt table and writes raw structured responses plus an audit log.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / 'research/decision_state/results'
DEFAULT_BASE = os.environ.get('LLM_BASE_URL', 'http://127.0.0.1:31518/v1')
DEFAULT_MODEL = 'Qwen3.5-4B'
VARIANTS = ['full', 'minus_self', 'minus_market', 'placebo']
TARGETS = ['activity', 'active_days', 'counterparty_breadth', 'new_counterparties']


def clean_num(x, digits=5):
    if pd.isna(x):
        return 'NA'
    try:
        return f'{float(x):.{digits}g}'
    except Exception:
        return 'NA'


def build_evidence(row, variant):
    # The packet is compact and deliberately does not include target outcomes.
    self_text = (
        f"30d_events={clean_num(row.get('history_event_count_30d'))}; "
        f"7d_events={clean_num(row.get('event_count_7d'))}; "
        f"30d_active_days={clean_num(row.get('active_days_30d'))}; "
        f"7d_active_days={clean_num(row.get('active_days_7d'))}; "
        f"30d_unique_counterparties={clean_num(row.get('unique_counterparties_30d'))}; "
        f"7d_unique_counterparties={clean_num(row.get('score_unique_counterparties_7d'))}; "
        f"7d_new_counterparties={clean_num(row.get('new_counterparties_7d'))}; "
        f"7d_repeat_counterparties={clean_num(row.get('repeat_counterparties_7d'))}; "
        f"30d_incoming={clean_num(row.get('incoming_event_count_30d'))}; "
        f"30d_outgoing={clean_num(row.get('outgoing_event_count_30d'))}; "
        f"30d_self={clean_num(row.get('self_event_count_30d'))}; "
        f"30d_native_events={clean_num(row.get('native_event_count_30d'))}; "
        f"30d_token_events={clean_num(row.get('token_event_count_30d'))}; "
        f"30d_internal_events={clean_num(row.get('internal_event_count_30d'))}; "
        f"30d_counterparty_entropy={clean_num(row.get('counterparty_entropy_30d'))}; "
        f"30d_median_inter_event_gap_sec={clean_num(row.get('inter_event_gap_median_sec_30d'))}; "
        f"30d_native_netflow={clean_num(row.get('native_netflow_30d'))}"
    )
    market_text = (
        f"ETH_return_1d={clean_num(row.get('eth_return_1d'))}; "
        f"ETH_return_7d={clean_num(row.get('eth_return_7d'))}; "
        f"ETH_volatility_7d={clean_num(row.get('eth_volatility_7d'))}; "
        f"ETH_drawdown_30d={clean_num(row.get('eth_drawdown_30d'))}"
    )
    coverage_text = (
        f"history_window=30d; observed_before_cutoff=true; "
        f"history_activity_bin={row.get('activity_bin','NA')}; timezone=UTC"
    )
    placebo_text = 'The packet was rendered from a tabular source with UTC timestamps.'
    if variant == 'placebo':
        placebo_text = 'The packet was rendered from a JSON-compatible source with UTC timestamps.'

    blocks = []
    if variant == 'minus_self':
        blocks.append('[E_SELF]\nSelf-history evidence is unavailable in this packet.')
    else:
        blocks.append('[E_SELF]\n' + self_text)
    if variant == 'minus_market':
        blocks.append('[E_MARKET]\nMarket-context evidence is unavailable in this packet.')
    else:
        blocks.append('[E_MARKET]\n' + market_text)
    blocks.append('[E_COVERAGE]\n' + coverage_text)
    blocks.append('[E_PLACEBO]\n' + placebo_text)
    return '\n'.join(blocks)


def make_messages(row, variant):
    evidence = build_evidence(row, variant)
    system = (
        'You are a cautious behavioral forecasting analyst. Analyze an external '
        'Ethereum address as an address-level actor proxy, not a human mind. '
        'Do not infer true emotion, private intent, or causal belief. Generate '
        'three competing operational behavioral hypotheses that could be checked '
        'against the next 7 days of observed on-chain behavior. Use only the '
        'evidence in the packet; do not use future information.'
    )
    user = f'''Frozen cutoff packet. The cutoff is {row['cutoff_date']} UTC. Future outcomes are hidden.

{evidence}

Return ONLY valid JSON with this exact top-level schema:
{{
  "hypotheses": [
    {{
      "id": "H1",
      "text": "one concise operational behavioral hypothesis",
      "probability": 0.0,
      "horizon_days": 7,
      "evidence_ids": ["E_SELF"],
      "consequences": {{
        "activity": "up|same|down",
        "active_days": "up|same|down",
        "counterparty_breadth": "up|same|down",
        "new_counterparties": "up|same|down"
      }},
      "alternative_to": null
    }}
  ],
  "abstain_probability": 0.0
}}

Requirements: produce exactly 3 hypotheses if possible; probabilities must be nonnegative; consequence values must be exactly one of up, same, down; evidence_ids may only use E_SELF, E_MARKET, E_COVERAGE, E_PLACEBO; include at least one meaningful alternative explanation; use abstain_probability when evidence is weak. Do not mention the hidden future outcomes.'''
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def extract_json(text):
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip common markdown fences and search the outermost object.
    text2 = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I | re.S).strip()
    try:
        return json.loads(text2)
    except Exception:
        pass
    start, end = text2.find('{'), text2.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text2[start:end+1])
        except Exception:
            return None
    return None


def validate(obj):
    if not isinstance(obj, dict) or not isinstance(obj.get('hypotheses'), list):
        return False, 'missing_hypotheses'
    hs = obj['hypotheses']
    if len(hs) < 1:
        return False, 'empty_hypotheses'
    for h in hs[:3]:
        if not isinstance(h, dict):
            return False, 'hypothesis_not_object'
        if not isinstance(h.get('text'), str) or not h['text'].strip():
            return False, 'missing_text'
        try:
            if float(h.get('probability')) < 0:
                return False, 'negative_probability'
        except Exception:
            return False, 'bad_probability'
        cons = h.get('consequences')
        if not isinstance(cons, dict):
            return False, 'missing_consequences'
        if any(cons.get(t) not in {'up','same','down'} for t in TARGETS):
            return False, 'bad_consequence'
        ev = h.get('evidence_ids', [])
        if not isinstance(ev, list) or any(e not in {'E_SELF','E_MARKET','E_COVERAGE','E_PLACEBO'} for e in ev):
            return False, 'bad_evidence_id'
    return True, 'ok'


def call_one(row, variant, base_url, model, max_tokens, timeout, retries):
    messages = make_messages(row, variant)
    prompt_hash = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    body = {
        'model': model,
        'messages': messages,
        'temperature': 0.0,
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'},
    }
    token = os.environ.get('LLM_BEARER', '')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    out = {
        'case_id': row['case_id'], 'cutoff_date': row['cutoff_date'],
        'split': row['split'], 'variant': variant, 'model_requested': model,
        'prompt_sha256': prompt_hash, 'attempts': 0,
    }
    last_error = None
    for attempt in range(retries + 1):
        out['attempts'] = attempt + 1
        t0 = time.time()
        try:
            req = urllib.request.Request(
                base_url.rstrip('/') + '/chat/completions',
                data=json.dumps(body).encode(), headers=headers,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
                out['http_status'] = getattr(resp, 'status', 200)
            choice = payload['choices'][0]
            message = choice.get('message', {})
            content = message.get('content') or ''
            parsed = extract_json(content)
            valid, validation = validate(parsed)
            out.update({
                'model_returned': payload.get('model', model),
                'finish_reason': choice.get('finish_reason'),
                'usage': payload.get('usage', {}),
                'latency_s': round(time.time() - t0, 4),
                'raw_content': content,
                'parsed': parsed,
                'parse_valid': valid,
                'validation': validation,
                'reasoning_nonempty': bool(message.get('reasoning') or message.get('reasoning_content')),
            })
            return out
        except Exception as e:
            last_error = repr(e)
            out['latency_s'] = round(time.time() - t0, 4)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    out.update({'error': last_error, 'parse_valid': False, 'validation': 'request_error', 'raw_content': '', 'parsed': None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='cases per cutoff; 0 means all 1000')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--base-url', default=os.environ.get('LLM_BASE_URL', DEFAULT_BASE))
    ap.add_argument('--model', default=os.environ.get('LLM_MODEL', DEFAULT_MODEL))
    ap.add_argument('--max-tokens', type=int, default=700)
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--retries', type=int, default=2)
    ap.add_argument('--output', default='hypothesis_panel.jsonl')
    args = ap.parse_args()
    cases = pd.read_csv(RES / 'decision_state_prompt_cases.csv', low_memory=False)
    if args.limit:
        cases = cases.sort_values(['cutoff_date','sample_rank']).groupby('cutoff_date', group_keys=False).head(args.limit)
    tasks = [(row.to_dict(), variant) for _, row in cases.iterrows() for variant in VARIANTS]
    out_path = RES / args.output
    # Do not overwrite an existing panel accidentally.
    if out_path.exists():
        raise SystemExit(f'output exists: {out_path}; choose --output explicitly')
    print(f'cases={len(cases)} calls={len(tasks)} endpoint={args.base_url} model={args.model} workers={args.workers}', flush=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs=[ex.submit(call_one,row,var,args.base_url,args.model,args.max_tokens,args.timeout,args.retries) for row,var in tasks]
        for i,f in enumerate(concurrent.futures.as_completed(futs),1):
            results.append(f.result())
            if i % 25 == 0 or i == len(futs):
                valid=sum(bool(r.get('parse_valid')) for r in results)
                print(f'completed={i}/{len(futs)} valid={valid}/{i}', flush=True)
    results.sort(key=lambda r:(r['cutoff_date'],r['case_id'],VARIANTS.index(r['variant'])))
    with out_path.open('w') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
    summary={
        'protocol':'decision_state_v1','output':str(out_path),
        'n_cases':len(cases),'n_calls':len(results),
        'valid':sum(bool(r.get('parse_valid')) for r in results),
        'http_200':sum(r.get('http_status')==200 for r in results),
        'model_returned':sorted({r.get('model_returned') for r in results if r.get('model_returned')}),
        'variants':{v:sum(bool(r.get('parse_valid')) for r in results if r['variant']==v) for v in VARIANTS},
        'errors':sum('error' in r for r in results),
        'endpoint':args.base_url,
    }
    (out_path.with_suffix('.manifest.json')).write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
