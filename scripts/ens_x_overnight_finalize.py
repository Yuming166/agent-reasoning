#!/usr/bin/env python3
"""Build a clearly provisional 231-account X graph from bounded cached pages.

This does not promote candidate wallet/X identities to confirmed or infer
unobserved historical follow edges. No network or paid data access.
"""
from __future__ import annotations


import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
BASE = ROOT / 'artifacts/ens_x_crosswalk'
OUT = BASE / 'overnight_ai_dataset_20260926'
RUN = OUT / 'candidate_timeline_evidence'
PILOT = BASE / 'timeline_expansion_pilot_20260925'
START = '2026-01-01T00:00:00Z'
END = '2026-09-24T17:24:10Z'


def rows_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def rows_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def csv_out(path: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def jsonl_out(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    tmp.replace(path)


def new_graph() -> tuple[list[dict], list[dict], list[dict], dict]:
    statuses = rows_jsonl(RUN / 'normalized_observed_statuses.jsonl')
    queue = rows_csv(OUT / 'candidate_review_ai_231.csv')
    new_ids = {r['x_user_id'] for r in queue} - {str(r['x_user_id']) for r in json.loads((PILOT / 'pilot_queue.json').read_text())}
    authors = {str(r['tweet_id']): str(r['source_author_id']) for r in statuses
               if not r.get('is_repost') and r.get('source_author_id')}
    edges: dict[tuple[str, str, str, str], dict] = {}
    authored = []
    reposts = []
    raw_cache = {}
    missing_raw = 0
    owner_errors = 0
    for rec in statuses:
        actor = str(rec['queried_user_id'])
        if actor not in new_ids or str(rec.get('timeline_owner_id_verified')) != actor:
            owner_errors += 1
            continue
        if rec.get('is_repost'):
            reposts.append({'x_user_id': actor, 'source_post_id': rec['tweet_id'],
                            'source_post_created_at_utc': rec.get('created_at_utc', ''),
                            'repost_action_time_known': False})
            continue
        when = rec.get('created_at_utc', '')
        if not (START <= when < END):
            continue
        if str(rec.get('source_author_id')) != actor:
            owner_errors += 1
            continue
        authored.append({'x_user_id': actor, 'tweet_id': str(rec['tweet_id']),
                         'created_at_utc': when, 'post_kind': rec.get('post_kind', ''),
                         'authored_text': rec.get('authored_text') or '',
                         'source_tier': 'provisional_candidate'})

        def add(target: object, kind: str, target_post: str = '') -> None:
            if target is None or str(target) in {'', actor}:
                return
            uid = str(target)
            key = (actor, uid, kind, str(rec['tweet_id']))
            edges[key] = {'source_x_user_id': actor, 'target_x_user_id': uid,
                          'event_type': kind, 'created_at_utc': when,
                          'source_post_id': str(rec['tweet_id']),
                          'target_post_id': target_post,
                          'time_semantics': 'authored_post_creation_time',
                          'link_quality': 'provisional_candidate'}

        if rec.get('quoted_author_id'):
            add(rec['quoted_author_id'], 'quote', str(rec.get('quoted_tweet_id') or ''))
        reply_to = rec.get('replying_to_tweet_id')
        if reply_to and str(reply_to) in authors:
            add(authors[str(reply_to)], 'reply', str(reply_to))
        raw_path = RUN / str(rec.get('raw_response_file') or '')
        if not raw_path.is_file():
            missing_raw += 1
            continue
        if raw_path not in raw_cache:
            payload = json.loads(raw_path.read_text(encoding='utf-8'))
            raw_cache[raw_path] = {str(s.get('id')): s for s in payload.get('results', []) if isinstance(s, dict)}
        raw = raw_cache[raw_path].get(str(rec['tweet_id']))
        if raw is None:
            missing_raw += 1
            continue
        for facet in (raw.get('raw_text') or {}).get('facets') or []:
            if isinstance(facet, dict) and facet.get('type') == 'mention' and facet.get('id'):
                add(facet['id'], 'mention')
    if owner_errors:
        raise RuntimeError(f'owner identity errors in normalized statuses: {owner_errors}')
    return list(edges.values()), authored, reposts, {'new_missing_raw_statuses': missing_raw, 'new_owner_errors': owner_errors}


def main() -> None:
    if (RUN / 'exit_code').read_text().strip() != '0':
        raise RuntimeError('candidate timeline collection did not complete successfully')
    fresh_edges, fresh_posts, reposts, integrity = new_graph()
    old_edges = rows_csv(PILOT / 'provisional_x_interaction_edges_temporal.csv')
    old_posts = rows_jsonl(PILOT / 'provisional_x_authored_posts.jsonl')
    edge_fields = ['source_x_user_id', 'target_x_user_id', 'event_type', 'created_at_utc',
                   'source_post_id', 'target_post_id', 'time_semantics', 'link_quality']
    combined_edges = {}
    for row in old_edges + fresh_edges:
        row = dict(row)
        row['link_quality'] = 'provisional_candidate'
        key = (row['source_x_user_id'], row['target_x_user_id'], row['event_type'], row['source_post_id'])
        combined_edges[key] = row
    edges = list(combined_edges.values())
    csv_out(OUT / 'provisional_231_x_interaction_edges.csv', edges, edge_fields)
    posts = {}
    for row in old_posts + fresh_posts:
        row = dict(row)
        row['source_tier'] = 'provisional_candidate'
        posts[str(row['tweet_id'])] = row
    jsonl_out(OUT / 'provisional_231_x_authored_posts.jsonl', list(posts.values()))
    csv_out(OUT / 'new_candidate_repost_observations_untimed.csv', reposts,
            ['x_user_id', 'source_post_id', 'source_post_created_at_utc', 'repost_action_time_known'])

    reviewed = rows_csv(OUT / 'candidate_review_ai_231.csv')
    ids = {r['x_user_id'] for r in reviewed}
    node_ids = ids | {r['target_x_user_id'] for r in edges}
    nodes = [{'x_user_id': uid, 'role': 'provisional_mapped_actor' if uid in ids else 'observed_external_target',
              'wallet_address_candidate': next((r['address'] for r in reviewed if r['x_user_id'] == uid), ''),
              'identity_status': next((r['ai_verdict'] for r in reviewed if r['x_user_id'] == uid), 'external_unmapped')}
             for uid in sorted(node_ids)]
    csv_out(OUT / 'provisional_231_x_nodes.csv', nodes, list(nodes[0]))

    all_wallets = {r['address'].lower() for r in reviewed}
    month = pd.read_parquet(BASE / 'final_validated_address_month_events_2026.parquet')
    month['address'] = month['address'].str.lower()
    month = month[month['address'].isin(all_wallets)]
    month.to_csv(OUT / 'provisional_231_wallet_month_activity_2026.csv', index=False)

    cov_old = rows_jsonl(PILOT / 'coverage.jsonl')
    cov_new = rows_jsonl(RUN / 'coverage.jsonl')
    coverage = []
    for row, source in [(r, 'previous_50_pilot') for r in cov_old] + [(r, 'new_181_bounded') for r in cov_new]:
        coverage.append({'x_user_id': str(row['x_user_id']), 'source': source,
                         'pages': row.get('pages', ''), 'stop_reason': row.get('stop_reason', ''),
                         'author_posts_in_window_observed': row.get('authored_in_window', ''),
                         'full_history_claim': False})
    if len({r['x_user_id'] for r in coverage}) != 231:
        raise RuntimeError('provisional timeline coverage is not 231 unique IDs')
    csv_out(OUT / 'provisional_231_timeline_coverage.csv', coverage, list(coverage[0]))
    collector = json.loads((RUN / 'summary.json').read_text(encoding='utf-8'))
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'provisional_candidate_wallet_x_pairs': 231,
        'timeline_accounts_with_bounded_attempt': len(coverage),
        'previous_pilot_accounts': len(cov_old), 'new_bounded_accounts': len(cov_new),
        'new_http_attempts': collector['new_http_attempts'],
        'new_page_observations': collector['new_timeline_pages_observed'],
        'provisional_social_nodes': len(nodes),
        'provisional_social_timestamped_edges': len(edges),
        'provisional_edges_by_type': dict(Counter(r['event_type'] for r in edges)),
        'provisional_authored_posts_observed': len(posts),
        'new_repost_observations_without_action_time': len(reposts),
        'provisional_wallet_month_activity_rows': len(month),
        'full_timeline_accounts_proven': 0,
        'historical_asof_validated_links': 0,
        'paid_queries': 0, 'integrity': integrity,
        'limitations': [
            'All 231 wallets/X IDs are provisional candidates; the AI evidence verdict is in candidate_review_ai_231.csv.',
            'The original 12-wallet Ethereum event graph is separate; candidate wallets have monthly count features, not detailed transfer edges.',
            'A page ceiling or cursor exhaustion is not proof of complete X history.',
            'Repost source timestamps are not repost action timestamps and are excluded from temporal edges.',
            'Following relationships were not collected as historical edges.',
        ],
    }
    (OUT / 'provisional_231_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'provisional_231_README.md').write_text(
        '# Provisional 231-account research graph\n\n'
        'This graph uses X timeline observations from 231 ENS/X candidate IDs. It is exploratory: '
        'candidate wallet links are not validated historical identity. Review `candidate_review_ai_231.csv` '
        'for per-pair AI evidence verdicts, `provisional_231_timeline_coverage.csv` for page limits, '
        'and `provisional_231_report.json` for counts and limitations.\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
