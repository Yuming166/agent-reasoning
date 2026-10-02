#!/usr/bin/env python3
"""Offline snapshot of the 50-account pilot plus 24 interrupted candidate accounts."""
from __future__ import annotations


import json
from collections import Counter
from datetime import datetime, timezone

from ens_x_overnight_finalize import OUT, PILOT, RUN, csv_out, jsonl_out, new_graph, rows_csv, rows_jsonl


def main() -> None:
    fresh_edges, fresh_posts, reposts, integrity = new_graph()
    old_edges = rows_csv(PILOT / 'provisional_x_interaction_edges_temporal.csv')
    old_posts = rows_jsonl(PILOT / 'provisional_x_authored_posts.jsonl')
    edge_fields = ['source_x_user_id', 'target_x_user_id', 'event_type', 'created_at_utc',
                   'source_post_id', 'target_post_id', 'time_semantics', 'link_quality']
    edges = {}
    for row in old_edges + fresh_edges:
        row = dict(row)
        row['link_quality'] = 'provisional_candidate'
        key = (row['source_x_user_id'], row['target_x_user_id'], row['event_type'], row['source_post_id'])
        edges[key] = row
    edge_rows = list(edges.values())
    csv_out(OUT / 'partial_provisional_x_interaction_edges.csv', edge_rows, edge_fields)
    posts = {}
    for row in old_posts + fresh_posts:
        row = dict(row)
        row['source_tier'] = 'provisional_candidate'
        posts[str(row['tweet_id'])] = row
    jsonl_out(OUT / 'partial_provisional_x_authored_posts.jsonl', list(posts.values()))
    csv_out(OUT / 'partial_new_repost_observations_untimed.csv', reposts,
            ['x_user_id', 'source_post_id', 'source_post_created_at_utc', 'repost_action_time_known'])
    old_cov = rows_jsonl(PILOT / 'coverage.jsonl')
    new_cov = rows_jsonl(RUN / 'coverage.jsonl')
    observed_ids = {str(r['x_user_id']) for r in old_cov + new_cov}
    coverage = [{'x_user_id': str(r['x_user_id']),
                 'source': 'previous_50_pilot' if i < len(old_cov) else 'interrupted_new_candidate_batch',
                 'pages': r.get('pages', ''), 'stop_reason': r.get('stop_reason', ''),
                 'authored_in_window_observed': r.get('authored_in_window', ''),
                 'full_history_claim': False}
                for i, r in enumerate(old_cov + new_cov)]
    csv_out(OUT / 'partial_provisional_timeline_coverage.csv', coverage, list(coverage[0]))
    report = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'provisional_candidate_frame_pairs': 231,
              'accounts_with_any_bounded_timeline_observation': len(observed_ids),
              'prior_pilot_accounts': len(old_cov), 'new_accounts_before_interruption': len(new_cov),
              'provisional_timestamped_edges_observed': len(edge_rows),
              'provisional_edges_by_type': dict(Counter(r['event_type'] for r in edge_rows)),
              'provisional_authored_posts_observed': len(posts),
              'new_repost_observations_without_action_time': len(reposts),
              'new_normalized_integrity': integrity,
              'new_collector_exit_code': (RUN / 'exit_code').read_text().strip(),
              'historical_asof_validated_links': 0,
              'complete_timeline_claim': False,
              'paid_queries': 0,
              'limitation': 'All new candidate links remain provisional. Collection stopped early; only previously archived pages are represented. No new collection was performed by this offline build.'}
    (OUT / 'partial_provisional_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
