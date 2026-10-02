"""Final-epoch, full-candidate experiments with complete dev scores and gates."""
from pathlib import Path
from collections import defaultdict
import argparse, hashlib, json, os, pickle, time
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from torch.nn import functional as F
from certificate_models_v2 import Scorer,VARIANTS,ranking_metrics

KEYS=['B','C','E','X','gm','ctx']
def dump(p,obj):
    tmp=p.with_name(p.name+'.tmp.'+str(os.getpid()))
    tmp.write_text(json.dumps(obj,indent=2,default=str)+'\n');os.replace(tmp,p)

def fit_normalization(cases):
    stats={}
    train=[r for r in cases if r['split']!='dev']
    for key in KEYS:
        n=0;su=0.;sq=0.
        for r in train:
            a=np.atleast_2d(r[key]).astype('float64');n+=len(a);su=su+a.sum(0);sq=sq+(a*a).sum(0)
        mean=su/n;std=np.sqrt(np.maximum(0,sq/n-mean**2));std[std<1e-6]=1.
        stats[key]={'mean':mean.tolist(),'std':std.tolist(),'n_train_rows':n}
    seq=np.concatenate([r['seq'][r['seq'][:,1]>0,3:]/100 for r in train])
    std=seq.std(0);std[std<1e-6]=1
    stats['seq']={'mean':seq.mean(0).tolist(),'std':std.tolist(),'n_train_events':len(seq)}
    stats['high_activity_threshold']=float(np.quantile([r['B'][0,9] for r in train],.75))
    stats['fit_splits']=sorted({r['split'] for r in train})
    return stats

def prepare(cases,stats):
    for r in cases:
        r['valid']=r['C'][:,0].copy();r['own_scores']=r['B'][:,1].copy()
        r['high_activity']=bool(r['B'][0,9]>=stats['high_activity_threshold'])
        r['raw_global']=r['B'][:,5].copy()
        for k in KEYS:
            r[k]=((r[k]-np.array(stats[k]['mean'],np.float32))/np.array(stats[k]['std'],np.float32)).astype(np.float32)
        r['seq']=r['seq'].copy()
        r['seq'][:,3:]=np.round(((r['seq'][:,3:]/100-np.array(stats['seq']['mean']))/np.array(stats['seq']['std']))*100).astype('int64')
    return cases

def collate(cases,device,variant,seed):
    n=max(len(r['pool']) for r in cases); out={}
    for key in ['B','C','E','X','gm']:
        a=np.zeros((len(cases),n,cases[0][key].shape[1]),np.float32)
        for i,r in enumerate(cases):
            v=r[key]
            if variant=='popularity_control' and key=='C':
                rng=np.random.default_rng(int(hashlib.sha256((r['case_id']+'|'+str(seed)).encode()).hexdigest()[:8],16))
                # Preserve true validity; break certificate identity within fixed popularity bins.
                perm=np.arange(len(v));bins=np.floor(r['raw_global']).astype(int)
                for b in np.unique(bins):
                    ix=np.flatnonzero(bins==b);perm[ix]=rng.permutation(ix)
                v=v[perm].copy();v[:,0]=r[key][:,0]
            a[i,:len(v)]=v
        out[key]=torch.from_numpy(a).to(device)
    for key in ['valid','cand_bucket']:
        a=np.zeros((len(cases),n),np.float32 if key=='valid' else np.int64)
        for i,r in enumerate(cases):a[i,:len(r[key])]=r[key]
        out[key]=torch.from_numpy(a).to(device)
    out['mask']=torch.tensor([[j<len(r['pool']) for j in range(n)] for r in cases],device=device)
    for key in ['ctx','seq']:out[key]=torch.from_numpy(np.stack([r[key] for r in cases])).to(device)
    out['target']=torch.tensor([max(0,r['y_idx']) for r in cases],device=device)
    out['support']=torch.tensor([r['active'] and r['y_idx']>=0 for r in cases],device=device,dtype=torch.bool)
    out['active']=torch.tensor([r['active'] for r in cases],device=device,dtype=torch.float32)
    out['ow']=torch.tensor([r['visibility']=='open_world' for r in cases],device=device,dtype=torch.float32)
    return out

def auroc(y,p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y,p)) if len(set(y))>1 else None

