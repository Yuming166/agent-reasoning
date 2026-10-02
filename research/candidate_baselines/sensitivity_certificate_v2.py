"""Physical-event deletion with frozen pools/model/normalization and rebuilt history."""
from pathlib import Path
from collections import Counter
import argparse, copy, gc, hashlib, json, math, pickle, time
import numpy as np
import pandas as pd
import torch
from certificate_history_v2 import History, COLS
from certificate_v2 import stable_id, BASE_NAMES, CERT_NAMES, EXTRA_NAMES
from certificate_models_v2 import Scorer
from train_certificate_v2 import prepare, collate, dump

MONTHS = ['2022-03', '2022-04', '2022-05', '2022-06']
CTX_NAMES = ['log_out_role_rows', 'log_unique_out_peers', 'last_out_decay', 'out_entropy', 'explore', 'log_in_role_rows']

def role_context(rows, cutoff, deleted_ids=()):
    q = rows[~rows.event_id.isin(deleted_ids)]
    outgoing = q[q.direction == 'outgoing']; incoming = q[q.direction == 'incoming']
    freq = outgoing.counterparty_address.value_counts(); n = int(freq.sum()); k = len(freq)
    ent = float(-np.sum(freq.to_numpy()/n * np.log(freq.to_numpy()/n)) / math.log(k)) if k > 1 else 0.
    last = math.exp(-(pd.Timestamp(cutoff, tz='UTC') - outgoing.block_timestamp.max()).total_seconds()/(90*86400)) if n else 0.
    return np.array([math.log1p(n), math.log1p(k), last, ent, k/max(1,n), math.log1p(len(incoming))], np.float32)

def read_wallet_roles(wallets, cutoff):
    src = Path('artifacts/offline_chain_events_v1_20260929_full')
    frames = []
    for month in MONTHS:
        q = pd.read_parquet(src/(month+'.parquet'), columns=COLS+['target_address','counterparty_address','direction'],
                            filters=[('target_address','in',list(wallets))])
        for k in COLS:
            if k not in ('block_timestamp','block_number','transaction_index','event_index','receipt_status'):
                q[k] = q[k].fillna('').astype(str)
        # The extractor normalizes role columns before building the legacy
        # index.  Arrow preserves null counterparty values in this narrow
        # wallet read. value_counts drops nulls, whereas the extractor counts
        # the normalized empty string, so match its role semantics exactly.
        for k in ('target_address', 'counterparty_address', 'direction'):
            q[k] = q[k].fillna('').astype(str)
        for k in ('block_number','transaction_index','event_index','receipt_status'):
            q[k] = pd.to_numeric(q[k],errors='coerce').fillna(-1).astype('int64')
        q['block_timestamp'] = pd.to_datetime(q.block_timestamp, utc=True)
        q = q[q.block_timestamp < pd.Timestamp(cutoff,tz='UTC')].copy()
        q['event_id'] = [stable_id(r) for r in q.to_dict('records')]
        frames.append(q)
    return pd.concat(frames,ignore_index=True)

@torch.no_grad()
def score_case(model, case, stats, device):
    r = prepare([copy.deepcopy(case)], stats)[0]
    s,g,d,b,act,ow = model(collate([r], device, 'chain_all', 0))
    score = s[0].cpu().numpy(); order = np.argsort(-score,kind='stable')
    rank = np.empty(len(score),np.int32); rank[order]=np.arange(1,len(score)+1)
    return dict(score=score, rank=rank, gate=g[0].cpu().numpy(), correction=d[0].cpu().numpy(),
                base_score=b[0].cpu().numpy(), activity_p=float(torch.sigmoid(act)[0]),
                open_world_p=float(torch.sigmoid(ow)[0]), top1=case['pool'][order[0]])

def point(scores, case, candidate):
    i=case['pool'].index(candidate)
    return {k:float(scores[k][i]) for k in ['score','gate','correction','base_score']} | dict(
        rank=int(scores['rank'][i]), valid=bool(case['C'][i,0]),
        target_rank=int(scores['rank'][case['y_idx']]) if case['y_idx']>=0 else -1,
        top1=scores['top1'],activity_p=scores['activity_p'],open_world_p=scores['open_world_p'])

