#!/usr/bin/env python3
"""Build the frozen, leakage-separated Level-1 decision-state cases.

The prompt table intentionally excludes all future outcome fields. Evaluation
outcomes are written to a separate file and joined only by the evaluator.
"""
from __future__ import annotations
import os

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
DATA = ROOT / 'research/openworld/ow010b/data'
OUT = ROOT / 'research/decision_state/results'
OUT.mkdir(parents=True, exist_ok=True)

DISCOVERY = DATA / 'ow010b_discovery_features.csv'
FUTURE = DATA / 'ow010b_future_outcomes_evaluation_only.csv'
PRICE = ROOT / 'data/raw/prices/ethusd_1min_ohlc.csv'

CUTOFFS = {
    'train': '2022-06-01',
    'dev': '2022-07-01',
    'test': '2022-08-01',
}
N_PER_CUTOFF = 1000
BINS = ['1-2', '3-9', '10-19', '20+']

M0_FEATURES = [
    'history_event_count_30d', 'event_count_7d', 'active_days_30d',
    'active_days_7d', 'unique_counterparties_30d', 'unique_event_count_7d',
    'incoming_event_count_30d', 'outgoing_event_count_30d',
    'native_event_count_30d', 'token_event_count_30d',
    'internal_event_count_30d',
]
M1_PREFIXES = [
    'history_', 'event_count_', 'unique_event_count_', 'active_days_',
    'active_hours_', 'native_', 'token_', 'internal_', 'incoming_',
    'outgoing_', 'self_', 'inter_event_gap_', 'mean_events_per_active_hour_',
    'std_events_per_active_hour_', 'unique_counterparties_',
    'mapped_counterparties_', 'unmapped_counterparties_',
    'score_unique_counterparties_', 'prior_unique_counterparties_',
    'new_counterparties_', 'repeat_counterparties_',
    'reciprocal_counterparties_', 'counterparty_entropy_',
    'rapid_forwarding_', 'max_events_per_active_hour_',
    'max_fan_in_counterparties_per_hour_', 'max_fan_out_counterparties_per_hour_',
]
EXCLUDE_EXACT = {
    'anchor_wallet', 'anchor_exgraph_node_id', 'cutoff_time',
    'history_start', 'score_start', 'history_end', 'first_event_timestamp',
    'observed_before_cutoff', 'data_role', 'feature_version',
}


def stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def cmp3(future: pd.Series, prior: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=future.index, dtype='object')
    valid = future.notna() & prior.notna()
    out.loc[valid & (future > prior)] = 'up'
    out.loc[valid & (future < prior)] = 'down'
    out.loc[valid & (future == prior)] = 'same'
    return out


def market_context() -> pd.DataFrame:
    # Build daily context from the as-of-safe 1-minute ETH file. The last
    # minute of each UTC day is the daily close used by all cutoffs.
    use = ['timestamp', 'close']
    chunks = []
    for ch in pd.read_csv(PRICE, usecols=use, chunksize=500_000):
        ch['timestamp'] = pd.to_datetime(ch['timestamp'], unit='s', utc=True)
        ch['close'] = pd.to_numeric(ch['close'], errors='coerce')
        ch = ch.dropna(subset=['timestamp', 'close'])
        ch['date'] = ch['timestamp'].dt.floor('D')
        chunks.append(ch[['date', 'timestamp', 'close']])
    px = pd.concat(chunks, ignore_index=True)
    daily = (px.sort_values('timestamp').groupby('date', as_index=False)
             .tail(1).set_index('date')['close'].sort_index())
    logret = np.log(daily).diff()
    rows = []
    for date_s in CUTOFFS.values():
        d = pd.Timestamp(date_s, tz='UTC')
        prior = daily.loc[daily.index < d]
        if prior.empty:
            rows.append({'cutoff_date': date_s})
            continue
        c0 = float(prior.iloc[-1])
        c1 = float(prior.iloc[-2]) if len(prior) >= 2 else np.nan
        c7 = float(prior.iloc[-8]) if len(prior) >= 8 else np.nan
        last30 = prior.iloc[-30:]
        r7 = logret.loc[logret.index < d].iloc[-7:]
        rows.append({
            'cutoff_date': date_s,
            'eth_close_asof': c0,
            'eth_return_1d': c0 / c1 - 1 if np.isfinite(c1) and c1 else np.nan,
            'eth_return_7d': c0 / c7 - 1 if np.isfinite(c7) and c7 else np.nan,
            'eth_volatility_7d': float(r7.std(ddof=1)) if len(r7) >= 3 else np.nan,
            'eth_drawdown_30d': c0 / float(last30.max()) - 1 if len(last30) else np.nan,
        })
    return pd.DataFrame(rows)


