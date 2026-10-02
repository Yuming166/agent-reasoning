#!/usr/bin/env python3
"""Extract event-level certificates for one cutoff group.

This is a parallelizable worker for the fixed-pool certificate round. It only
reads the March-July offline cache; August remains excluded by construction.
"""
from __future__ import annotations
import argparse, json, pickle, time
from collections import Counter
from pathlib import Path
import pandas as pd
import motif_certificate_fixed_pool as cfp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cutoff', required=True)
    ap.add_argument('--fixed-cache', type=Path, required=True)
    ap.add_argument('--events-cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    with args.fixed_cache.open('rb') as f:
        fixed = pickle.load(f)
    cases = [c for c in fixed if c['cutoff'] == args.cutoff]
    with args.events_cache.open('rb') as f:
        ev = pickle.load(f)
    # extract_cert_features assumes every case supplied has one cutoff; this
    # keeps the worker's bounded certificate counters independent.
    enriched = cfp.extract_cert_features(ev, cases, args.out)
    (args.out / 'worker_manifest.json').write_text(json.dumps({
        'status': 'complete', 'cutoff': args.cutoff, 'cases': len(cases),
        'events': len(ev), 'elapsed_seconds': time.time() - t0,
        'august_partition_opened': False,
    }, indent=2) + '\n')
    print(json.dumps({'status': 'complete', 'cutoff': args.cutoff,
                      'cases': len(cases), 'seconds': time.time() - t0}), flush=True)

if __name__ == '__main__':
    main()