def feature_changes(before, after, candidate):
    i=before['pool'].index(candidate); result={}
    for k,names in [('B',BASE_NAMES),('C',CERT_NAMES),('E',EXTRA_NAMES),('ctx',CTX_NAMES)]:
        a,b=before[k],after[k]; diff=np.abs(a-b)
        aa,bb=(a,b) if k=='ctx' else (a[i],b[i])
        result[k]=dict(changed_entries=int((diff>1e-7).sum()), max_absolute_change=float(diff.max()),
                       focus={name:dict(before=float(x),after=float(y),delta=float(y-x))
                              for name,x,y in zip(names,aa,bb) if abs(float(y-x))>1e-7})
    return result

def choose_cases(dev, predictions):
    byid={r['case_id']:r for r in dev}; eligible=predictions[predictions.active.astype(bool)].sort_values('case_id')
    success=eligible[(eligible['rank']>0)&(eligible['rank']<=5)]
    failure=eligible[(eligible['rank']<=0)|(eligible['rank']>5)]
    chosen=[]
    # Fixed diagnostic quota, not a performance estimate; target proof when available.
    for label,part in [('success',success),('failure',failure)]:
        for row in part.sort_values(['target_valid','case_id'],ascending=[False,True]).itertuples():
            r=byid[row.case_id]
            if r['C'][:,0].sum(): chosen.append((label,r))
            if sum(x[0]==label for x in chosen)==3:break
    for row in eligible.itertuples():
        if len(chosen)>=6:break
        if row.case_id not in {r['case_id'] for _,r in chosen} and byid[row.case_id]['C'][:,0].sum():
            chosen.append(('success' if 0<row.rank<=5 else 'failure',byid[row.case_id]))
    assert len(chosen)==6 and len({label for label,_ in chosen})==2
    return chosen

