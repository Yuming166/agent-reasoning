from pathlib import Path
import argparse, hashlib, json, os, pickle, shutil, time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from certificate_history_v2 import History, epoch_seconds
from certificate_v2 import CAPS, BASE_NAMES, CERT_NAMES, EXTRA_NAMES, EXTRA_GROUPS, verify


def dump(path, obj):
    tmp = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    os.replace(tmp, path)


def load_cutoff(arg):
    cutoff, old_shard, canonical_path, out_dir = arg
    started = time.time()
    with open(old_shard, 'rb') as f:
        rows = pickle.load(f)
    canonical = pd.read_parquet(canonical_path)
    canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
    h = History(canonical, cutoff)
    proof_path = Path(out_dir) / 'parts' / (cutoff + '.jsonl')
    pool_path = Path(out_dir) / 'parts' / (cutoff + '.parquet')
    shard_path = Path(out_dir) / 'parts' / (cutoff + '.pkl')
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    invalid = 0
    candidate_rows = 0
    with proof_path.open('w') as pf:
        writer = None
        for j, r0 in enumerate(rows):
            r = dict(r0)
            # These fields are frozen upstream inputs. Rebuild all history-derived fields.
            for k in ('B', 'C', 'E', 'old_target', 'contract_target'):
                r.pop(k, None)
            seen = set(h.df.from_address) | set(h.df.to_address) | set(h.df.token_contract_address)
            if not set(r['pool']) <= seen:
                missing = sorted(set(r['pool']) - seen)[:5]
                raise RuntimeError(f'{cutoff} candidate not observed before cutoff: {missing}')
            proofs = h.proofs(r)
            B, C, E = h.features(r, proofs)
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
            n = len(r['pool'])
            candidate_rows += n
            tab = pa.Table.from_pydict(dict(
                case_id=[r['case_id']] * n,
                candidate=r['pool'],
                pool_index=np.arange(n, dtype=np.int32),
                has_valid_certificate=C[:, 0].astype(bool),
            ))
            if writer is None:
                writer = pq.ParquetWriter(pool_path, tab.schema, compression='zstd')
            writer.write_table(tab)
        if writer is not None:
            writer.close()
    with shard_path.open('wb') as f:
        pickle.dump(rows, f, protocol=4)
    audit = dict(cutoff=cutoff, cases=len(rows), certificates=total, invalid=invalid,
                 candidate_rows=candidate_rows, history_rows=len(h.df),
                 history_min=str(h.df.block_timestamp.min()),
                 history_max=str(h.df.block_timestamp.max()),
                 history_max_ts=int(h.df.timestamp.max()), cutoff_ts=h.ts,
                 counters=dict(h.audit), seconds=time.time() - started)
    dump(Path(out_dir) / 'parts' / (cutoff + '.json'), audit)
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--old', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    old = Path(args.old); out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'parts').mkdir()
    started = time.time()
    old_cfg = json.loads((old / 'config.json').read_text())
    cfg = dict(old_cfg)
    cfg.update(status='rebuilding_timestamp_fixed', source_run=str(old),
               invalidated_source_reason='pandas 3 datetime64[us] divided by 1e9 produced millisecond-scale integers',
               reuse_frozen_inputs=['pool', 'ctx', 'seq', 'X', 'gm', 'cand_bucket', 'source_sizes'],
               rebuild_fields=['canonical timestamp', 'B', 'C', 'E', 'old_target', 'contract_target', 'proofs', 'certificate mask'],
               august_opened=False)
    dump(out / 'config.json', cfg)
    for p in old.glob('fixed_cases.csv'):
        shutil.copy2(p, out / p.name)
    shutil.copy2(old / 'fixed_pool_audit.json', out / 'fixed_pool_audit.json')
    canonical_path = old / 'canonical_ledger.parquet'
    canonical = pd.read_parquet(canonical_path)
    canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
    canonical.to_parquet(out / 'canonical_ledger.parquet', index=False)
    # Preserve the calendar schema audit and state that this run independently validates time.
    old_schema = json.loads((old / 'schema_asof_audit.json').read_text())
    old_schema.update(timestamp_unit='explicit pandas datetime resolution to seconds',
                      timestamp_rebuilt_from_block_timestamp=True,
                      strict_calendar_cutoff=True, source_run=str(old), august_opened=False)
    dump(out / 'schema_asof_audit.json', old_schema)
    old_shards = sorted((old / 'shards').glob('*.pkl'))
    args_list = [(p.stem, str(p), str(out / 'canonical_ledger.parquet'), str(out)) for p in old_shards]
    audits = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(load_cutoff, a) for a in args_list]
        for fut in as_completed(futs):
            audit = fut.result(); audits.append(audit)
            print(json.dumps({'cutoff': audit['cutoff'], 'cases': audit['cases'],
                              'certificates': audit['certificates'], 'seconds': round(audit['seconds'], 1)},
                             flush=True))
    audits.sort(key=lambda x: x['cutoff'])
    (out / 'shards').mkdir()
    # Merge independent worker outputs in cutoff order for deterministic files.
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
    dump(out / 'extraction_complete.json', dict(status='extraction_complete', cases=sum(a['cases'] for a in audits),
         certificates=total, invalid=sum(a['invalid'] for a in audits), cutoffs=audits,
         seconds=time.time() - started, source_run=str(old), timestamp_fixed=True))
    # Parts are reproducible intermediates; retain compact audits but remove large duplicates.
    for p in (out / 'parts').glob('*.jsonl'):
        p.unlink()
    for p in (out / 'parts').glob('*.parquet'):
        p.unlink()
    print(json.dumps({'status': 'rebuild_complete', 'certificates': total,
                      'seconds': time.time() - started}), flush=True)


if __name__ == '__main__':
    main()