@torch.no_grad()
def evaluate(model,cases,variant,seed,device,out,save=True):
    model.eval(); rows=[]; writer=None; gs=[];ds=[];zero_fail=0
    for start in range(0,len(cases),8):
        sub=cases[start:start+8]; batch=collate(sub,device,variant,seed)
        s,g,d,base,act,ow=model(batch)
        scores=s.cpu().numpy();gates=g.cpu().numpy();deltas=d.cpu().numpy();bases=base.cpu().numpy()
        aa=torch.sigmoid(act).cpu().numpy(); oo=torch.sigmoid(ow).cpu().numpy()
        for i,r in enumerate(sub):
            n=len(r['pool']); score=scores[i,:n];order=np.argsort(-score,kind='stable');rank=np.empty(n,np.int32);rank[order]=np.arange(1,n+1)
            tr=int(rank[r['y_idx']]) if r['y_idx']>=0 else -1
            row={k:r[k] for k in ['case_id','wallet','cutoff','target','active','visibility','old_target','contract_target','high_activity']}
            row.update(rank=tr,supported=r['y_idx']>=0,seed=seed,variant=variant,activity_p=float(aa[i]),open_world_p=float(oo[i]),
                       top1=r['pool'][order[0]],valid_fraction=float(r['valid'].mean()),
                       target_valid=bool(r['valid'][r['y_idx']]) if r['y_idx']>=0 else False)
            rows.append(row)
            valid=r['valid']>0;gs.extend(gates[i,:n][valid].tolist());ds.extend(deltas[i,:n][valid].tolist())
            if variant not in ['certificate_only','direct_global_chain','legacy_motif','graphmixer','direct_global_legacy']:
                zero_fail+=int(np.count_nonzero(deltas[i,:n][~valid]))
            if save:
                tab=pa.Table.from_pydict(dict(case_id=[r['case_id']]*n,candidate=r['pool'],pool_index=np.arange(n,dtype=np.int32),
                         score=score,rank=rank,gate=gates[i,:n],correction=deltas[i,:n],base_score=bases[i,:n],valid_certificate=valid))
                if writer is None:writer=pq.ParquetWriter(out/'predictions.parquet',tab.schema,compression='zstd')
                writer.write_table(tab)
    if writer:writer.close()
    active=[r for r in rows if r['active']]
    metrics=ranking_metrics([r['rank'] for r in active]);metrics['supported_only']=ranking_metrics([r['rank'] for r in active if r['supported']])
    metrics['strata']={name:ranking_metrics([r['rank'] for r in active if condition(r)]) for name,condition in {
        'old_target':lambda r:r['old_target'],'new_target':lambda r:not r['old_target'],
        'observed_contract_target':lambda r:r['contract_target'],'unknown_contract_status':lambda r:not r['contract_target'],
        'high_activity':lambda r:r['high_activity'],'lower_activity':lambda r:not r['high_activity']}.items()}
    metrics['activity']={'n':len(rows),'auroc':auroc([r['active'] for r in rows],[r['activity_p'] for r in rows]),
                         'brier':float(np.mean([(r['activity_p']-r['active'])**2 for r in rows]))}
    metrics['open_world']={'auroc':auroc([r['visibility']=='open_world' for r in active],[r['open_world_p'] for r in active]),'address_topk_credit':False}
    metrics['gate']={'valid_candidate_n':len(gs),'mean':float(np.mean(gs)) if gs else 0.,'quantiles':np.quantile(gs,[0,.1,.5,.9,.99,1]).tolist() if gs else [],
                     'frac_gt_095':float(np.mean(np.array(gs)>.95)) if gs else 0.,'frac_lt_005':float(np.mean(np.array(gs)<.05)) if gs else 0.,
                     'no_certificate_nonzero_corrections':zero_fail,'max_abs_correction':float(np.max(np.abs(ds))) if ds else 0.}
    assert zero_fail==0
    if variant in ['bounded_residual','chain_all','popularity_control','invalid_control'] or variant.startswith('minus_'):
        assert metrics['gate']['max_abs_correction']<=2.000001
    if save:
        pd.DataFrame(rows).to_csv(out/'case_predictions.csv',index=False);dump(out/'metrics.json',metrics)
    return metrics,rows

