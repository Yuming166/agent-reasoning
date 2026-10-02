"""Full fixed-union extraction; explicit March--June reads, no August access."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, pickle, shutil, time
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from certificate_v2 import CAPS, BASE_NAMES, CERT_NAMES, EXTRA_NAMES, EXTRA_GROUPS, verify
from certificate_history_v2 import History, canonicalize
from graphmixer_features_v2 import outgoing_index, candidate_matrix
import motif_certificate_fixed_pool as old
import motif_gated_retriever as legacy

def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, default=str)+'\n')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=False)
    started=time.time()
    cfg=dict(status='extracting',seeds=[0,1,2],epochs=6,batch_size=32,lr=.001,weight_decay=.0001,
             checkpoint='final_epoch',caps=CAPS,base_names=BASE_NAMES,cert_names=CERT_NAMES,
             extra_names=EXTRA_NAMES,extra_groups=EXTRA_GROUPS,partitions=['2022-03','2022-04','2022-05','2022-06'],
             pool_rule='sorted union of frozen motif, graphmixer, typed_tgn pools; no label injection',
             train_cases=2150,dev_cases=150,active_dev=52,bound=2.,bootstrap_unit='wallet',
             negative_controls=['within-case popularity-bin certificate permutation','all invalid certificates'],
             high_activity_rule='wallet outgoing tx >= training case 75th percentile',
             deletion_cases=6,deletion_random_repeats=3,bootstrap_repeats=2000,august_opened=False)
    dump(out/'config.json',cfg)
    (out/'source').mkdir()
    for p in Path(__file__).parent.glob('*v2*.py'): shutil.copy2(p,out/'source'/p.name)
    for name in ['motif_gated_retriever.py','graphmixer_train.py','RESUME_PROTOCOL_20261001.md']:
        shutil.copy2(Path(__file__).parent/name,out/'source'/name)
    m=old.load_cache(old.MOTIF_CACHE); g=old.load_cache(old.GM_CACHE); n=old.load_cache(old.TGN_CACHE)
    assert set(m)==set(g)==set(n)
    cases=[]
    for cid in sorted(m):
        a,b,d=m[cid],g[cid],n[cid]
        assert all((a[k]==b[k]==d[k]) for k in ['wallet','cutoff','target','split','active'])
        pool=sorted(set(a['pool'])|set(b['pool'])|set(d['pool']))
        r={k:a[k] for k in ['case_id','wallet','cutoff','target','split','active','visibility']}
        r.update(pool=pool,y_idx=pool.index(a['target']) if a['target'] in pool else -1,
                 ctx=a['ctx'],seq=b['seq'],source_sizes=[len(a['pool']),len(b['pool']),len(d['pool'])])
        cases.append(r)
    del n
    cases.sort(key=lambda r:(r['cutoff'],r['case_id']))
    dev=[r for r in cases if r['split']=='dev']
    audit=dict(cases=len(cases),dev=len(dev),active=sum(r['active'] for r in dev),
               supported_active=sum(r['active'] and r['y_idx']>=0 for r in dev),
               candidate_rows=sum(len(r['pool']) for r in cases),pool_rule=cfg['pool_rule'])
    assert (audit['cases'],audit['dev'],audit['active'],audit['supported_active'])==(2300,150,52,40)
    dump(out/'fixed_pool_audit.json',audit)
    pd.DataFrame([{k:v for k,v in r.items() if k not in ['pool','seq','ctx']} for r in cases]).to_csv(out/'fixed_cases.csv',index=False)
    frames=[]; schema={}
    for month in cfg['partitions']:
        p=old.SRC/(month+'.parquet'); x=pd.read_parquet(p)
        schema[month]=dict(rows=len(x),columns=list(x.columns),bytes=p.stat().st_size)
        frames.append(x); print(json.dumps({'read':month,'rows':len(x)}),flush=True)
    role=pd.concat(frames,ignore_index=True); del frames
    role['block_timestamp']=pd.to_datetime(role.block_timestamp,utc=True)
    for c in ['target_address','counterparty_address','direction','event_family','value_lossless','token_contract_address']:
        role[c]=role[c].fillna('').astype(str)
    role=role.sort_values(['block_timestamp','block_number','transaction_index','event_index'],kind='stable').reset_index(drop=True)
    canonical=canonicalize(role)
    canonical.to_parquet(out/'canonical_ledger.parquet',index=False)
    dump(out/'schema_asof_audit.json',dict(partitions=schema,role_rows=len(role),physical_rows=len(canonical),
         duplicate_role_rows_removed=len(role)-len(canonical),strict_cutoff=True,august_opened=False,
         missing=['selector/input','nonce','gas','protocol labels','trusted token decimals'],
         contract_semantics='observed token contract or receipt creation before cutoff; unobserved means unknown',
         sequence_semantics='cached as-of outgoing role events; cross-family same-tx order is only a tie breaker',
         old_feature_semantics='legacy only: raw-value fingerprint and proxy motif; global counterparty roles include both directions'))
    writer=None; proof_file=(out/'certificates.jsonl').open('w'); totalproof=0; audits=[]
    (out/'shards').mkdir()
    for cutoff in sorted({r['cutoff'] for r in cases}):
        t=time.time(); rows=[r for r in cases if r['cutoff']==cutoff]
        hist=role[role.block_timestamp<pd.Timestamp(cutoff,tz='UTC')]
        print(json.dumps({'cutoff':cutoff,'stage':'index','historical_roles':len(hist)}),flush=True)
        idx=legacy.build_motif_index(hist,cutoff)
        gm_index=outgoing_index(hist,cutoff,[r['wallet'] for r in rows])
        h=History(canonical,cutoff)
        seen=set(h.df.from_address)|set(h.df.to_address)|set(h.df.token_contract_address)
        invalid=0
        for j,r in enumerate(rows):
            assert set(r['pool'])<=seen, 'candidate not observed before cutoff'
            proofs=h.proofs(r); B,C,E=h.features(r,proofs)
            dm=legacy.diffusion_and_motif(idx,r['wallet'])
            # Original feature implementation recomputed on the full union, including missing cached candidates.
            X=np.asarray([legacy.pair_features(idx,r['wallet'],c,dm) for c in r['pool']],np.float32)
            r.update(B=B,C=C,E=E,X=X)
            r['ctx']=np.asarray(legacy.wallet_context(idx,r['wallet']),np.float32)
            orig=g[r['case_id']]; pos={c:i for i,c in enumerate(orig['pool'])}
            r['gm']=candidate_matrix(gm_index,r['wallet'],r['pool'])
            cached=[(i,pos[c]) for i,c in enumerate(r['pool']) if c in pos]
            assert np.allclose(r['gm'][[i for i,_ in cached]],orig['cand_feats'][[j for _,j in cached]],atol=1e-5,rtol=0)
            r['cand_bucket']=np.asarray([int(hashlib.sha1(c.encode()).hexdigest(),16)%32768 for c in r['pool']],dtype=np.int64)
            r['old_target']=bool(B[r['y_idx'],0]) if r['y_idx']>=0 else bool(idx['out_cnt'].get(r['wallet'],{}).get(r['target'],0))
            r['contract_target']=r['target'] in h.contracts
            for ps in proofs.values():
                for p in ps:
                    ok,reasons=verify(p,h.lookup); invalid+=not ok
                    assert ok,reasons
                    proof_file.write(json.dumps(p,separators=(',',':'))+'\n'); totalproof+=1
            tab=pa.Table.from_pydict(dict(case_id=[r['case_id']]*len(r['pool']),candidate=r['pool'],
                                        pool_index=np.arange(len(r['pool']),dtype=np.int32),has_valid_certificate=C[:,0].astype(bool)))
            if writer is None: writer=pq.ParquetWriter(out/'fixed_candidate_pools.parquet',tab.schema,compression='zstd')
            writer.write_table(tab)
            if (j+1)%25==0: print(json.dumps({'cutoff':cutoff,'cases_done':j+1,'certificates':totalproof,'seconds':round(time.time()-t,1)}),flush=True)
        with (out/'shards'/(cutoff+'.pkl')).open('wb') as f: pickle.dump(rows,f,protocol=4)
        audits.append(dict(cutoff=cutoff,cases=len(rows),invalid=invalid,history_max=str(h.df.block_timestamp.max()),
                           counters=dict(h.audit),seconds=time.time()-t))
        proof_file.flush(); dump(out/'extraction_progress.json',audits)
        # Release rich matrices once checkpointed; only one cutoff is live.
        for r in rows:
            for k in ['B','C','E','X','gm','cand_bucket']: r.pop(k,None)
        del idx,h,gm_index
    writer.close(); proof_file.close()
    dump(out/'extraction_complete.json',dict(cases=len(cases),certificates=totalproof,invalid=0,seconds=time.time()-started,cutoffs=audits))
    print(json.dumps({'status':'extraction_complete','seconds':time.time()-started}),flush=True)

if __name__=='__main__': main()
