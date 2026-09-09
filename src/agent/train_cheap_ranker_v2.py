#!/usr/bin/env python3
"""Train/tune/freeze the v2 cheap ranker after adding unknown negatives.

Training: June v2 candidates only. July and August are untouched validation /
frozen-test panels. Scoring uses average competition ranks for exact ties.
"""
import argparse, glob, json, os, pickle, sys
import numpy as np
import pandas as pd
ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','..'))
sys.path.insert(0,os.path.join(ROOT,'src'))
from agent.data import EVENT_KEY, FEATURE_COLS, META_COLS, add_features, join_meta  # noqa


def read_events_v1(snap):
    d=pd.concat([pd.read_csv(f) for f in glob.glob('artifacts/llm_panel_v1/events/*.csv.gz')],ignore_index=True)
    return d[d.snapshot_date==snap].copy()

def read_events_sept():
    return pd.concat([pd.read_csv(f) for f in glob.glob('artifacts/llm_panel_20220901/events/*.csv.gz')],ignore_index=True)

def read_candidates(snap):
    if snap=='2022-09-01':
        path='artifacts/llm_panel_20220901/candidates/*.csv.gz'
    else:
        path=f'artifacts/llm_panel_v2/{snap}/candidates/*.csv.gz'
    return pd.concat([pd.read_csv(f) for f in glob.glob(path)],ignore_index=True)

def avg_rank_rr(df, score_col):
    # candidate-address tie-break only chooses deterministic ordering; rank is
    # average within equal cheap score, so RR is tie-invariant.
    parts=[]
    for k,g in df.groupby(EVENT_KEY,sort=False):
        g=g.sort_values([score_col,'candidate_address'],ascending=[False,True]).copy()
        g['avg_rank']=g[score_col].rank(method='average',ascending=False)
        pos=g[g.label==1]
        if len(pos)!=1: raise RuntimeError((k,len(pos)))
        parts.append(pos.iloc[0])
    pos=pd.DataFrame(parts)
    rr=1.0/pos.avg_rank
    return {'n_events':int(len(pos)),
            'MRR_unweighted':float(rr.mean()),
            'MRR_popweighted':float((rr*pos.pop_weight).sum()/pos.pop_weight.sum()),
            'R@top_tie':float(((pos.avg_rank==1)*pos.pop_weight).sum()/pos.pop_weight.sum()),
            'R@5':float(((pos.avg_rank<=5)*pos.pop_weight).sum()/pos.pop_weight.sum()),
            'R@10':float(((pos.avg_rank<=10)*pos.pop_weight).sum()/pos.pop_weight.sum())}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--outdir',default='artifacts/llm_panel_v2'); args=ap.parse_args()
    os.makedirs(args.outdir,exist_ok=True)
    months=['2022-06-01','2022-07-01','2022-08-01','2022-09-01']
    frames=[]
    for snap in months:
        ev=read_events_sept() if snap=='2022-09-01' else read_events_v1(snap)
        ca=read_candidates(snap)
        d=add_features(join_meta(ev,ca))
        frames.append(d)
    all_df=pd.concat(frames,ignore_index=True)
    tr=all_df[all_df.snapshot_date=='2022-06-01']
    from sklearn.ensemble import HistGradientBoostingClassifier
    # Same frozen family/hyperparameters as v1; no July/Aug/Sep label use here.
    model=HistGradientBoostingClassifier(max_iter=300,learning_rate=.05,max_depth=6,l2_regularization=1.,random_state=20260909)
    model.fit(tr[FEATURE_COLS].to_numpy(),tr.label.to_numpy())
    model_path=os.path.join(args.outdir,'cheap_ranker_jun_v2_frozen.pkl')
    with open(model_path,'wb') as f: pickle.dump({'model':model,'features':FEATURE_COLS,'trained_on':'2022-06-01 v2 panel','tie_policy':'average competition rank'},f)
    all_df=all_df.copy(); all_df['cheap_score']=model.predict_proba(all_df[FEATURE_COLS].to_numpy())[:,1]
    metrics={}
    for snap in months:
        d=all_df[all_df.snapshot_date==snap]
        m=avg_rank_rr(d,'cheap_score')
        d=d.copy(); d['pop_score']=-d.g_rank
        m['globalpop']=avg_rank_rr(d,'pop_score')
        metrics[snap]=m
    out=os.path.join(args.outdir,'cheap_ranker_v2_metrics.json')
    json.dump({'model':model_path,'overall':metrics},open(out,'w'),indent=2)
    keep=EVENT_KEY+['candidate_address','label','cand_source','g_rank','g_cnt','personal_cnt','days_since','bridge_paths','bridge_signal','cheap_score','stratum','activity','pop_weight','cp_type','counterparty_address','truth_g_rank','evt_cnt_90d','cp_entropy_90d','cp_new_rate_30d']
    scored=os.path.join(args.outdir,'panel_scored_v2.csv.gz')
    all_df[keep].to_csv(scored,index=False,compression='gzip')
    print(json.dumps({'model':model_path,'metrics':metrics,'scored':scored},indent=2))
if __name__=='__main__': main()
