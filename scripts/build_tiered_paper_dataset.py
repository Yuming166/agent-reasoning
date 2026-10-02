#!/usr/bin/env python3
"""Build an offline, evidence-tiered ENS/X research snapshot from archived data."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SOURCE = ROOT / 'artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926'
MONTH_SOURCE = ROOT / 'artifacts/ens_x_crosswalk/final_validated_address_month_events_2026.parquet'
OUT = ROOT / 'artifacts/ens_x_crosswalk/paper_dataset_tiered_20260926'
WINDOW_START = '2026-01-01T00:00:00Z'
WINDOW_END = '2026-09-24T17:24:10Z'


def read_csv(name: str) -> list[dict]:
    with (SOURCE / name).open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def read_jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (SOURCE / name).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_csv(name: str, rows: list[dict], fields: list[str]) -> None:
    with (OUT / name).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    strict = read_csv('crosswalk_analysis_snapshot.csv')
    candidates = read_csv('candidate_review_ai_231.csv')
    coverage = read_csv('partial_provisional_timeline_coverage.csv')
    strict_posts = read_jsonl('x_authored_posts_observed.jsonl')
    provisional_posts = read_jsonl('partial_provisional_x_authored_posts.jsonl')
    strict_edges = read_csv('x_interaction_edges_observed.csv')
    provisional_edges = read_csv('partial_provisional_x_interaction_edges.csv')
    labels = read_jsonl('sentiment_labels.jsonl')

    assert len(strict) == 12 and len(candidates) == 231 and len(coverage) == 74
    assert len(strict_posts) == 267 and len(provisional_posts) == 1771
    assert len(strict_edges) == 162 and len(provisional_edges) == 1694
    strict_ids = {r['x_user_id'] for r in strict}
    candidate_ids = {r['x_user_id'] for r in candidates}
    observed_ids = {r['x_user_id'] for r in coverage}
    assert len(strict_ids) == 12 and len(candidate_ids) == 231
    assert not strict_ids & candidate_ids and observed_ids <= candidate_ids
    assert len({r['address'].lower() for r in strict + candidates}) == 243
    assert len({r['tweet_id'] for r in strict_posts + provisional_posts}) == 2038
    assert {r['x_user_id'] for r in strict_posts} <= strict_ids
    assert {r['x_user_id'] for r in provisional_posts} <= observed_ids
    assert {r['source_x_user_id'] for r in strict_edges} <= strict_ids
    assert {r['source_x_user_id'] for r in provisional_edges} <= observed_ids

    crosswalk = []
    for r in strict:
        crosswalk.append({'address': r['address'].lower(), 'x_user_id': r['x_user_id'],
                          'handle': r['handle'], 'evidence_tier': 'strict_account_side_reviewed',
                          'ai_verdict': '', 'asof_validated': False,
                          'use_for_confirmed_snapshot': True, 'use_for_historical_attribution': False,
                          'evidence_source': 'crosswalk_analysis_snapshot.csv'})
    for r in candidates:
        verdict = r['ai_verdict']
        tier = 'ai_explicit_wallet_in_bio' if verdict == 'account_confirms' else 'ens_profile_screen_only'
        crosswalk.append({'address': r['address'].lower(), 'x_user_id': r['x_user_id'],
                          'handle': r['handle_at_profile_audit'], 'evidence_tier': tier,
                          'ai_verdict': verdict, 'asof_validated': False,
                          'use_for_confirmed_snapshot': False, 'use_for_historical_attribution': False,
                          'evidence_source': 'candidate_review_ai_231.csv'})
    write_csv('crosswalk_evidence_tiers.csv', crosswalk,
              ['address', 'x_user_id', 'handle', 'evidence_tier', 'ai_verdict',
               'asof_validated', 'use_for_confirmed_snapshot',
               'use_for_historical_attribution', 'evidence_source'])
    by_uid = {r['x_user_id']: r for r in crosswalk}

    # Keep the two observed graph edge sets separate while also providing one
    # typed social graph. The candidate sources remain explicitly provisional.
    for source_name, output_name in [
        ('ethereum_address_nodes_observed.csv', 'ethereum_seed_address_nodes.csv'),
        ('ethereum_event_edges_observed.csv', 'ethereum_seed_event_edges.csv'),
        ('x_user_nodes_observed.csv', 'x_strict_user_nodes.csv'),
        ('x_interaction_edges_observed.csv', 'x_strict_interaction_edges.csv'),
        ('partial_provisional_x_interaction_edges.csv', 'x_provisional_interaction_edges.csv'),
    ]:
        shutil.copyfile(SOURCE / source_name, OUT / output_name)
    social_edges = []
    for r in strict_edges + provisional_edges:
        source = by_uid[r['source_x_user_id']]
        target = by_uid.get(r['target_x_user_id'])
        social_edges.append({
            'source_x_user_id': r['source_x_user_id'],
            'target_x_user_id': r['target_x_user_id'],
            'event_type': r['event_type'],
            'created_at_utc': r['created_at_utc'],
            'source_post_id': r['source_post_id'],
            'target_post_id': r.get('target_post_id', ''),
            'time_semantics': r['time_semantics'],
            'source_identity_tier': source['evidence_tier'],
            'target_identity_tier': target['evidence_tier'] if target else 'external_unmapped',
        })
    assert len({(r['source_x_user_id'], r['target_x_user_id'], r['event_type'],
                 r['source_post_id']) for r in social_edges}) == len(social_edges)
    write_csv('x_interaction_edges_tiered.csv', social_edges,
              ['source_x_user_id', 'target_x_user_id', 'event_type', 'created_at_utc',
               'source_post_id', 'target_post_id', 'time_semantics',
               'source_identity_tier', 'target_identity_tier'])
    social_node_ids = strict_ids | observed_ids
    social_node_ids |= {r['target_x_user_id'] for r in social_edges}
    source_ids = {r['source_x_user_id'] for r in social_edges}
    social_nodes = []
    for uid in sorted(social_node_ids):
        mapping = by_uid.get(uid)
        social_nodes.append({'x_user_id': uid,
                             'address': mapping['address'] if mapping else '',
                             'identity_tier': mapping['evidence_tier'] if mapping else 'external_unmapped',
                             'has_observed_timeline': uid in strict_ids | observed_ids,
                             'has_observed_dated_interaction': uid in source_ids})
    write_csv('x_user_nodes_tiered.csv', social_nodes,
              ['x_user_id', 'address', 'identity_tier', 'has_observed_timeline',
               'has_observed_dated_interaction'])
    with (OUT / 'x_authored_posts_tiered.jsonl').open('w', encoding='utf-8') as stream:
        for row in strict_posts + provisional_posts:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')

    # This cache has monthly counts for validated ENS addresses. It is not a
    # detailed event graph for the newly screened 231 wallets.
    month_rows = pq.read_table(MONTH_SOURCE, columns=['address', 'month', 'tx_events',
                                                        'token_events', 'total']).to_pylist()
    monthly = []
    for r in month_rows:
        addr = r['address'].lower()
        if addr not in {x['address'] for x in crosswalk}:
            continue
        monthly.append({'address': addr, 'month': r['month'],
                        'tx_events': r['tx_events'], 'token_events': r['token_events'],
                        'total_events': r['total']})
    assert len({(r['address'], r['month']) for r in monthly}) == len(monthly)
    write_csv('wallet_month_activity_observed.csv', monthly,
              ['address', 'month', 'tx_events', 'token_events', 'total_events'])

    # Verify every inherited label against both account identity and the
    # exact author text that was sent to the local sentiment model.
    labels_by_tweet = {r['tweet_id']: r for r in labels}
    assert len(labels_by_tweet) == len(labels) == len(provisional_posts)
    provisional_by_tweet = {r['tweet_id']: r for r in provisional_posts}
    sentiment = []
    for tweet_id, post in provisional_by_tweet.items():
        label = labels_by_tweet[tweet_id]
        assert label['x_user_id'] == post['x_user_id']
        assert label['created_at_utc'] == post['created_at_utc']
        assert label['authored_text_sha256'] == hashlib.sha256(post['authored_text'].encode()).hexdigest()
        assert post['post_kind'] != 'repost'
        assert WINDOW_START <= post['created_at_utc'] < WINDOW_END
        identity = by_uid[post['x_user_id']]
        sentiment.append({'address': identity['address'], 'x_user_id': post['x_user_id'],
                          'tweet_id': tweet_id, 'created_at_utc': post['created_at_utc'],
                          'month': post['created_at_utc'][:7], 'post_kind': post['post_kind'],
                          'identity_tier': identity['evidence_tier'],
                          'stance': label['stance'], 'target': label['target'],
                          'valence': label['valence'], 'uncertainty': label['uncertainty'],
                          'model': label['model'],
                          'timeline_is_complete': False})
    write_csv('provisional_post_sentiment_observed.csv', sentiment,
              ['address', 'x_user_id', 'tweet_id', 'created_at_utc', 'month', 'post_kind',
               'identity_tier', 'stance', 'target', 'valence', 'uncertainty', 'model',
               'timeline_is_complete'])

    group = defaultdict(list)
    for r in sentiment:
        group[(r['address'], r['x_user_id'], r['month'])].append(r)
    monthly_sentiment = []
    for (address, uid, month), items in sorted(group.items()):
        relevant = [r for r in items if r['stance'] != 'not_applicable']
        monthly_sentiment.append({'address': address, 'x_user_id': uid,
                                  'month': month, 'observed_authored_posts': len(items),
                                  'observed_stance_posts': len(relevant),
                                  'observed_bullish': sum(r['stance'] == 'bullish' for r in items),
                                  'observed_bearish': sum(r['stance'] == 'bearish' for r in items),
                                  'observed_neutral': sum(r['stance'] == 'neutral' for r in items),
                                  'observed_mixed': sum(r['stance'] == 'mixed' for r in items),
                                  'observed_not_applicable': sum(r['stance'] == 'not_applicable' for r in items),
                                  'observed_valence_sum': sum(int(r['valence']) for r in relevant),
                                  'timeline_is_complete': False,
                                  'identity_tier': by_uid[uid]['evidence_tier']})
    write_csv('provisional_wallet_month_sentiment_observed.csv', monthly_sentiment,
              ['address', 'x_user_id', 'month', 'observed_authored_posts',
               'observed_stance_posts', 'observed_bullish', 'observed_bearish',
               'observed_neutral', 'observed_mixed', 'observed_not_applicable',
               'observed_valence_sum', 'timeline_is_complete', 'identity_tier'])

    strict_sentiment = []
    strict_journal = OUT / 'sentiment_labels.jsonl'
    strict_exit = OUT / 'seed_sentiment_exit_code'
    if strict_exit.exists() and strict_exit.read_text().strip() == '0':
        strict_labels = [json.loads(line) for line in strict_journal.read_text().splitlines() if line.strip()]
        assert len(strict_labels) == len(strict_posts)
        strict_by_tweet = {r['tweet_id']: r for r in strict_labels}
        assert len(strict_by_tweet) == len(strict_labels)
        for post in strict_posts:
            label = strict_by_tweet[post['tweet_id']]
            assert label['x_user_id'] == post['x_user_id']
            assert label['created_at_utc'] == post['created_at_utc']
            assert label['authored_text_sha256'] == hashlib.sha256(post['authored_text'].encode()).hexdigest()
            assert label['identity_tier'] == 'strict_account_side_reviewed_snapshot'
            assert post['post_kind'] != 'repost'
            identity = by_uid[post['x_user_id']]
            strict_sentiment.append({'address': identity['address'], 'x_user_id': post['x_user_id'],
                                     'tweet_id': post['tweet_id'], 'created_at_utc': post['created_at_utc'],
                                     'month': post['created_at_utc'][:7], 'post_kind': post['post_kind'],
                                     'identity_tier': identity['evidence_tier'],
                                     'stance': label['stance'], 'target': label['target'],
                                     'valence': label['valence'], 'uncertainty': label['uncertainty'],
                                     'model': label['model'], 'timeline_is_complete': False})
        write_csv('strict_post_sentiment_observed.csv', strict_sentiment,
                  ['address', 'x_user_id', 'tweet_id', 'created_at_utc', 'month', 'post_kind',
                   'identity_tier', 'stance', 'target', 'valence', 'uncertainty', 'model',
                   'timeline_is_complete'])
    all_sentiment = strict_sentiment + sentiment
    write_csv('post_sentiment_all_tiered.csv', all_sentiment,
              ['address', 'x_user_id', 'tweet_id', 'created_at_utc', 'month', 'post_kind',
               'identity_tier', 'stance', 'target', 'valence', 'uncertainty', 'model',
               'timeline_is_complete'])
    all_groups = defaultdict(list)
    for r in all_sentiment:
        all_groups[(r['address'], r['x_user_id'], r['month'])].append(r)
    all_month_sentiment = []
    for (address, uid, month), items in sorted(all_groups.items()):
        relevant = [r for r in items if r['stance'] != 'not_applicable']
        all_month_sentiment.append({
            'address': address, 'x_user_id': uid, 'month': month,
            'identity_tier': by_uid[uid]['evidence_tier'],
            'observed_authored_posts': len(items),
            'observed_stance_posts': len(relevant),
            'observed_bullish': sum(r['stance'] == 'bullish' for r in items),
            'observed_bearish': sum(r['stance'] == 'bearish' for r in items),
            'observed_neutral': sum(r['stance'] == 'neutral' for r in items),
            'observed_mixed': sum(r['stance'] == 'mixed' for r in items),
            'observed_not_applicable': sum(r['stance'] == 'not_applicable' for r in items),
            'observed_valence_sum': sum(int(r['valence']) for r in relevant),
            'timeline_is_complete': False,
        })
    write_csv('wallet_month_sentiment_all_tiered.csv', all_month_sentiment,
              ['address', 'x_user_id', 'month', 'identity_tier', 'observed_authored_posts',
               'observed_stance_posts', 'observed_bullish', 'observed_bearish',
               'observed_neutral', 'observed_mixed', 'observed_not_applicable',
               'observed_valence_sum', 'timeline_is_complete'])

    # Restrict the graph summaries to observed edges. A missing interaction is
    # never treated as a negative edge when timelines are incomplete.
    strict_internal = sum(r['target_x_user_id'] in strict_ids for r in strict_edges)
    provisional_internal = sum(r['target_x_user_id'] in observed_ids for r in provisional_edges)
    mapped_interactions = []
    for r in strict_edges + provisional_edges:
        source = by_uid.get(r['source_x_user_id'])
        target = by_uid.get(r['target_x_user_id'])
        if source is None or target is None:
            continue
        mapped_interactions.append({
            'source_x_user_id': r['source_x_user_id'],
            'source_address': source['address'],
            'source_evidence_tier': source['evidence_tier'],
            'target_x_user_id': r['target_x_user_id'],
            'target_address': target['address'],
            'target_evidence_tier': target['evidence_tier'],
            'event_type': r['event_type'],
            'created_at_utc': r['created_at_utc'],
            'source_post_id': r['source_post_id'],
            'historical_link_validated': False,
        })
    write_csv('mapped_frame_interactions_observed.csv', mapped_interactions,
              ['source_x_user_id', 'source_address', 'source_evidence_tier',
               'target_x_user_id', 'target_address', 'target_evidence_tier',
               'event_type', 'created_at_utc', 'source_post_id',
               'historical_link_validated'])
    timestamps = [r['created_at_utc'] for r in strict_edges + provisional_edges]
    assert all(WINDOW_START <= t < WINDOW_END for t in timestamps)
    assert all(WINDOW_START <= r['created_at_utc'] < WINDOW_END for r in strict_posts)
    assert len({r['x_user_id'] for r in coverage}) == len(coverage)
    coverage_status = Counter(r['stop_reason'] for r in coverage)
    observed_wallets = {r['address'] for r in monthly}
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'fixed_window_start_inclusive_utc': WINDOW_START,
        'fixed_window_end_exclusive_utc': WINDOW_END,
        'strict_account_side_reviewed_pairs': 12,
        'ai_explicit_wallet_in_bio_leads': 1,
        'ens_profile_screen_only_pairs': 230,
        'historically_asof_validated_pairs': 0,
        'monthly_chain_activity_rows': len(monthly),
        'wallets_with_cached_monthly_chain_activity': len(observed_wallets),
        'wallets_missing_cached_monthly_chain_activity': len(crosswalk) - len(observed_wallets),
        'strict_chain_graph_nodes': 247,
        'strict_chain_graph_event_edges': 4218,
        'strict_social_graph_nodes': 68,
        'strict_social_graph_interaction_edges': len(strict_edges),
        'tiered_social_graph_nodes': len(social_nodes),
        'tiered_social_graph_interaction_edges': len(social_edges),
        'strict_social_edges_between_mapped_accounts': strict_internal,
        'provisional_accounts_with_bounded_timeline_observation': len(observed_ids),
        'provisional_social_interaction_edges': len(provisional_edges),
        'provisional_social_edges_between_observed_candidate_accounts': provisional_internal,
        'social_edges_with_both_endpoints_in_243_pair_frame': len(mapped_interactions),
        'unique_directed_pairs_with_both_endpoints_in_frame': len({
            (r['source_x_user_id'], r['target_x_user_id']) for r in mapped_interactions}),
        'strict_authored_posts': len(strict_posts),
        'strict_authored_posts_with_ai_sentiment': len(strict_sentiment),
        'provisional_authored_posts_with_ai_sentiment': len(sentiment),
        'all_wallet_month_sentiment_rows': len(all_month_sentiment),
        'provisional_wallet_month_sentiment_rows': len(monthly_sentiment),
        'timeline_stop_reasons': dict(coverage_status),
        'provisional_stance_counts': dict(Counter(r['stance'] for r in sentiment)),
        'new_X_requests': 0,
        'new_paid_queries': 0,
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in
                          [MONTH_SOURCE] + [SOURCE / n for n in
                           ('crosswalk_analysis_snapshot.csv', 'candidate_review_ai_231.csv',
                            'partial_provisional_timeline_coverage.csv',
                            'x_authored_posts_observed.jsonl',
                            'partial_provisional_x_authored_posts.jsonl',
                            'x_interaction_edges_observed.csv',
                            'partial_provisional_x_interaction_edges.csv',
                            'sentiment_labels.jsonl')]},
        'limitations': [
            'The 12 strict links and one AI wallet-in-bio lead are current snapshots; none are historical as-of links.',
            'The 230 ENS/profile screen pairs are not verified identities and are excluded from confirmed graph attribution.',
            'Detailed Ethereum event edges exist only for the original 12 seed wallets. Other wallets have monthly counts.',
            'Observed timeline pages are incomplete or uncertain; no-edge and zero-post inferences are invalid.',
            'AI sentiment labels are research features, not human gold labels; the current labels cover provisional posts only.',
            'Following relations and dated repost actions are absent.'
        ]
    }
    write_json('report.json', report)
    (OUT / 'README.md').write_text(
        '# ENS–X paper dataset: evidence-tiered offline snapshot\n\n'
        'Fixed observation window: `[2026-01-01T00:00:00Z, 2026-09-24T17:24:10Z)`. '
        'All files here are derived from archived data; this build makes zero X requests and zero paid queries.\n\n'
        '## Identity tiers\n\n'
        '- `strict_account_side_reviewed`: 12 original account-side reviewed wallet–stable-X-ID pairs. '
        'These are current snapshots, not historical as-of links.\n'
        '- `ai_explicit_wallet_in_bio`: one additional strong AI lead with the full wallet address '
        'quoted and checked against the archived X bio. Keep separate from the strict tier.\n'
        '- `ens_profile_screen_only`: 230 screened pairs without sufficient account-side proof. '
        'Their X content and edges are exploratory observations only.\n\n'
        '## Files\n\n'
        '- `crosswalk_evidence_tiers.csv`: 243 pairs with explicit use flags.\n'
        '- `ethereum_seed_address_nodes.csv`, `ethereum_seed_event_edges.csv`: the original '
        '12-wallet observed transaction graph.\n'
        '- `x_user_nodes_tiered.csv`, `x_interaction_edges_tiered.csv`: the combined observed '
        'social graph with source and target identity tiers. Strict and provisional edges also have '
        'their own files.\n'
        '- `x_authored_posts_tiered.jsonl`: the archived authored text used for sentiment; '
        'keep internal unless the planned release terms allow it.\n'
        '- `wallet_month_activity_observed.csv`: cached monthly native/token event counts for the pair frame. '
        'It is not a detailed event graph for candidate wallets.\n'
        '- `provisional_post_sentiment_observed.csv`: one verified join per archived candidate-authored post '
        'and local-model sentiment label. Reposts are excluded.\n'
        '- `strict_post_sentiment_observed.csv`: corresponding labels for the original 12-account '
        'seed, present when the independent labeling job has completed.\n'
        '- `provisional_wallet_month_sentiment_observed.csv`: sums over *observed* posts only. '
        'Do not interpret a missing row as zero posts or join same-month sentiment into an earlier prediction.\n'
        '- `post_sentiment_all_tiered.csv`, `wallet_month_sentiment_all_tiered.csv`: '
        'combined convenience views retaining identity tiers and observation flags.\n'
        '- `mapped_frame_interactions_observed.csv`: dated interactions whose two endpoints occur '
        'in the 243-pair candidate frame, with evidence tiers on both ends. These are not '
        'historically attributed wallet interactions.\n'
        '- `report.json`: counts, limitations, source hashes. The graph and source posts/edges stay '
        'in `overnight_ai_dataset_20260926`.\n\n'
        '## Experimental boundary\n\n'
        'For a predictive task, freeze an event cutoff, reconstruct historical ENS/address/X evidence '
        'at that cutoff, and use only social content posted before it. Keep strict and provisional '
        'results in separate tables. Missing social edges cannot be negatives until timeline coverage is validated.\n',
        encoding='utf-8')
    report['output_sha256'] = {p.name: digest(p) for p in OUT.iterdir() if p.is_file() and p.name != 'report.json'}
    write_json('report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('source_sha256', 'output_sha256', 'limitations')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
