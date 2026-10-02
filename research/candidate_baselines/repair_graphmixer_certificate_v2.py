"""Archive mixed-direction artifacts, repair GM inputs, retain all other inputs."""
from pathlib import Path
import argparse, hashlib, json, os, pickle, shutil, time
import numpy as np
import pandas as pd
from graphmixer_features_v2 import outgoing_index, candidate_matrix
from train_certificate_v2 import dump
import motif_certificate_fixed_pool as old


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);a=ap.parse_args()
    root=Path(a.run);done=root/'graphmixer_correction.json'
    if done.exists():
        print(done.read_text());return
    start=time.time();archive=root/'superseded_graphmixer_mixed_direction';archive.mkdir(exist_ok=True)
    (archive/'shards').mkdir(exist_ok=True)
    if not (archive/'normalization.json').exists():shutil.copy2(root/'normalization.json',archive/'normalization.json')
    if not (archive/'schema_asof_audit.json').exists():shutil.copy2(root/'schema_asof_audit.json',archive/'schema_asof_audit.json')
    stats=json.loads((archive/'normalization.json').read_text())
    months=['2022-03','2022-04','2022-05','2022-06']
    frames=[pd.read_parquet(old.SRC/(m+'.parquet'),columns=['target_address','counterparty_address','direction','block_timestamp']) for m in months]
    role=pd.concat(frames,ignore_index=True);del frames
    role['block_timestamp']=pd.to_datetime(role.block_timestamp,utc=True)
    for k in ['target_address','counterparty_address','direction']:role[k]=role[k].fillna('').astype(str).str.lower()
    cache=old.load_cache(old.GM_CACHE);audits=[];n=0;su=np.zeros(5);sq=np.zeros(5)
    for path in sorted((root/'shards').glob('*.pkl')):
        backup=archive/'shards'/path.name
        if not backup.exists():shutil.copy2(path,backup)
        with backup.open('rb') as f:cases=pickle.load(f)
        idx=outgoing_index(role,path.stem,[r['wallet'] for r in cases]);changed=added=checked=0;cached_error=0.
        for r in cases:
            original=cache[r['case_id']];pos={c:i for i,c in enumerate(original['pool'])}
            matrix=candidate_matrix(idx,r['wallet'],r['pool'])
            pairs=[(i,pos[c]) for i,c in enumerate(r['pool']) if c in pos]
            error=float(np.abs(matrix[[i for i,_ in pairs]]-original['cand_feats'][[j for _,j in pairs]]).max())
            assert error<1e-5,(r['case_id'],error)
            assert np.array_equal(r['seq'],original['seq'])
            cached_error=max(cached_error,error);checked+=len(pairs);added+=len(matrix)-len(pairs)
            changed+=int(np.any(matrix!=r['gm'],axis=1).sum());r['gm']=matrix
            if r['split']!='dev':
                x=matrix.astype(np.float64);n+=len(x);su+=x.sum(0);sq+=(x*x).sum(0)
        tmp=path.with_suffix('.repair.tmp')
        with tmp.open('wb') as f:pickle.dump(cases,f,protocol=4)
        os.replace(tmp,path)
        audit=dict(cutoff=path.stem,cases=len(cases),cached_rows=checked,added_rows=added,changed_rows=changed,
                   cached_max_absolute_error=cached_error,before_sha256=sha(backup),after_sha256=sha(path))
        audits.append(audit);dump(archive/'progress.json',audits);print(json.dumps(audit),flush=True)
    mean=su/n;std=np.sqrt(np.maximum(0,sq/n-mean**2));std[std<1e-6]=1.
    stats['gm']=dict(mean=mean.tolist(),std=std.tolist(),n_train_rows=n)
    current=json.loads((root/'normalization.json').read_text())
    assert all(current[k]==stats[k] for k in stats if k!='gm')
    dump(root/'normalization.json',stats)
    model=root/'models'/'graphmixer'
    if model.exists():
        assert all((model/f'seed{s}'/'complete.json').exists() for s in range(3))
        assert not (archive/'models').exists();shutil.move(model,archive/'models')
    schema=json.loads((root/'schema_asof_audit.json').read_text())
    schema['sequence_semantics']='cached as-of outgoing role events; cross-family same-tx order is only a tie breaker'
    dump(root/'schema_asof_audit.json',schema)
    result=dict(status='repaired_pending_graphmixer_retrain',cause='new candidates mixed both-direction counters with original outgoing-only cached candidates',
                fix='all candidate GM features recomputed from strict-as-of outgoing role rows; all cached features and sequences verified',
                audits=audits,seconds=time.time()-start,partitions=months,august_opened=False,
                archived=str(archive),normalization_changed_keys=['gm'],
                other_models='B/C/E/X/context/sequence and their normalization unchanged; their checkpoints carry unused old GM normalization',
                superseded_graphmixer_runs=3)
    dump(done,result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