def train_one(cases,stats,variant,seed,device,root):
    target=root/'models'/variant/('seed'+str(seed))
    if (target/'complete.json').exists():return
    target.mkdir(parents=True,exist_ok=True)
    torch.manual_seed(seed);np.random.seed(seed)
    model=Scorer(variant).to(device)
    if variant=='legacy_cert_frozen':
        # Start exactly from the corresponding legacy baseline.  Only the
        # certificate residual/gate and auxiliary heads are trainable, so an
        # initially zero residual cannot destroy the established ordering.
        ref=Scorer('direct_global_legacy').to(device)
        ckpt=torch.load(root/'models'/'direct_global_legacy'/('seed'+str(seed))/'model.pt',map_location=device)
        ref.load_state_dict(ckpt['model'])
        model.legacy.load_state_dict(ref.legacy.state_dict())
        model.activity.load_state_dict(ref.activity.state_dict())
        model.open_world.load_state_dict(ref.open_world.state_dict())
        for p in model.legacy.parameters(): p.requires_grad=False
        torch.nn.init.zeros_(model.cert[-1].weight)
        torch.nn.init.zeros_(model.cert[-1].bias)
        del ref
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.001,weight_decay=.0001)
    train=[r for r in cases if r['split']!='dev'];dev=[r for r in cases if r['split']=='dev']
    rng=np.random.default_rng(seed);start=time.time();logs=[]
    for epoch in range(6):
        model.train();order=rng.permutation(len(train));losses=[];updates=0
        for j in range(0,len(order),32):
            sub=[train[k] for k in order[j:j+32]];batch=collate(sub,device,variant,seed)
            opt.zero_grad(set_to_none=True);s,_,_,_,act,ow=model(batch)
            sup=batch['support'];rankloss=F.cross_entropy(s.masked_fill(~batch['mask'],-1e9)[sup],batch['target'][sup]) if sup.any() else s.sum()*0
            loss=rankloss+.2*F.binary_cross_entropy_with_logits(act,batch['active'])+.2*F.binary_cross_entropy_with_logits(ow,batch['ow'])
            assert torch.isfinite(loss)
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);opt.step();updates+=1;losses.append(float(loss.detach()))
        rec=dict(variant=variant,seed=seed,epoch=epoch+1,loss=float(np.mean(losses)),updates=updates,seconds=time.time()-start)
        logs.append(rec);dump(target/'train_log.json',logs);print(json.dumps(rec),flush=True)
    torch.save({'model':model.state_dict(),'variant':variant,'seed':seed,'normalization':stats,'epochs':6},target/'model.pt')
    metrics,rows=evaluate(model,dev,variant,seed,device,target)
    summary=dict(variant=variant,seed=seed,parameters=sum(p.numel() for p in model.parameters()),
                 optimizer_updates=sum(r['updates'] for r in logs),training_cases=len(train),dev_cases=len(dev),seconds=time.time()-start,metrics=metrics)
    dump(target/'complete.json',summary);print(json.dumps({'complete':variant,'seed':seed,'metrics':metrics}),flush=True)
    del model,opt
    if str(device).startswith('cuda'):torch.cuda.empty_cache()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--worker',type=int,default=0);ap.add_argument('--workers',type=int,default=1);ap.add_argument('--device',default='cuda:0');a=ap.parse_args()
    root=Path(a.run);assert (root/'extraction_complete.json').exists()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=True
    cases=[]
    for p in sorted((root/'shards').glob('*.pkl')):
        with p.open('rb') as f:cases.extend(pickle.load(f))
    if a.worker==0:
        stats=fit_normalization(cases);dump(root/'normalization.json',stats)
        dump(root/'training_protocol.json',dict(variants=VARIANTS,seeds=[0,1,2],epochs=6,batch_size=32,
             loss='supported-active full-pool cross entropy + 0.2 activity BCE + 0.2 OPEN_WORLD BCE',grad_clip=5.,
             primary='ALL 52 active; unsupported zero; final epoch',bootstrap='wallet cluster, seeds averaged',tf32=True,
             controls='same Scorer dimensions; fixed within-case integer log-global bins; true validity mask retained',
             train_normalization_only=True,august_opened=False))
    else:
        while not (root/'normalization.json').exists():time.sleep(1)
        stats=json.loads((root/'normalization.json').read_text())
    cases=prepare(cases,stats)
    for i,v in enumerate(VARIANTS):
        if i%a.workers!=a.worker:continue
        for seed in [0,1,2]:train_one(cases,stats,v,seed,a.device,root)
    dump(root/('worker'+str(a.worker)+'_complete.json'),dict(status='complete',variants=VARIANTS[a.worker::a.workers]))

if __name__=='__main__':main()