def main() -> None:
    discovery = pd.read_csv(DISCOVERY, low_memory=False)
    future = pd.read_csv(FUTURE, low_memory=False)
    discovery['cutoff_date'] = pd.to_datetime(discovery['cutoff_time'], unit='s', utc=True).dt.strftime('%Y-%m-%d')
    future['cutoff_date'] = pd.to_datetime(future['cutoff_time'], unit='s', utc=True).dt.strftime('%Y-%m-%d')

    eligible = discovery[
        discovery['cutoff_date'].isin(CUTOFFS.values())
        & discovery['observed_before_cutoff'].astype(bool)
        & (pd.to_numeric(discovery['history_event_count_30d'], errors='coerce') > 0)
        & (discovery['history_window_coverage_status'] == 'OBSERVED_FULL_WINDOW')
    ].copy()
    bins = pd.cut(
        pd.to_numeric(eligible['history_event_count_30d'], errors='coerce'),
        bins=[0, 2, 9, 19, np.inf], labels=BINS,
        include_lowest=True,
    )
    eligible['activity_bin'] = bins.astype(str)
    selected = []
    for cutoff in CUTOFFS.values():
        sub = eligible[eligible['cutoff_date'] == cutoff].copy()
        # Equal quota per pre-registered activity bin. The source audit showed
        # all four bins have >= 1,000 examples per cutoff.
        per_bin = N_PER_CUTOFF // len(BINS)
        for b in BINS:
            sb = sub[sub['activity_bin'] == b].copy()
            sb['_stable'] = sb.apply(lambda r: stable_int(f"{r.anchor_wallet}|{cutoff}"), axis=1)
            sb = sb.sort_values('_stable').head(per_bin)
            selected.append(sb)
        # deterministic top-up if integer division ever leaves a remainder
        chosen = pd.concat(selected[-len(BINS):], ignore_index=True)
        remaining = sub[~sub['anchor_wallet'].isin(chosen['anchor_wallet'])].copy()
        if len(chosen) < N_PER_CUTOFF:
            remaining['_stable'] = remaining.apply(lambda r: stable_int(f"topup|{r.anchor_wallet}|{cutoff}"), axis=1)
            chosen = pd.concat([chosen, remaining.sort_values('_stable').head(N_PER_CUTOFF-len(chosen))], ignore_index=True)
        chosen['split'] = next(k for k, v in CUTOFFS.items() if v == cutoff)
        selected[-len(BINS):] = [chosen]
    cases = pd.concat(selected, ignore_index=True)
    cases = cases.drop(columns=['_stable'], errors='ignore')
    cases['case_id'] = [f"{d}|{a}" for d, a in zip(cases['cutoff_date'], cases['anchor_wallet'])]
    cases['sample_rank'] = cases.groupby('cutoff_date')['case_id'].rank(method='first').astype(int)

    # Restrict and coerce M1 numeric features. Status and identifier columns are
    # never passed to the model or prompt builder.
    feature_cols = []
    for c in cases.columns:
        if c in EXCLUDE_EXACT or c.endswith('_status'):
            continue
        if c in M0_FEATURES or any(c.startswith(p) for p in M1_PREFIXES):
            if c not in feature_cols:
                feature_cols.append(c)
    for c in feature_cols:
        cases[c] = pd.to_numeric(cases[c], errors='coerce')
    cases['m1_missing_count'] = cases[feature_cols].isna().sum(axis=1)
    cases['m1_finite_feature_count'] = cases[feature_cols].notna().sum(axis=1)

    # As-of market context is computed separately from price data and joined by
    # cutoff. It contains no future prices relative to that cutoff.
    cases = cases.merge(market_context(), on='cutoff_date', how='left', validate='many_to_one')

    # Join evaluation-only outcomes only in this local evaluator table.
    eval_cols = [
        'anchor_wallet', 'cutoff_date', 'future7_event_count',
        'future7_active_days', 'future7_unique_counterparties',
        'future7_new_counterparties', 'future7_window_coverage_status',
        'evaluation_only',
    ]
    ev = future[eval_cols].copy()
    merged = cases[['case_id', 'anchor_wallet', 'cutoff_date', 'split',
                    'activity_bin', 'sample_rank']].merge(
        ev, on=['anchor_wallet', 'cutoff_date'], how='left', validate='one_to_one')
    for c in ['future7_event_count', 'future7_active_days', 'future7_unique_counterparties', 'future7_new_counterparties']:
        merged[c] = pd.to_numeric(merged[c], errors='coerce')
    # Prior 7-day references come from the discovery table and are as-of safe.
    refs = cases[['case_id', 'event_count_7d', 'active_days_7d',
                  'score_unique_counterparties_7d', 'new_counterparties_7d']].copy()
    merged = merged.merge(refs, on='case_id', validate='one_to_one')
    merged['y_activity'] = cmp3(merged.future7_event_count, merged.event_count_7d)
    merged['y_active_days'] = cmp3(merged.future7_active_days, merged.active_days_7d)
    merged['y_counterparty_breadth'] = cmp3(merged.future7_unique_counterparties, merged.score_unique_counterparties_7d)
    merged['y_new_counterparties'] = cmp3(merged.future7_new_counterparties, merged.new_counterparties_7d)
    merged['eval_complete'] = (
        merged['evaluation_only'].eq(True)
        & merged['future7_window_coverage_status'].eq('OBSERVED_FULL_WINDOW')
        & merged[['y_activity', 'y_active_days', 'y_counterparty_breadth', 'y_new_counterparties']].notna().all(axis=1)
    )

    # Prompt file is explicitly stripped of all future outcomes and target labels.
    id_cols = ['case_id', 'anchor_wallet', 'cutoff_date', 'split', 'activity_bin', 'sample_rank']
    prompt_cols = id_cols + M0_FEATURES + [c for c in feature_cols if c not in M0_FEATURES] + [
        'm1_missing_count', 'm1_finite_feature_count', 'eth_close_asof',
        'eth_return_1d', 'eth_return_7d', 'eth_volatility_7d', 'eth_drawdown_30d',
    ]
    prompt_cols = list(dict.fromkeys(c for c in prompt_cols if c in cases.columns))
    prompts = cases[prompt_cols].copy()
    prompts.to_csv(OUT / 'decision_state_prompt_cases.csv', index=False)
    merged.to_csv(OUT / 'decision_state_eval_cases.csv', index=False)
    cases.to_parquet(OUT / 'decision_state_asof_features.parquet', index=False)

    manifest = {
        'protocol': 'decision_state_v1',
        'build_date': '2026-09-19',
        'source_discovery': str(DISCOVERY),
        'source_future_eval': str(FUTURE),
        'source_price': str(PRICE),
        'source_sha256': {
            'discovery': sha256_file(DISCOVERY),
            'future': sha256_file(FUTURE),
            'price': sha256_file(PRICE),
        },
        'n_cases': int(len(cases)),
        'n_prompt_cases': int(len(prompts)),
        'n_eval_complete': int(merged['eval_complete'].sum()),
        'counts_by_cutoff': cases['cutoff_date'].value_counts().sort_index().to_dict(),
        'counts_by_bin': {f'{k[0]}|{k[1]}': int(v) for k, v in cases.groupby(['cutoff_date', 'activity_bin'], observed=False).size().items()},
        'prompt_columns': prompt_cols,
        'm0_features': M0_FEATURES,
        'm1_features': feature_cols,
        'future_columns_only_in_eval': [c for c in merged.columns if c.startswith('future7_') or c.startswith('y_') or c in ['evaluation_only', 'eval_complete']],
        'market_context_asof': ['eth_close_asof','eth_return_1d','eth_return_7d','eth_volatility_7d','eth_drawdown_30d'],
    }
    (OUT / 'decision_state_case_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: manifest[k] for k in ['n_cases','n_eval_complete','counts_by_cutoff','counts_by_bin']}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
