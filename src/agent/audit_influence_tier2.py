#!/usr/bin/env python3
"""Post-hoc Tier2 signal audit on the FROZEN August node-selection outcomes.

This is explicitly exploratory / post-hoc: it re-uses the already-frozen
selector inputs and outcomes, joins wallet-level influence measures, and asks
whether influence provides signal for budget allocation. It does NOT retrain
or replace the preregistered frozen selector; deltas are descriptive.
"""
import json, os, sys
import pandas as pd
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BUDGETS = [0.05, 0.10, 0.20, 0.50, 0.75]
AUG = '2022-08-01'

def load():
    base = f'{ROOT}/artifacts/llm_panel_v2/node_selection_v2_final_audited_20260910'
    out = pd.read_csv(f'{base}/frozen_test_outcomes_for_audit.csv', dtype={'target_address': str})
    sel = pd.read_csv(f'{base}/frozen_test_selector_input.csv', dtype={'target_address': str})
    run = pd.read_csv(f'{ROOT}/artifacts/llm_panel_v2/runs/aug_gonogo_local_vllm4b_rerun_20260910.csv', dtype={'target_address': str})
    inf = pd.read_csv(f'{ROOT}/artifacts/influence_v1/wallet_influence_v1.csv', dtype={'target_address': str})
    for d in (out, sel, run):
        d['snapshot_date'] = d['snapshot_date'].astype(str)
        d['target_sequence_index'] = pd.to_numeric(d['target_sequence_index'], errors='coerce')
    inf['snapshot_date'] = inf['snapshot_date'].astype(str)
    run = run[run['snapshot_date'] == AUG]
    run = run[['snapshot_date','target_address','target_sequence_index','pop_weight','cheap_rr','full_rr','full_parse_ok']]
    out = out[out['snapshot_date'] == AUG]
    sel = sel[sel['snapshot_date'] == AUG]
    inf = inf[inf['snapshot_date'] == AUG]
    # outcomes has gain_full already (operational + fallback)
    df = out[['snapshot_date','target_address','target_sequence_index','cheap_rr','gain_full','total_tokens','truth_in_pool']].copy()
    df = df.merge(run[['snapshot_date','target_address','target_sequence_index','pop_weight']],
                  on=['snapshot_date','target_address','target_sequence_index'], how='left')
    df = df.merge(sel[['snapshot_date','target_address','target_sequence_index','learned_score']],
                  on=['snapshot_date','target_address','target_sequence_index'], how='left')
    df = df.merge(inf[['target_address','icf_score_p1','trigger_score_p2','market_share_usd','total_usd','native_usd','token_usd_priced']],
                  on='target_address', how='left')
    df['pop_weight'] = pd.to_numeric(df['pop_weight'], errors='coerce').fillna(1.0)
    df['cheap_rr'] = pd.to_numeric(df['cheap_rr'], errors='coerce').fillna(0.0)
    df['gain_full'] = pd.to_numeric(df['gain_full'], errors='coerce').fillna(0.0)
    for c in ['learned_score','icf_score_p1','trigger_score_p2','market_share_usd','total_usd']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df

def weighted_mrr_curve(df, score):
    d = df.copy()
    d['_score'] = score
    d = d.sort_values(['_score','target_address','target_sequence_index'], ascending=[False, True, True], kind='mergesort')
    n = len(d)
    w = d['pop_weight'].to_numpy(float)
    cheap = d['cheap_rr'].to_numpy(float)
    gain = d['gain_full'].to_numpy(float)
    res = {}
    for b in BUDGETS:
        k = max(1, int(round(n * b)))
        sel = np.zeros(n, bool)
        sel[:k] = True
        out = cheap + sel.astype(float) * gain
        res[str(b)] = float(np.sum(w * out) / np.sum(w))
    return res

def rank_pct(s):
    return s.rank(method='average', pct=True)

def main():
    df = load()
    print('events', len(df), 'unique wallets', df['target_address'].nunique())
    scores = {
        'learned': df['learned_score'],
        'icf': df['icf_score_p1'],
        'trigger': df['trigger_score_p2'],
        'market_share': df['market_share_usd'],
        'total_usd': df['total_usd'],
        'fusion_learned_icf_5050': (rank_pct(df['learned_score']) + rank_pct(df['icf_score_p1']))/2,
        'fusion_learned_trigger_5050': (rank_pct(df['learned_score']) + rank_pct(df['trigger_score_p2']))/2,
        'fusion_learned_share_5050': (rank_pct(df['learned_score']) + rank_pct(df['market_share_usd']))/2,
    }
    curves = {name: weighted_mrr_curve(df, s) for name, s in scores.items()}
    # correlations vs realized gain (post-hoc descriptive)
    corr_cols = ['learned_score','icf_score_p1','trigger_score_p2','market_share_usd','total_usd']
    corr = {}
    for c in corr_cols:
        corr[c] = {
            'spearman_vs_gain_full': float(df[[c,'gain_full']].corr(method='spearman').iloc[0,1]),
            'spearman_vs_learned': float(df[[c,'learned_score']].corr(method='spearman').iloc[0,1]),
        }
    result = {
        'note': 'POST-HOC exploratory audit on frozen Aug selector inputs/outcomes; not a preregistered claim',
        'n_events': int(len(df)),
        'n_wallets': int(df['target_address'].nunique()),
        'budgets': [str(b) for b in BUDGETS],
        'weighted_mrr_by_policy': curves,
        'delta_vs_learned': {k: {b: round(v[b]-curves['learned'][b],6) for b in curves['learned']} for k,v in curves.items()},
        'correlations': corr,
    }
    os.makedirs(f'{ROOT}/artifacts/influence_v1', exist_ok=True)
    out_json = f'{ROOT}/artifacts/influence_v1/tier2_signal_audit_20260801.json'
    json.dump(result, open(out_json,'w'), indent=2)
    # curves as csv
    rows=[]
    for k,v in curves.items():
        for b,m in v.items():
            rows.append({'policy':k,'budget':b,'weighted_mrr':m})
    pd.DataFrame(rows).to_csv(f'{ROOT}/artifacts/influence_v1/tier2_signal_audit_20260801.csv', index=False)
    print('saved', out_json)
    print(json.dumps({'weighted_mrr_by_policy': curves, 'correlations': corr}, indent=2))

if __name__ == '__main__':
    main()
