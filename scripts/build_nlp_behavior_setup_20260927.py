#!/usr/bin/env python3
"""Build leakage-audited natural-language behavior-state inputs from frozen event cases.

This is a setup artifact only: it does not call an LLM and does not change frozen
baseline results. Every narrative is generated solely from the pre-cutoff fields
in cases.jsonl.
"""
import hashlib, json, re
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
OUT = ROOT / 'artifacts/nlp_behavior_setup_20260927'
CONFIG = ROOT / 'configs/nlp_behavior_v1.json'
OUT.mkdir(parents=True, exist_ok=True)

FORBIDDEN = {
    'label_any_new_cp_7d', 'future_event_count', 'future_new_cp_count',
    'numeric_pred', 'numeric_prob', 'split', 'llm_sample'
}
STATE_GUIDANCE = {
    'dormant': 'no or very sparse recent activity',
    'reactivation': 'recent activity resumed after a long inactive gap',
    'stable_repeat': 'repeated interaction with a small, persistent counterparty set',
    'exploration': 'recent introduction of new counterparties or event families',
    'expansion': 'breadth and activity both appear to be increasing',
    'consolidation': 'recent activity concentrates on recurring counterparties',
    'routing': 'activity appears to move across directions or event families'
}

def iso(ts):
    return pd.Timestamp(ts).tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')

def event_line(e):
    return (f"{e['evidence_id']} | {iso(e['time'])} | {e['direction']} | "
            f"{e['family']} | counterparty={e['counterparty']} | sequence={e['sequence_index']}")

def narrative(c):
    f = c['features']
    ev = c['evidence']
    intervals = []
    for a, b in zip(ev, ev[1:]):
        dt = (pd.Timestamp(b['time']) - pd.Timestamp(a['time'])).total_seconds() / 86400
        intervals.append(round(max(0.0, dt), 4))
    interval_text = ', '.join(f'{x:g}d' for x in intervals[-8:]) if intervals else 'none'
    return '\n'.join([
        f"Wallet behavior record; cutoff={c['cutoff']}T00:00:00Z.",
        "All events below occurred strictly before the cutoff. Counterparties are anonymized stable aliases.",
        "Recent pre-cutoff event sequence:",
        *(event_line(x) for x in ev),
        f"Recent inter-event gaps (days, chronological): {interval_text}.",
        "Pre-cutoff multiscale context:",
        f"7d_events={f['evt_7d']}; 30d_events={f['evt_30d']}; 90d_events={f['evt_90d']}; ",
        f"active_days_30d={f['active_days_30d']}; distinct_counterparties_30d={f['distinct_cp_30d']}; ",
        f"new_counterparty_rate_30d={f['new_cp_rate_30d']:.4f}; counterparty_entropy_30d={f['cp_entropy_30d']:.4f}; ",
        f"top_counterparty_share_30d={f['top_cp_share_30d']:.4f}; reciprocal_pairs_30d={f['reciprocal_pairs_30d']}; ",
        f"outgoing_share_30d={f['out_share_30d']:.4f}; token_share_30d={f['token_share_30d']:.4f}; ",
        f"trace_share_30d={f['trace_share_30d']:.4f}; days_since_last_event={f['days_since_last_event']:.4f}.",
    ])

def prompt(c, mode):
    body = narrative(c)
    states = ', '.join(STATE_GUIDANCE)
    if mode == 'state':
        instruction = f"""Infer one current behavior state from: {states}.
Also give a possible state transition only if directly supported by the supplied sequence.
Forecast NEW, NONE, or ABSTAIN for at least one previously unseen counterparty in the next 7 days.
Return JSON only with keys state, transition, forecast, confidence, evidence_ids, uncertainty, abstain.
Cite only supplied evidence ids. Do not use future information, address identity, motive, or intent."""
    else:
        instruction = """Produce a compact falsifiable hypothesis about the next 7 days, then map it to NEW, NONE, or ABSTAIN. Cite 1-3 supplied evidence ids. The hypothesis must refer to a temporal or relational pattern, not merely restate a count. Return JSON only with keys hypothesis, forecast, confidence, evidence_ids, uncertainty, abstain. Do not use future information, address identity, motive, or intent."""
    return body + "\n\n" + instruction

cases = [json.loads(x) for x in SRC.read_text().splitlines() if x.strip()]
rows = []
for c in cases:
    base = {k: c[k] for k in ('case_id', 'wallet', 'cutoff')}
    base['split'] = {'2022-06-01': 'train', '2022-07-01': 'dev', '2022-08-01': 'test'}[c['cutoff']]
    base['n_pre_cutoff_events'] = c['history_event_count']
    base['n_evidence_events'] = len(c['evidence'])
    base['narrative'] = narrative(c)
    base['state_prompt'] = prompt(c, 'state')
    base['hypothesis_prompt'] = prompt(c, 'hypothesis')
    rows.append(base)

out_jsonl = OUT / 'nlp_inputs.jsonl'
with out_jsonl.open('w') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# Static leakage audit over generated inputs.
prompt_text = '\n'.join(r['state_prompt'] + '\n' + r['hypothesis_prompt'] for r in rows)
violations = []
for token in FORBIDDEN:
    if re.search(rf'\b{re.escape(token)}\b', prompt_text):
        violations.append(token)
# Future target data are not included in the generated records. Verify each row's cutoff.
for r, c in zip(rows, cases):
    cutoff = pd.Timestamp(c['cutoff'], tz='UTC')
    for e in c['evidence']:
        if not (pd.Timestamp(e['time']) < cutoff):
            violations.append(f"evidence_after_cutoff:{c['case_id']}:{e['evidence_id']}")

manifest = {
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source': str(SRC),
    'source_sha256': hashlib.sha256(SRC.read_bytes()).hexdigest(),
    'config': str(CONFIG),
    'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
    'cases': len(rows),
    'split_counts': pd.Series([r['split'] for r in rows]).value_counts().to_dict(),
    'input_fields': ['pre-cutoff event sequence', 'event family', 'direction', 'stable counterparty aliases', 'inter-event gaps', '7d/30d/90d summaries'],
    'forbidden_fields_checked': sorted(FORBIDDEN),
    'leakage_violations': violations,
    'status': 'PASS' if not violations else 'FAIL'
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
(OUT / 'README.md').write_text('''# NLP behavior setup v1\n\nThis directory contains leakage-audited prompts and pre-cutoff event narratives for the EX-Graph behavior forecasting task. It does not contain LLM predictions.\n\n- `nlp_inputs.jsonl`: one record per wallet-cutoff case.\n- `manifest.json`: source hashes, split counts, and leakage audit.\n- The prompt asks for behavior state, state transition, evidence ids, forecast, confidence, and abstention.\n\nFrozen future labels remain outside all generated prompts.\n''')
print(json.dumps(manifest, indent=2, ensure_ascii=False))
