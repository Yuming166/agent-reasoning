#!/usr/bin/env python3
"""Package cached Ethereum/X graphs using only manually confirmed seed links.

AI-reviewed candidates are emitted separately as non-confirming review leads.
No network access or paid queries. Graphs contain observed cached events only.
"""
from __future__ import annotations


import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/ens_x_crosswalk'
OUT = SRC / 'overnight_ai_dataset_20260926'
SEED = SRC / 'two_graph_seed_20260925'
PILOT = SRC / 'timeline_expansion_pilot_20260925'
WINDOW_START = '2026-01-01T00:00:00Z'
WINDOW_END = '2026-09-24T17:24:10Z'


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def jsonl_rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
        f.flush()
    temp.replace(path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        f.flush()
    temp.replace(path)


def confirmed_seed_crosswalk(seed_rows: list[dict]) -> list[dict]:
    """Return only the pre-existing human-confirmed mapping rows."""
    return [{'address': r['address'], 'x_user_id': r['x_user_id'],
             'handle': r['handle_at_verification'],
             'evidence_tier': 'prior_account_side_verified',
             'review_method': 'prior_human_review',
             'historical_asof_status': 'not_reconstructed'} for r in seed_rows]


def ai_review_leads(candidate_rows: list[dict]) -> list[dict]:
    """Preserve AI labels as non-confirming leads, never graph mappings."""
    return [{'address': r['address'], 'x_user_id': r['x_user_id'],
             'ai_verdict_lead': r.get('ai_verdict', ''),
             'human_review_status': 'pending',
             'eligible_as_confirmed_crosswalk': 'false'} for r in candidate_rows]


def main() -> None:
    summary = json.loads((OUT / 'review_summary.json').read_text(encoding='utf-8'))
    if summary.get('reviewed_candidate_pairs') != 231:
        raise ValueError('AI review is incomplete')
    seed = csv_rows(SEED / 'crosswalk_confirmed_unique.csv')
    if len(seed) != 12:
        raise ValueError(f'expected 12 prior human-confirmed seeds, got {len(seed)}')
    linked = confirmed_seed_crosswalk(seed)
    ids = {r['x_user_id'] for r in linked}
    wallets = {r['address'].lower() for r in linked}
    linked_by_id = {r['x_user_id']: r for r in linked}
    write_csv(OUT / 'crosswalk_analysis_snapshot.csv', linked, list(linked[0]))
    ai_candidates = csv_rows(OUT / 'candidate_review_ai_231.csv')
    leads = ai_review_leads(ai_candidates)
    write_csv(OUT / 'review_leads_ai_only.csv', leads, list(leads[0]))

    chain_edges = csv_rows(SEED / 'eth_transfer_edges_2026_seed_neighborhood.csv')
    chain_nodes = csv_rows(SEED / 'eth_address_nodes_2026_seed_neighborhood.csv')
    for row in chain_edges:
        row['source_dataset'] = 'prior_verified_12_seed'
    write_csv(OUT / 'ethereum_event_edges_observed.csv', chain_edges, list(chain_edges[0]))
    write_csv(OUT / 'ethereum_address_nodes_observed.csv', chain_nodes, list(chain_nodes[0]))
    represented = {r['address'].lower() for r in chain_nodes if r.get('role') == 'account_confirmed_seed'}

    month = pd.read_parquet(SRC / 'final_validated_address_month_events_2026.parquet')
    month['address'] = month['address'].str.lower()
    month = month[month['address'].isin(wallets)]
    month.to_csv(OUT / 'linked_wallet_month_activity_2026.csv', index=False)

    seed_edges = csv_rows(SEED / 'x_interaction_edges_temporal.csv')
    pilot_edges = csv_rows(PILOT / 'provisional_x_interaction_edges_temporal.csv')
    edge_fields = ['source_x_user_id', 'target_x_user_id', 'event_type', 'created_at_utc',
                   'source_post_id', 'target_post_id', 'time_semantics', 'edge_source_tier']
    edges = []
    for source, rows in [('prior_verified_12_seed', seed_edges), ('AI_reviewed_pilot_subset', pilot_edges)]:
        for row in rows:
            if row['source_x_user_id'] not in ids:
                continue
            if not (WINDOW_START <= row['created_at_utc'] < WINDOW_END):
                continue
            edges.append({**{f: row.get(f, '') for f in edge_fields}, 'edge_source_tier': source})
    unique_edges = {}
    for row in edges:
        key = (row['source_x_user_id'], row['target_x_user_id'], row['event_type'], row['source_post_id'])
        unique_edges[key] = row
    edges = list(unique_edges.values())
    write_csv(OUT / 'x_interaction_edges_observed.csv', edges, edge_fields)
    node_ids = ids | {e['source_x_user_id'] for e in edges} | {e['target_x_user_id'] for e in edges}
    nodes = []
    for uid in sorted(node_ids):
        mapped = linked_by_id.get(uid)
        nodes.append({'x_user_id': uid, 'linked_wallet_address': mapped['address'] if mapped else '',
                      'evidence_tier': mapped['evidence_tier'] if mapped else 'external_unmapped',
                      'role': 'mapped_actor' if mapped else 'observed_external_target'})
    write_csv(OUT / 'x_user_nodes_observed.csv', nodes, list(nodes[0]))

    posts = []
    for source, path in [('prior_verified_12_seed', SEED / 'x_authored_posts.jsonl'),
                         ('AI_reviewed_pilot_subset', PILOT / 'provisional_x_authored_posts.jsonl')]:
        for row in jsonl_rows(path):
            if str(row.get('x_user_id', '')) in ids and WINDOW_START <= str(row.get('created_at_utc', '')) < WINDOW_END:
                posts.append({**row, 'source_tier': source})
    posts_by_id = {str(r['tweet_id']): r for r in posts}
    posts = list(posts_by_id.values())
    write_jsonl(OUT / 'x_authored_posts_observed.jsonl', posts)

    seed_coverage = {r['x_user_id']: r for r in csv_rows(SRC / 'fx_authorized_batch_20260924T172410Z/continuation_20260924_fixed_window/combined_coverage.csv')}
    pilot_coverage = {str(r['x_user_id']): r for r in jsonl_rows(PILOT / 'coverage.jsonl')}
    coverage = []
    for row in linked:
        uid = row['x_user_id']
        seed_cov, pilot_cov = seed_coverage.get(uid), pilot_coverage.get(uid)
        status = ('seed_observed_uncertain_or_partial' if seed_cov else
                  'pilot_observed_uncertain_or_partial' if pilot_cov else 'no_cached_timeline')
        coverage.append({'address': row['address'], 'x_user_id': uid,
                         'evidence_tier': row['evidence_tier'], 'timeline_observation_status': status,
                         'timeline_stop_reason': (seed_cov or pilot_cov or {}).get('stop_reason', ''),
                         'has_cached_chain_event_neighborhood': row['address'].lower() in represented,
                         'historical_asof_validated': False})
    write_csv(OUT / 'coverage_by_linked_wallet.csv', coverage, list(coverage[0]))

    observed_sources = {e['source_x_user_id'] for e in edges}
    manifest = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'fixed_window_start_inclusive_utc': WINDOW_START,
        'fixed_window_end_exclusive_utc': WINDOW_END,
        'analysis_snapshot_mapped_wallet_x_pairs': len(linked),
        'prior_verified_pairs': len(linked),
        'AI_candidates_review_leads_only': len(leads),
        'AI_candidates_admitted_as_confirmed': 0,
        'ethereum_event_edges_observed': len(chain_edges),
        'ethereum_nodes_observed': len(chain_nodes),
        'ethereum_seed_wallets_with_event_neighborhood': len(represented),
        'linked_wallet_month_activity_rows': len(month),
        'x_interaction_edges_observed': len(edges),
        'x_nodes_observed': len(nodes),
        'x_authored_posts_observed': len(posts),
        'linked_x_accounts_with_observed_interaction_edges': len(observed_sources),
        'linked_wallets_without_chain_event_neighborhood': len(wallets - represented),
        'linked_accounts_without_cached_timeline': sum(r['timeline_observation_status'] == 'no_cached_timeline' for r in coverage),
        'historical_asof_validated_pairs': 0,
        'new_X_requests': 0, 'new_paid_queries': 0,
        'limitations': [
            'Crosswalk links are current account-side snapshots, not historical as-of links.',
            'AI candidate labels are review leads only and are excluded from mappings, graph attribution, and analyses.',
            'Only the original 12 human-confirmed seed links are admitted to this package.',
            'Ethereum event graph covers the original 12-wallet seed neighborhood only.',
            'Additional mapped wallets have monthly counts where cached but no detailed transfer edges.',
            'X timeline observations may be truncated or incomplete; absence of an edge is not evidence of no interaction.',
            'Repost observations lack repost action time and are excluded from temporal edges.',
            'Following relationships were not collected and are not represented as historical edges.',
        ],
    }
    data_paths = [p for p in OUT.iterdir() if p.is_file() and p.name not in {'dataset_manifest.json', 'run.log'}]
    manifest['file_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in data_paths}
    (OUT / 'dataset_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    readme = f'''# ENS/X 双图数据集：可审计快照（2026-09-26）

本目录含分层钱包—X 映射、已缓存的以太坊逐事件图与 X 带时间戳互动图。
研究时间窗为 `[{WINDOW_START}, {WINDOW_END})`。

- 确认映射：{len(linked)} 对，仅含原有 12 个账号侧人工确认种子。231 个 AI 候选仅列于 `review_leads_ai_only.csv`，全部待人工核验，不进入映射或图归属分析。
- 链上图：{len(chain_nodes)} 节点、{len(chain_edges)} 条逐事件边，只覆盖原有 12 个种子的钱包邻域。新增映射的钱包尚无逐事件边；其已有月度活动记录在 `linked_wallet_month_activity_2026.csv`。
- 社交图：{len(nodes)} 节点、{len(edges)} 条带时间戳互动边、{len(posts)} 条账号撰写的缓存帖子。页面/月份覆盖不完整，见 `coverage_by_linked_wallet.csv`。
- 现有资料不能证明历史交易时点的身份关联；`historical_asof_validated_pairs=0`。转发没有动作时间，未当作带时间戳的互动边。
- 本次打包没有新增 X 请求或付费查询。详细计数、哈希与缺口见 `dataset_manifest.json`。

这些数据可用于方法开发和覆盖审计；不能将快照映射或未观测到的社交边表述为完整历史双图。
'''
    (OUT / 'README.md').write_text(readme, encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'file_sha256'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
