#!/usr/bin/env python3
"""Offline, diagnostic temporal graph candidate retrieval on frozen EX-Graph cases."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import log1p
from pathlib import Path
import csv
import json

import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/offline_chain_events_v1_20260929_full'
CASES = ROOT / 'artifacts/fullpanel_candidate_coverage_v1_20260929/case_level.csv'
OUT = ROOT / 'artifacts/graph_retrieval_diagnostic_v2_20260929'
K = (5, 50, 500, 2000)


def graph_rank(wallet, own_recent, inverse, recent_by_wallet, n_wallets):
    peers = Counter()
    # Use only recent observed destinations; exclude common hubs from peer discovery.
    for c in own_recent[:100]:
        users = inverse.get(c, ())
        if 1 < len(users) <= 100:
            weight = log1p(n_wallets / len(users))
            for peer in users:
                if peer != wallet:
                    peers[peer] += weight
    scores = Counter()
    for peer, similarity in peers.most_common(100):
        for rank, c in enumerate(recent_by_wallet[peer][:50], start=1):
            scores[c] += similarity / rank
    return sorted(scores, key=lambda c: (-scores[c], c)), len(peers)


def main():
    if OUT.exists():
        raise SystemExit(f'refusing to overwrite {OUT}')
    OUT.mkdir(parents=True)
    cases = pd.read_csv(CASES)
    cases = cases[(cases.policy == 'attempted') & cases.active].copy()
    parts = []
    for p in sorted(SRC.glob('2022-??.parquet')):
        if p.stem > '2022-07':
            continue
        x = pd.read_parquet(p, columns=['target_address', 'counterparty_address', 'direction', 'event_family', 'block_timestamp', 'block_number', 'transaction_index', 'transaction_hash'])
        x = x[(x.direction == 'outgoing') & (x.event_family == 'external_tx') & x.counterparty_address.notna()]
        parts.append(x)
    events = pd.concat(parts, ignore_index=True)
    details = []
    summaries = []
    for cutoff in sorted(cases.cutoff.unique()):
        t = pd.Timestamp(cutoff, tz='UTC')
        h = events[events.block_timestamp.lt(t)].copy()
        h.sort_values(['block_timestamp', 'block_number', 'transaction_index', 'transaction_hash'], ascending=False, inplace=True)
        distinct = h.drop_duplicates(['target_address', 'counterparty_address'])
        by_wallet = distinct.groupby('target_address', sort=False).counterparty_address.agg(list).to_dict()
        n_wallets = len(by_wallet)
        inverse = defaultdict(list)
        for w, cs in by_wallet.items():
            for c in cs:
                inverse[c].append(w)
        counts = h.counterparty_address.value_counts()
        popular = sorted(counts.index.tolist(), key=lambda c: (-int(counts[c]), c))
        active = cases[cases.cutoff == cutoff]
        for row in active.itertuples(index=False):
            w, y = row.wallet, row.first_target
            own = by_wallet.get(w, [])
            graph, n_peers = graph_rank(w, own, inverse, by_wallet, n_wallets)
            # Fixed, illustrative quota: own 500, graph 1000, global 500; fill vacancies by popularity.
            mix = list(dict.fromkeys(own[:500] + graph[:1000] + popular[:500] + popular))[:2000]
            rec = {'cutoff': cutoff, 'wallet': w, 'target': y, 'n_peers': n_peers,
                   'own_old': y in set(own), 'globally_seen': y in inverse,
                   'graph_pool_size': len(graph), 'mix_hit_2000': y in set(mix),
                   'hybrid_hit_2000': bool(row.hybrid_hit_2000)}
            for k in K:
                rec[f'graph_hit_{k}'] = y in set(graph[:k])
            details.append(rec)
        d = [r for r in details if r['cutoff'] == cutoff]
        summary = {'cutoff': cutoff, 'active': len(d), 'historically_visible': sum(r['globally_seen'] for r in d),
                   'hybrid_hits_2000': sum(r['hybrid_hit_2000'] for r in d),
                   'graph_hits_2000': sum(r['graph_hit_2000'] for r in d),
                   'mix_hits_2000': sum(r['mix_hit_2000'] for r in d),
                   'mix_gain_vs_hybrid': sum(r['mix_hit_2000'] and not r['hybrid_hit_2000'] for r in d),
                   'mix_loss_vs_hybrid': sum(r['hybrid_hit_2000'] and not r['mix_hit_2000'] for r in d)}
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    for name, rows in [('case_level.csv', details), ('summary.csv', summaries)]:
        with (OUT / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'diagnostic_only',
                'source': str(SRC), 'case_source': str(CASES), 'cutoff_rule': 'all graph edges strictly before cutoff',
                'graph_path': 'wallet -> shared historical outgoing destination <- peer wallet -> peer recent destination',
                'graph_hub_cap': 100, 'wallet_recent_seed_count': 100, 'peer_count': 100,
                'peer_destination_count': 50, 'fixed_mix_quota': [500, 1000, 500],
                'note': '240 explored wallets and August already observed; these are diagnostics, not independent test results'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
