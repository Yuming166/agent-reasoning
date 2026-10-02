#!/usr/bin/env python3
"""Support-restricted re-evaluation of the sampled candidate ranker.

nc_ranker_samples_v2 draws negatives from historical top-2000 addresses but
keeps positives even when the next counterparty is outside that pool.  Those
out-of-support positives have g_rank=99999 and are therefore trivially
separable.  This audit retains only events whose observed positive is itself
in the top-2000 support, and rebuilds event-conditional rank/gate metrics.
"""
import glob, json, os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATS = ["g_rank", "g_cnt", "personal_cnt", "days_since", "bridge_paths", "bridge_signal"]
KEYS = ["snapshot_date", "u", "target_sequence_index"]
EVENT_BASE = ["candidate_n", "neg_n", "bridge_candidate_n", "bridge_share",
              "bridge_signal_sum", "bridge_signal_mean", "bridge_signal_max",
              "bridge_paths_sum", "best_neg_g_rank", "median_neg_g_rank"]
GATE_FEATS = EVENT_BASE + ["log_" + c for c in EVENT_BASE[:8]]
BUDGETS = (0.01, 0.05, 0.10, 0.20, 0.50, 1.00)
CHEAP, DELIB = 32, 96


def load_supported(workdir):
    parts, positives = [], []
    for path in sorted(glob.glob(os.path.join(workdir, "*.csv.gz"))):
        reader = pd.read_csv(path, chunksize=1_000_000)
        for chunk in reader:
            pos = chunk[chunk.label == 1][KEYS + ["g_rank"]]
            positives.append(pos)
    pos = pd.concat(positives, ignore_index=True)
    eligible = set(map(tuple, pos.loc[pos.g_rank <= 2000, KEYS].itertuples(index=False, name=None)))
    for path in sorted(glob.glob(os.path.join(workdir, "*.csv.gz"))):
        reader = pd.read_csv(path, chunksize=1_000_000)
        for chunk in reader:
            key = list(zip(chunk.snapshot_date, chunk.u, chunk.target_sequence_index))
            mask = pd.Series(key, index=chunk.index).isin(eligible)
            parts.append(chunk.loc[mask].copy())
    df = pd.concat(parts, ignore_index=True)
    for c in FEATS:
        df[c] = df[c].replace([np.inf, -np.inf], np.nan).fillna(0)
    return df, pos


def context(df):
    neg = df[df.label == 0]
    b = neg[neg.bridge_paths > 0]
    out = df.groupby(KEYS).candidate_n.size().reset_index(name='candidate_n') if False else None
    cn = df.groupby(KEYS).agg(candidate_n=('c','size')).reset_index()
    g = neg.groupby(KEYS).agg(neg_n=('c','size'), best_neg_g_rank=('g_rank','min'),
                              median_neg_g_rank=('g_rank','median')).reset_index()
    ba = b.groupby(KEYS).agg(bridge_candidate_n=('c','size'),
        bridge_signal_sum=('bridge_signal','sum'), bridge_signal_mean=('bridge_signal','mean'),
        bridge_signal_max=('bridge_signal','max'), bridge_paths_sum=('bridge_paths','sum')).reset_index()
    ev = cn.merge(g,on=KEYS,how='left').merge(ba,on=KEYS,how='left')
    for c in ['bridge_candidate_n','bridge_signal_sum','bridge_signal_mean','bridge_signal_max','bridge_paths_sum']:
        ev[c] = ev[c].fillna(0.0)
    ev['bridge_share'] = ev.bridge_candidate_n / ev.neg_n.clip(lower=1)
    for c in EVENT_BASE[:8]: ev['log_'+c] = np.log1p(ev[c])
    return ev


def rank_metrics(df, score):
    x = df[KEYS+['label',score]].sort_values(KEYS+[score], ascending=[True,True,True,False]).copy()
    x['rank'] = x.groupby(KEYS).cumcount()+1
    p = x[x.label==1]
    return {'n_events':int(len(p)), 'MRR':float((1/p['rank']).mean()),
            'R@1':float((p['rank']==1).mean()), 'R@5':float((p['rank']<=5).mean()),
            'R@10':float((p['rank']<=10).mean()), 'median_rank':float(p['rank'].median())}, p


def event_ranks(df, model, snapshot, score):
    x = df[df.snapshot_date==snapshot].copy(); x[score]=model.predict_proba(x[FEATS])[:,1]
    lm,_=rank_metrics(x,score); lm=lm
    lr=x.sort_values(KEYS+[score],ascending=[True,True,True,False]).copy(); lr['rank']=lr.groupby(KEYS).cumcount()+1
    lr=lr[lr.label==1][KEYS+['rank']].rename(columns={'rank':'learned_rank'})
    y=x.copy(); y['global_score']=-y.g_rank.astype(float)
    gr=y.sort_values(KEYS+['global_score'],ascending=[True,True,True,False]).copy(); gr['rank']=gr.groupby(KEYS).cumcount()+1
    gr=gr[gr.label==1][KEYS+['rank']].rename(columns={'rank':'global_rank'})
    gm,_=rank_metrics(y.assign(global_score=-y.g_rank.astype(float)),'global_score')
    return lr.merge(gr,on=KEYS), lm, gm


