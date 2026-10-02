"""Check cached and added GraphMixer candidates against raw as-of role rows."""
from pathlib import Path
import argparse, json, math, pickle, time
import numpy as np
import pandas as pd
from train_certificate_v2 import dump
import motif_certificate_fixed_pool as old

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);a=ap.parse_args()
    root=Path(a.run);start=time.time();cache=old.load_cache(old.GM_CACHE)
    audits=[];maxerr=0.;n_added=0;n_cached=0
    for cutoff,months in [('2022-04-01',['2022-03']),('2022-07-01',['2022-03','2022-04','2022-05','2022-06'])]:
        path=root/'shards'/(cutoff+'.pkl')
        if not path.exists(): raise SystemExit('Required shard not yet available: '+str(path))
        with path.open('rb') as f:cases=pickle.load(f)
        if cutoff=='2022-04-01':cases=cases[:25]
        frames=[pd.read_parquet(old.SRC/(m+'.parquet'),columns=['target_address','counterparty_address','direction','block_timestamp']) for m in months]
        role=pd.concat(frames,ignore_index=True);del frames
        role['block_timestamp']=pd.to_datetime(role.block_timestamp,utc=True)
        for k in ['target_address','counterparty_address','direction']:
            role[k]=role[k].fillna('').astype(str).str.lower()
        role=role[(role.block_timestamp<pd.Timestamp(cutoff,tz='UTC')) & (role.direction=='outgoing') & role.counterparty_address.ne('') & role.target_address.ne('')]
        gcnt=role.counterparty_address.value_counts()
        rcnt=role.loc[role.block_timestamp>=pd.Timestamp(cutoff,tz='UTC')-pd.Timedelta(days=30),'counterparty_address'].value_counts()
        needed=role[role.target_address.isin([r['wallet'] for r in cases])]
        grouped={w:g for w,g in needed.groupby('target_address',sort=False)}
        del role,needed
        checked=added=cached=0;cuterr=0.;examples=[]
        for r in cases:
            rows=grouped.get(r['wallet'])
            counts=rows.counterparty_address.value_counts() if rows is not None else {}
            last=rows.groupby('counterparty_address').block_timestamp.max() if rows is not None else {}
            original=set(cache[r['case_id']]['pool'])
            expected=[]
            for candidate in r['pool']:
                own=counts.get(candidate,0)
                age=min(365.,(pd.Timestamp(cutoff,tz='UTC')-last[candidate]).total_seconds()/86400) if own else 365.
                expected.append([math.log1p(gcnt.get(candidate,0)),math.log1p(rcnt.get(candidate,0)),math.log1p(own),math.log1p(age),float(own>0)])
            expected=np.asarray(expected,np.float32);error=np.abs(expected-r['gm'])
            err=float(error.max());cuterr=max(cuterr,err);checked+=len(expected)
            new=[i for i,c in enumerate(r['pool']) if c not in original]
            added+=len(new);cached+=len(expected)-len(new)
            if len(examples)<10 and new:
                i=new[0];examples.append(dict(case_id=r['case_id'],candidate=r['pool'][i],observed=r['gm'][i].tolist(),expected=expected[i].tolist()))
            assert err<1e-5, ('GraphMixer extension semantic mismatch',r['case_id'],err,np.unravel_index(error.argmax(),error.shape))
        n_added+=added;n_cached+=cached;maxerr=max(maxerr,cuterr)
        audits.append(dict(cutoff=cutoff,cases=len(cases),candidate_rows=checked,added_rows=added,cached_rows=cached,max_absolute_error=cuterr,examples=examples))
        print(json.dumps(audits[-1]),flush=True)
    dump(root/'graphmixer_extension_audit.json',dict(status='passed',audits=audits,added_rows=n_added,cached_rows=n_cached,
         max_absolute_error=maxerr,seconds=time.time()-start,
         semantics='outgoing-only target-role counterparty counts; recent 30 days; days since latest outgoing own interaction; strict cutoff; physical unique-tx B is intentionally different',
         partitions=['2022-03','2022-04','2022-05','2022-06'],august_opened=False))

if __name__=='__main__':main()
