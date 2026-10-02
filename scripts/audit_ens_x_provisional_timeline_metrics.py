#!/usr/bin/env python3
"""Summarize existing timeline-pilot coverage for 231-frame candidates.

Offline only. Outputs descriptive *observed lower bounds* for provisional,
unadjudicated links. This script never promotes mappings or builds a shortlist.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('artifacts/ens_x_crosswalk')
PILOT = BASE / 'timeline_expansion_pilot_20260925'
CANDIDATES = BASE / 'expansion_decision_20260925/candidate_review_full_231.csv'

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def read_jsonl(p):
    with p.open(encoding='utf-8') as f:
        for n,line in enumerate(f,1):
            if line.strip():
                try: yield json.loads(line)
                except json.JSONDecodeError as e: raise ValueError(f'{p}:{n}: malformed JSON') from e
def read_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(p,rows,fields):
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def status_dedup_key(uid: str, tweet_id: str, is_repost: bool) -> tuple[str, str, bool]:
    """Deduplicate observations per timeline owner and kind, not by canonical post ID alone.

    FxEmbed repost rows carry the original post ID. That ID can also appear as an
    authored row when its author is in the queried cohort; those are distinct
    observations and the repost row must not suppress the authored post.
    """
    return (str(uid), str(tweet_id), bool(is_repost))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',type=Path,default=Path.cwd())
    ap.add_argument('--out-dir',type=Path,default=BASE/'state_audit_20260925')
    a=ap.parse_args(); root=a.project_root.resolve(); out=a.out_dir if a.out_dir.is_absolute() else root/a.out_dir
    summary=json.loads((root/PILOT/'summary.json').read_text(encoding='utf-8'))
    start=datetime.fromisoformat(summary['fixed_window_start_utc'].replace('Z','+00:00'))
    end=datetime.fromisoformat(summary['fixed_window_end_exclusive_utc'].replace('Z','+00:00'))
    queue=json.loads((root/PILOT/'pilot_queue.json').read_text(encoding='utf-8'))
    candidates=read_csv(root/CANDIDATES)
    candidate_by_id={r['x_user_id']:r for r in candidates}
    qids=[str(r['x_user_id']) for r in queue]
    if len(qids)!=len(set(qids)):raise ValueError('pilot queue has duplicate stable X IDs')
    if not set(qids)<=set(candidate_by_id):raise ValueError('pilot IDs outside the 231-candidate frame')
    for q in queue:
        if q.get('review_status')!='automatic_exact_match_requires_manual_audit':
            raise ValueError('unexpected pilot review status; refusing to characterize provisional queue')
    ids=set(qids)
    coverage_rows=list(read_jsonl(root/PILOT/'coverage.jsonl'))
    coverage={str(r['x_user_id']):r for r in coverage_rows}
    if len(coverage)!=len(coverage_rows) or set(coverage)!=ids:raise ValueError('coverage ledger does not exactly match pilot queue')
    counts=Counter(); months=defaultdict(Counter); first={};last={}; seen_posts=set(); owner_errors=0; out_of_window_statuses=0; out_of_window_edges=0
    for r in read_jsonl(root/PILOT/'normalized_observed_statuses.jsonl'):
        uid=str(r['queried_user_id']); tid=str(r['tweet_id'])
        if uid not in ids or str(r.get('timeline_owner_id_verified'))!=uid:owner_errors+=1;continue
        is_repost=bool(r.get('is_repost'))
        key=status_dedup_key(uid,tid,is_repost)
        if key in seen_posts:continue
        seen_posts.add(key)
        dt=datetime.fromisoformat(str(r['created_at_utc']).replace('Z','+00:00')).astimezone(timezone.utc)
        if not start<=dt<end:out_of_window_statuses+=1;continue
        month=dt.strftime('%Y-%m')
        if is_repost:
            counts[(uid,'untimed_repost_observation')]+=1
            continue
        if str(r.get('source_author_id'))!=uid:owner_errors+=1;continue
        counts[(uid,'authored_post')]+=1
        if str(r.get('authored_text') or '').strip():counts[(uid,'nonempty_authored_text')]+=1
        months[uid][month]+=1
        iso=dt.isoformat()
        first[uid]=min(first.get(uid,iso),iso);last[uid]=max(last.get(uid,iso),iso)
    edge_counts=Counter(); edge_months=defaultdict(Counter); edge_keys=set(); internal_keys=set(); external_neighbors=defaultdict(set); internal_incident=set()
    edge_path=root/PILOT/'provisional_x_interaction_edges_temporal.csv'
    for e in read_csv(edge_path):
        src=str(e['source_x_user_id']);dst=str(e['target_x_user_id']); typ=e['event_type']; dt=datetime.fromisoformat(e['created_at_utc'].replace('Z','+00:00')).astimezone(timezone.utc)
        if src not in ids:raise ValueError('edge source outside pilot IDs')
        if not start<=dt<end:out_of_window_edges+=1;continue
        key=(src,str(e['source_post_id']),dst,typ)
        if key in edge_keys:continue
        edge_keys.add(key);edge_counts[(src,'out_edges')]+=1;edge_months[src][dt.strftime('%Y-%m')]+=1
        if dst in ids:
            internal_keys.add(key);internal_incident.update((src,dst))
        else:external_neighbors[src].add(dst)
    rows=[]
    for q in queue:
        uid=str(q['x_user_id']); c=coverage[uid]
        authored=counts[(uid,'authored_post')]; nonempty=counts[(uid,'nonempty_authored_text')]
        rows.append({'address':q['address'],'x_user_id':uid,'handle':q.get('handle_at_profile_audit',''),
          'review_status':'automatic_exact_match_requires_manual_audit','crosswalk_status':'candidate_unconfirmed_not_eligible_for_shortlist',
          'events_2026':q.get('events_2026',''),'authored_posts_observed_in_window':authored,
          'nonempty_authored_posts_observed_in_window':nonempty,'authored_active_months':sum(1 for n in months[uid].values() if n),
          'first_authored_post_observed_utc':first.get(uid,''),'last_authored_post_observed_utc':last.get(uid,''),
          'timestamped_interaction_edges_observed':edge_counts[(uid,'out_edges')],
          'unique_external_interaction_neighbors_observed':len(external_neighbors[uid]),
          'timeline_pages':c.get('pages',''),'timeline_statuses':c.get('statuses',''),
          'stop_reason':c.get('stop_reason',''),'endpoint_cursor_exhausted':str(c.get('stop_reason')=='cursor_exhausted').lower(),
          'window_coverage_complete_claim':'no','coverage_semantics':'observed_lower_bound_page_capped_or_endpoint_exhausted_not_history_complete'})
    mrows=[]
    for q in queue:
        uid=str(q['x_user_id'])
        for month in sorted(set(months[uid])|set(edge_months[uid])):
            mrows.append({'x_user_id':uid,'month_utc':month,'authored_posts_observed':months[uid][month],
                          'timestamped_interaction_edges_observed':edge_months[uid][month],
                          'crosswalk_status':'candidate_unconfirmed'})
    out.mkdir(parents=True,exist_ok=True)
    per=out/'provisional_50_timeline_lower_bound_metrics_20260925.csv'
    mon=out/'provisional_50_timeline_monthly_metrics_20260925.csv'
    write_csv(per,rows,list(rows[0]));write_csv(mon,mrows,['x_user_id','month_utc','authored_posts_observed','timestamped_interaction_edges_observed','crosswalk_status'])
    totals={k:sum(r[k] for r in rows) for k in ['authored_posts_observed_in_window','nonempty_authored_posts_observed_in_window','timestamped_interaction_edges_observed']}
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'offline_existing_artifacts_only_no_network_no_collection',
      'candidate_frame_rows':len(candidates),'pilot_candidate_rows':len(queue),'pilot_ids_subset_of_candidate_frame':True,
      'crosswalk_adjudication':'all 50 automatic exact-match candidates; none treated as confirmed',
      'window_start_inclusive_utc':summary['fixed_window_start_utc'],'window_end_exclusive_utc':summary['fixed_window_end_exclusive_utc'],
      'totals_observed_lower_bounds':totals,'monthly_observed_authored_posts':{k:sum(v[k] for v in months.values()) for k in sorted({m for x in months.values() for m in x})},
      'coverage_stop_reasons':dict(Counter(str(r.get('stop_reason')) for r in coverage_rows)),
      'mean_posts_per_account_observed':round(totals['authored_posts_observed_in_window']/len(queue),3),
      'pilot_induced_social_graph':{'candidate_nodes':len(ids),'candidate_to_candidate_edges':len(internal_keys),'candidate_nodes_incident_to_candidate_to_candidate_edges':len(internal_incident),'observed_external_neighbors_unique_by_source_sum':sum(len(v) for v in external_neighbors.values())},
      'integrity':{'coverage_accounts':len(coverage),'stable_id_owner_errors':owner_errors,'out_of_window_deduplicated_status_observations':out_of_window_statuses,'out_of_window_interaction_edges':out_of_window_edges,'deduplicated_timeline_status_observations':len(seen_posts),'metric_rows':len(rows),'monthly_rows':len(mrows)},
      'interpretation':'These are observed lower bounds from an existing capped pilot, not completeness estimates, confirmation evidence, or a shortlist. The 50 candidate links must be independently adjudicated before any wallet-X graph admission. No candidate-to-candidate social edge was observed in this pilot; edges primarily point to external X IDs without wallet crosswalks.',
      'inputs':{str(p):sha(root/p) for p in [PILOT/'pilot_queue.json',PILOT/'coverage.jsonl',PILOT/'normalized_observed_statuses.jsonl',PILOT/'provisional_x_interaction_edges_temporal.csv',PILOT/'summary.json',CANDIDATES]},
      'outputs':{'per_account_csv':per.name,'monthly_csv':mon.name}}
    rp=out/'provisional_50_timeline_metrics_audit_20260925.json';rp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(rp),'totals':totals,'monthly':report['monthly_observed_authored_posts'],'stop_reasons':report['coverage_stop_reasons'],'induced_graph':report['pilot_induced_social_graph'],'integrity':report['integrity']},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