def fit_ranker(data):
    m=HistGradientBoostingClassifier(max_iter=300, learning_rate=.03, max_leaf_nodes=15,
        min_samples_leaf=50,l2_regularization=1.0,random_state=7)
    m.fit(data[FEATS],data.label); return m


def curve(ev):
    n=len(ev); cheap=(1/ev.global_rank).to_numpy(); dele=(1/ev.learned_rank).to_numpy(); gain=np.maximum(0,dele-cheap)
    o=np.argsort(-ev.gate_p.to_numpy(),kind='mergesort'); oo=np.argsort(-gain,kind='mergesort'); rows=[]
    for b in BUDGETS:
        k=max(1,int(round(b*n))); s=np.zeros(n,bool); s[o[:k]]=True; ss=np.zeros(n,bool); ss[oo[:k]]=True
        m=np.where(s,dele,cheap).mean(); om=np.where(ss,dele,cheap).mean()
        denom=k*DELIB+(n-k)*CHEAP
        rows.append({'budget_fraction':b,'selected_events':k,'learned_gate_MRR':float(m),
            'learned_gate_gain':float(m-cheap.mean()),'oracle_gate_MRR':float(om),
            'oracle_gate_gain':float(om-cheap.mean()),'random_expected_MRR':float(cheap.mean()+b*(dele.mean()-cheap.mean())),
            'delta_MRR_per_1000_token_units':float((m-cheap.mean())*1000/denom),
            'selected_actual_winner_share':float(ev.gate_target.to_numpy()[o[:k]].mean())})
    return pd.DataFrame(rows)


def main():
    import argparse, matplotlib.pyplot as plt
    ap=argparse.ArgumentParser(); ap.add_argument('--workdir',default='artifacts/ranker_samples'); ap.add_argument('--outdir',default='artifacts/nc_v1')
    args=ap.parse_args(); os.makedirs(args.outdir,exist_ok=True)
    df,pos=load_supported(args.workdir); ctx=context(df)
    tr=df[df.snapshot_date=='2022-06-01']; va=df[df.snapshot_date=='2022-07-01']; te=df[df.snapshot_date=='2022-08-01']
    june=fit_ranker(tr); frozen=fit_ranker(pd.concat([tr,va]))
    jrank,_,_=event_ranks(df,june,'2022-07-01','s'); arank,lm,gm=event_ranks(df,frozen,'2022-08-01','s')
    jev=ctx[ctx.snapshot_date=='2022-07-01'].merge(jrank,on=KEYS)
    ev=ctx[ctx.snapshot_date=='2022-08-01'].merge(arank,on=KEYS)
    jev['gate_target']=(jev.learned_rank<jev.global_rank).astype(int)
    ev['gate_target']=(ev.learned_rank<ev.global_rank).astype(int)
    gate=make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000,class_weight='balanced',C=.5,solver='liblinear'))
    gate.fit(jev[GATE_FEATS],jev.gate_target); ev['gate_p']=gate.predict_proba(ev[GATE_FEATS])[:,1]
    bc=curve(ev); oracle=float(np.maximum(1/ev.global_rank,1/ev.learned_rank).mean())
    support=pos.groupby('snapshot_date').agg(total=('g_rank','size'),in_top2000=('g_rank',lambda x:int((x<=2000).sum())))
    support['support_rate']=support.in_top2000/support.total
    res={'protocol':'positive must be in historical top-2000 support; sampled ~50-candidate pool',
         'positive_support_by_snapshot':support.reset_index().to_dict('records'),
         'rows_by_snapshot_supported':df.snapshot_date.value_counts().sort_index().to_dict(),
         'august_scorers_supported_pool':{'global_sampled_pool':gm,'learned_sampled_pool':lm,'oracle_best_sampled_pool':{'MRR':oracle}},
         'gate':{'july_events':int(len(jev)),'august_events':int(len(ev)),'base_rate_learned_wins':float(ev.gate_target.mean()),
                 'AUROC':float(roc_auc_score(ev.gate_target,ev.gate_p)),'AUPRC':float(average_precision_score(ev.gate_target,ev.gate_p))},
         'budget_curve':bc.to_dict('records')}
    json.dump(res,open(os.path.join(args.outdir,'supported_pool_v1.json'),'w'),indent=2)
    bc.to_csv(os.path.join(args.outdir,'gate_budget_supported_curve.csv'),index=False)
    ev.to_csv(os.path.join(args.outdir,'aug_supported_gate_events.csv'),index=False)
    plt.figure(figsize=(7,4.5)); plt.plot(bc.budget_fraction*100,bc.learned_gate_MRR,marker='o',label='learned gate'); plt.plot(bc.budget_fraction*100,bc.oracle_gate_MRR,marker='s',label='oracle'); plt.plot(bc.budget_fraction*100,bc.random_expected_MRR,marker='^',label='random'); plt.xlabel('deliberation budget (%)'); plt.ylabel('supported-pool MRR'); plt.grid(alpha=.3); plt.legend(); plt.tight_layout(); plt.savefig(os.path.join(args.outdir,'gate_budget_supported_curve.png'),dpi=160)
    print(json.dumps(res['august_scorers_supported_pool'],indent=2)); print(bc.to_string(index=False))
if __name__=='__main__': main()
