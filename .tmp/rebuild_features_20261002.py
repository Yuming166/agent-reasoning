"""Rebuild B/C/E in the timefix run's shards from its (verified-correct) canonical ledger.

The 2026-10-01 timefix rebuild reused the invalidated run's B/C/E arrays verbatim
(all 150 dev cases byte-identical; log_age_days pinned at ~9.856, i.e. the 1970
fingerprint). Proofs, pools, gm, ctx, X and seq in that run are verified correct,
so only the history-derived feature blocks are recomputed here.

For every shard cutoff we rebuild History with the current (fixed) epoch_seconds,
recompute proofs + B/C/E per case, verify against freshly verified proofs, and
write parts + shards + certificates into a new run directory. The pool / ctx /
seq / X / gm / cand_bucket blocks are copied byte-for-byte from the source run.
"""
from pathlib import Path
import argparse, hashlib, json, os, pickle, shutil, time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from certificate_history_v2 import History, epoch_seconds
from certificate_v2 import verify

FEATURE_KEYS = ('B', 'C', 'E', 'old_target', 'contract_target')


def dump(path, obj):
    tmp = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    os.replace(tmp, path)


def load_cutoff(arg):
    cutoff, shard_path, canonical_path, out_dir = arg
    started = time.time()
    with open(shard_path, 'rb') as f:
        rows = pickle.load(f)
    canonical = pd.read_parquet(canonical_path)
    canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
    h = History(canonical, cutoff)
    # Guard against reintroducing the unit bug: history must end strictly before cutoff.
    assert int(h.a['timestamp'].max()) < h.ts, (cutoff, int(h.a['timestamp'].max()), h.ts)
    assert int(h.a['timestamp'].min()) > 1600000000, 'timestamp column not in epoch seconds'

    proof_path = Path(out_dir) / 'parts' / (cutoff + '.jsonl')
    shard_out = Path(out_dir) / 'parts' / (cutoff + '.pkl')
    total = 0
    invalid = 0
    rebuilt = 0
    unchanged = 0
    with proof_path.open('w') as pf:
        out_rows = []
        for r0 in rows:
            r = dict(r0)
            for k in FEATURE_KEYS:
                r.pop(k, None)
            proofs = h.proofs(r)
            B, C, E = h.features(r, proofs)
            # Old (buggy) arrays, if still attached to the copied case, must differ
            # where the bug bit; record whether this case actually changed.
            changed = True
            if isinstance(r0.get('B'), np.ndarray) and r0['B'].shape == B.shape:
                changed = float(np.abs(r0['B'] - B).max()) > 1e-5 or float(np.abs(r0['C'] - C).max()) > 1e-5
            rebuilt += int(changed)
            unchanged += int(not changed)
            r.update(B=B, C=C, E=E)
            r['old_target'] = bool(B[r['y_idx'], 0]) if r['y_idx'] >= 0 else False
            r['contract_target'] = r['target'] in h.contracts
            for ps in proofs.values():
                for p in ps:
                    ok, reasons = verify(p, h.lookup)
                    invalid += int(not ok)
                    if not ok:
                        raise AssertionError((r['case_id'], reasons))
                    pf.write(json.dumps(p, separators=(',', ':')) + '\n')
                    total += 1
            out_rows.append(r)
    with shard_out.open('wb') as f:
        pickle.dump(out_rows, f, protocol=4)
    audit = dict(cutoff=cutoff, cases=len(out_rows), certificates=total, invalid=invalid,
                 feature_changed_cases=rebuilt, feature_unchanged_cases=unchanged,
                 history_rows=len(h.df),
                 history_min=str(h.df.block_timestamp.min()),
                 history_max=str(h.df.block_timestamp.max()),
                 history_max_ts=int(h.df.timestamp.max()), cutoff_ts=h.ts,
                 seconds=time.time() - started)
    dump(Path(out_dir) / 'parts' / (cutoff + '.json'), audit)
    summary = {k: audit[k] for k in ('cutoff', 'cases', 'certificates', 'invalid',
                                     'feature_changed_cases', 'feature_unchanged_cases',
                                     'seconds')}
    print(json.dumps(summary), flush=True)
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='timefix run whose pools/gm/ctx are frozen inputs')
    ap.add_argument('--out', required=True, help='new run directory (must not exist)')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    src = Path(args.src); out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'parts').mkdir()
    started = time.time()

    cfg = json.loads((src / 'config.json').read_text())
    cfg.update(status='feature_rebuild_from_verified_ledger', source_run=str(src),
               reason='timefix run reused invalidated B/C/E verbatim; ledger and proofs verified correct',
               reuse_frozen_inputs=['pool', 'ctx', 'seq', 'X', 'gm', 'cand_bucket', 'source_sizes'],
               rebuild_fields=['B', 'C', 'E', 'old_target', 'contract_target', 'proofs', 'certificate mask'],
               august_opened=False)
    dump(out / 'config.json', cfg)

    canonical = pd.read_parquet(src / 'canonical_ledger.parquet')
    canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
    canonical.to_parquet(out / 'canonical_ledger.parquet', index=False)

    old_schema = json.loads((src / 'schema_asof_audit.json').read_text())
    old_schema.update(timestamp_unit='explicit pandas datetime resolution to seconds',
                      feature_rebuild_from_verified_ledger=True, august_opened=False)
    dump(out / 'schema_asof_audit.json', old_schema)

    args_list = [(p.stem, str(p), str(out / 'canonical_ledger.parquet'), str(out))
                 for p in sorted((src / 'shards').glob('*.pkl'))]
    audits = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(load_cutoff, a) for a in args_list]
        for fut in as_completed(futs):
            audits.append(fut.result())
    audits.sort(key=lambda x: x['cutoff'])

    (out / 'shards').mkdir()
    proof_out = (out / 'certificates.jsonl').open('w')
    pool_writer = None
    total = 0
    for a in audits:
        cutoff = a['cutoff']
        shutil.copy2(out / 'parts' / (cutoff + '.pkl'), out / 'shards' / (cutoff + '.pkl'))
        with (out / 'parts' / (cutoff + '.jsonl')).open() as f:
            for line in f:
                proof_out.write(line); total += 1
        tab = pq.read_table(out / 'parts' / (cutoff + '.parquet'))
        if pool_writer is None:
            pool_writer = pq.ParquetWriter(out / 'fixed_candidate_pools.parquet', tab.schema, compression='zstd')
        pool_writer.write_table(tab)
    proof_out.close()
    if pool_writer is not None: pool_writer.close()
    dump(out / 'extraction_progress.json', audits)
    dump(out / 'extraction_complete.json',
         dict(status='extraction_complete', cases=sum(a['cases'] for a in audits),
              certificates=total, invalid=sum(a['invalid'] for a in audits), cutoffs=audits,
              source_run=str(src), timestamp_fixed=True,
              feature_rebuild_from_verified_ledger=True))
    print(json.dumps(dict(rebuild='complete', cases=sum(a['cases'] for a in audits),
                          certificates=total, invalid=sum(a['invalid'] for a in audits),
                          seconds=round(time.time() - started, 1)), flush=True))


if __name__ == '__main__':
    main()