def matching_random(h, indices, rng, focus_wallet, focus_candidate):
    forbidden=set(indices); chosen=[]; matches=[]
    family=h.a['event_family']; ts=h.a['timestamp']; week=ts//(7*86400)
    # Family+week is mandatory when available; prefer matching focus actor involvement.
    for i in indices:
        involved_wallet=focus_wallet in (h.a['from_address'][i],h.a['to_address'][i])
        involved_candidate=focus_candidate in (h.a['from_address'][i],h.a['to_address'][i])
        eligible=(family==family[i]) & (week==week[i])
        actor_mask=((h.a['from_address']==focus_wallet)|(h.a['to_address']==focus_wallet)) == involved_wallet
        actor_mask &= (((h.a['from_address']==focus_candidate)|(h.a['to_address']==focus_candidate)) == involved_candidate)
        options=np.flatnonzero(eligible & actor_mask)
        options=np.array([int(j) for j in options if j not in forbidden],dtype=np.int64)
        method='family_week_actor_involvement'
        if not len(options):
            options=np.array([int(j) for j in np.flatnonzero(eligible) if j not in forbidden],dtype=np.int64)
            method='family_week'
        if not len(options):
            options=np.array([int(j) for j in np.flatnonzero(family==family[i]) if j not in forbidden],dtype=np.int64)
            distance=np.abs(ts[options]-ts[i]); options=options[distance==distance.min()]
            method='family_nearest_time_fallback'
        assert len(options)
        j=int(rng.choice(options)); forbidden.add(j); chosen.append(j)
        matches.append(dict(evidence_event_id=h.compact(i)['event_id'], control_event_id=h.compact(j)['event_id'],
                            method=method, same_family=bool(family[j]==family[i]), same_week=bool(week[j]==week[i]),
                            abs_time_delta_seconds=int(abs(ts[j]-ts[i]))))
    assert len(chosen)==len(indices) and not set(chosen)&set(indices)
    return chosen,matches

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--run',required=True); ap.add_argument('--device',default='cpu'); a=ap.parse_args()
    root=Path(a.run); out=root/'sensitivity'; out.mkdir(exist_ok=True)
    ck=root/'models'/'chain_all'/'seed0'; assert (ck/'complete.json').exists()
    start=time.time(); torch.set_num_threads(4)
    stats=json.loads((root/'normalization.json').read_text())
    checkpoint=torch.load(ck/'model.pt',map_location=a.device,weights_only=False)
    model=Scorer('chain_all').to(a.device); model.load_state_dict(checkpoint['model']); model.eval()
    with (root/'shards'/'2022-07-01.pkl').open('rb') as f: dev=pickle.load(f)
    selected=choose_cases(dev,pd.read_csv(ck/'case_predictions.csv'))
    ledger=pd.read_parquet(root/'canonical_ledger.parquet')
    baseline=History(ledger,'2022-07-01')
    roles=read_wallet_roles([r['wallet'] for _,r in selected],'2022-07-01')
    dump(out/'protocol.json',dict(model='chain_all',seed=0,cases=6,random_repeats=3,
         selection='up to three R@5 successes and three failures; certified target first, then case ID',
         deletions='all physical event IDs in the focal candidate proofs, not complete transactions',
         match='family/week, prefer same wallet and candidate involvement; recorded fallbacks',
         frozen=['candidate pool','checkpoint','normalization'],recomputed=['physical history','proofs','B','C','E','ctx'],
         unused_unchanged_inputs=['X','gm','seq','cand_bucket'],claim='controlled evidence sensitivity, not causal inference'))
    records=[]; flat=[]
    for position,(label,r) in enumerate(selected):
        casefile=out/(r['case_id'].replace('/','_')+'.json')
        if casefile.exists():
            saved=json.loads(casefile.read_text()); records.append(saved); flat.extend(saved['flat_rows']);continue
        ps=baseline.proofs(r); B,C,E=baseline.features(r,ps)
        wallet_roles=roles[roles.target_address==r['wallet']]
        ctx=role_context(wallet_roles,r['cutoff'])
        errors={k:float(np.abs(r[k]-v).max()) for k,v in [('B',B),('C',C),('E',E),('ctx',ctx)]}
        assert max(errors.values())<1e-5, ('baseline feature mismatch',r['case_id'],errors)
        orig=score_case(model,r,stats,a.device)
        prediction=pd.read_parquet(ck/'predictions.parquet',filters=[('case_id','==',r['case_id'])]).sort_values('pool_index')
        assert prediction.candidate.tolist()==r['pool']
        score_error=float(np.abs(prediction.score.to_numpy()-orig['score']).max())
        assert score_error<1e-4, ('baseline score mismatch',score_error)
        if r['y_idx']>=0 and r['C'][r['y_idx'],0]>0:
            focus=r['target']; reason='supported target with certificate'
        else:
            certified=np.flatnonzero(r['C'][:,0]>0)
            focus=r['pool'][certified[np.argmax(orig['score'][certified])]]
            reason='highest scored certified candidate; target has no certificate or is unsupported'
        proofs=ps[focus]
        evidence_ids=sorted({e['event_id'] for p in proofs for e in p['events']})
        ids=[int(baseline.event_map[eid]) for eid in evidence_ids]
        assert len(ids)==len(evidence_ids)>0
        rng=np.random.default_rng(20261001+position)
        changes=[('evidence',ids,[])]
        for repeat in range(3):
            ix,matched=matching_random(baseline,ids,rng,r['wallet'],focus)
            changes.append((f'random{repeat}',ix,matched))
        record=dict(case_id=r['case_id'],wallet=r['wallet'],target=r['target'],cutoff=r['cutoff'],
                    outcome=label,focus=focus,focus_reason=reason,pool_size=len(r['pool']),
                    baseline=point(orig,r,focus),baseline_feature_max_errors=errors,
                    baseline_saved_score_max_error=score_error,proofs=proofs,
                    candidate_pool_sha256=hashlib.sha256('\n'.join(r['pool']).encode()).hexdigest(),interventions=[])
        local_rows=[]
        for treatment,delete_indices,matching in changes:
            deleted=[baseline.compact(i) for i in delete_indices]
            deleted_eids={e['event_id'] for e in deleted}
            physical_rows=[int(baseline.source_indices[i]) for i in delete_indices]
            h=History(ledger,r['cutoff'],deleted=physical_rows)
            pnew=h.proofs(r); bnew,cnew,enew=h.features(r,pnew)
            # Deleting physical events also removes every corresponding directional role row.
            ctxnew=role_context(wallet_roles,r['cutoff'],deleted_eids)
            changed={**r,'B':bnew,'C':cnew,'E':enew,'ctx':ctxnew}
            scores=score_case(model,changed,stats,a.device); before=record['baseline']; after=point(scores,changed,focus)
            assert not deleted_eids & {e['event_id'] for pp in pnew.values() for p in pp for e in p['events']}
            changes_summary=feature_changes(r,changed,focus)
            intervention=dict(treatment=treatment,deleted_physical_rows=physical_rows,deleted_events=deleted,
                              match_records=matching,after=after,feature_changes=changes_summary,
                              remaining_focus_proofs=pnew.get(focus,[]),
                              focus_score_delta=after['score']-before['score'],
                              focus_rank_delta=after['rank']-before['rank'],
                              history_rows_before=len(baseline.df),history_rows_after=len(h.df),
                              deleted_wallet_role_rows=int(wallet_roles.event_id.isin(deleted_eids).sum()))
            assert len(baseline.df)-len(h.df)==len(delete_indices)
            record['interventions'].append(intervention)
            local_rows.append(dict(case_id=r['case_id'],outcome=label,focus_is_target=focus==r['target'],
                              treatment=treatment,deleted_events=len(deleted),rank_before=before['rank'],rank_after=after['rank'],
                              target_rank_before=before['target_rank'],target_rank_after=after['target_rank'],
                              score_delta=intervention['focus_score_delta'],rank_delta=intervention['focus_rank_delta'],
                              gate_before=before['gate'],gate_after=after['gate'],valid_before=before['valid'],valid_after=after['valid'],
                              B_changed=changes_summary['B']['changed_entries'],C_changed=changes_summary['C']['changed_entries'],
                              E_changed=changes_summary['E']['changed_entries'],ctx_changed=changes_summary['ctx']['changed_entries']))
            del h,pnew,bnew,cnew,enew,changed;gc.collect()
            print(json.dumps(dict(case=position+1,treatment=treatment,rank_before=before['rank'],rank_after=after['rank'],elapsed=time.time()-start)),flush=True)
        record['flat_rows']=local_rows; dump(casefile,record);records.append(record);flat.extend(local_rows)
    table=pd.DataFrame(flat);table.to_csv(out/'case_effects.csv',index=False)
    methods=Counter(m['method'] for r in records for t in r['interventions'] for m in t['match_records'])
    summ=dict(cases=len(records),random_controls=int(table.treatment.str.startswith('random').sum()),
              successes=sum(r['outcome']=='success' for r in records),failures=sum(r['outcome']=='failure' for r in records),
              matching_methods=dict(methods),seconds=time.time()-start,
              effects={str(k):dict(mean_score_delta=float(v.score_delta.mean()),mean_rank_delta=float(v.rank_delta.mean()),
                       validity_removed=int((~v.valid_after).sum())) for k,v in table.groupby(table.treatment=='evidence')})
    dump(out/'summary.json',summ)
    lines=['# Controlled evidence sensitivity','',
           'Frozen chain_all seed 0, six dev diagnostic cases and three matched random event deletions per case. '
           'Actual physical events are removed and histories, certificates, B/C/E and wallet context are rebuilt. '
           'Other candidate inputs are unused by this model. Selection balances successes/failures and is not a representative effect estimate.', '',
           '| Case | Outcome | Focus | Original rank | Evidence-deleted rank | Random ranks |',
           '|---|---|---|---:|---:|---|']
    for r in records:
        ranks=[t['after']['rank'] for t in r['interventions']]
        lines.append(f"| {r['case_id']} | {r['outcome']} | {'target' if r['focus']==r['target'] else 'certified prediction'} | {r['baseline']['rank']} | {ranks[0]} | {ranks[1:]} |")
    lines += ['', 'Deletion can uncover replacement proofs under the frozen caps. A surviving validity flag does not mean the deletion was skipped. '
              'Scores and ranks can move in either direction because base, certificate, chain and global features all change. '
              'Random controls use identical deletion counts with family/time matching; actor-matching fallbacks are recorded. '
              'This is sensitivity to the observed evidence, not an intervention on the blockchain or a causal estimate.','']
    for r in records:
        lines += [f"## {r['case_id']}",'',f"Wallet: {r['wallet']}; target: {r['target']}; focus: {r['focus']}.",
                  f"Focus rule: {r['focus_reason']}. Before deletion: rank {r['baseline']['rank']}, gate {r['baseline']['gate']:.4f}.",'',
                  'Proofs and immutable event IDs:','']
        for p in r['proofs']:
            ev=p['events']
            lines.append(f"- {p['kind']}: {ev[0]['event_id']} ({ev[0]['transaction_hash']}, {ev[0]['block_timestamp']}) → {ev[1]['event_id']} ({ev[1]['transaction_hash']}, {ev[1]['block_timestamp']}).")
        lines += ['',f"Full endpoints, directions, chain positions, deletion controls and all feature/score changes are in {r['case_id'].replace('/','_')}.json.",'']
    (out/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(summ),flush=True)

if __name__=='__main__':main()
