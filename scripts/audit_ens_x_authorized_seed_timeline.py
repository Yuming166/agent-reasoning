#!/usr/bin/env python3
"""Offline audit of the bounded FxEmbed timeline batch for 12 confirmed seed IDs.

No network/RPC/BigQuery calls. Uses only persisted manifests, ledgers, coverage,
raw hashes, and normalized timeline rows. Candidate IDs are never read or promoted.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path('artifacts/ens_x_crosswalk')
RUN = BASE / 'fx_authorized_batch_20260924T172410Z'
CONT = RUN / 'continuation_20260924_fixed_window'
SEED = BASE / 'two_graph_seed_20260925/crosswalk_confirmed_unique.csv'
KINDS = ('original', 'reply', 'quote', 'repost')


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def read_csv(path: Path) -> list[dict[str,str]]:
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))
def read_jsonl(path: Path) -> list[dict[str,Any]]:
    rows=[]
    with path.open(encoding='utf-8') as f:
        for n,line in enumerate(f,1):
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError as e: raise ValueError(f'{path}:{n}: invalid JSON') from e
    return rows
def dt(value: str) -> datetime:
    x=datetime.fromisoformat(value.replace('Z','+00:00'))
    if x.tzinfo is None: raise ValueError('timestamp must be timezone-aware')
    return x.astimezone(timezone.utc)
def write_csv(path: Path, rows: list[dict], fields: list[str] | None=None) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None: fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def analyze_tweets(ids: set[str], rows: list[dict[str,Any]], start: datetime, end: datetime) -> dict[str,Any]:
    """Validate, deduplicate, classify posts, and induce verified-ID quote/reply edges."""
    by_id=defaultdict(Counter); monthly=defaultdict(Counter); earliest={}; latest={}
    dedup={}; bad_owner=0; out_window=0; missing_time=0; invalid_kind=Counter()
    # First pass: only timeline-owner-verified in-window rows can contribute.
    for r in rows:
        owner=str(r.get('queried_user_id') or '')
        if owner not in ids or str(r.get('timeline_owner_id_verified') or '') != owner:
            bad_owner += 1; continue
        repost=bool(r.get('is_repost'))
        if not repost and str(r.get('source_author_id') or '') != owner:
            bad_owner += 1; continue
        raw_dt=r.get('created_at_utc')
        if not raw_dt: missing_time += 1; continue
        when=dt(str(raw_dt))
        if not start <= when < end: out_window += 1; continue
        kind=str(r.get('post_kind') or ('repost' if repost else ''))
        if kind not in KINDS: invalid_kind[kind or '<blank>'] += 1; continue
        key=(owner,str(r.get('tweet_id') or ''),kind)
        if not key[1]: invalid_kind['<missing_tweet_id>'] += 1; continue
        dedup.setdefault(key,(r,when,kind))
    authored_tweets={}
    for (owner,tid,kind),(r,when,_) in dedup.items():
        by_id[owner][f'{kind}_observations'] += 1
        by_id[owner]['all_unique_timeline_items'] += 1
        if kind=='repost':
            # Reposts have source-post time, not repost-action time. Never treat
            # them as authored text, time-indexed interaction, or an edge.
            continue
        by_id[owner]['authored_posts'] += 1
        if str(r.get('authored_text') or '').strip(): by_id[owner]['nonempty_authored_text_posts'] += 1
        month=when.strftime('%Y-%m')
        monthly[(owner,month)][kind] += 1
        authored_tweets[tid]=owner
        stamp=when.isoformat().replace('+00:00','Z')
        earliest[owner]=min(earliest.get(owner,stamp),stamp)
        latest[owner]=max(latest.get(owner,stamp),stamp)
    edges=Counter(); edge_months=defaultdict(Counter); edge_records=[]
    for (owner,tid,kind),(r,when,_) in dedup.items():
        if kind=='repost': continue
        target=''; relation=''
        if kind=='quote':
            target=str(r.get('quoted_author_id') or '')
            relation='quote'
        elif kind=='reply':
            reply_tid=str(r.get('replying_to_tweet_id') or '')
            target=authored_tweets.get(reply_tid,'')
            relation='reply_resolved_in_local_confirmed_corpus'
        if target and target in ids and target != owner:
            month=when.strftime('%Y-%m')
            edges[(owner,target,relation)] += 1
            edge_months[(owner,target,relation)][month] += 1
            edge_records.append({'source_x_user_id':owner,'target_x_user_id':target,'event_type':relation,
                                 'created_at_utc':when.isoformat().replace('+00:00','Z'),'tweet_id':tid,
                                 'crosswalk_scope':'12_confirmed_seed_ids_only'})
    return {'counts':by_id,'monthly':monthly,'earliest':earliest,'latest':latest,'edges':edges,
            'edge_months':edge_months,'edge_records':edge_records,'bad_owner':bad_owner,
            'out_window':out_window,'missing_time':missing_time,'invalid_kind':invalid_kind,
            'deduped_rows':len(dedup),'input_rows':len(rows)}

def audit_request_logs(project: Path) -> dict[str,Any]:
    logs=[(RUN/'requests.jsonl', project/RUN), (CONT/'continuation_requests.jsonl', project/CONT)]
    rows=[]
    for log_path, raw_base in logs:
        rows.extend((line, raw_base) for line in (project/log_path).read_text(encoding='utf-8').splitlines())
    parsed=[]
    for i,(line, raw_base) in enumerate(rows,1):
        if not line.strip(): continue
        try:
            rec=json.loads(line); rec['_raw_base']=str(raw_base); parsed.append(rec)
        except json.JSONDecodeError as e: raise ValueError(f'request ledger row {i} malformed') from e
    ids_seen=Counter(str(r.get('request_id') or '') for r in parsed)
    raw_missing=[]; raw_hash_mismatch=[]
    for r in parsed:
        rel=r.get('raw_file')
        if not rel: raw_missing.append(str(r.get('request_id'))); continue
        p=Path(r['_raw_base'])/rel
        if not p.is_file(): raw_missing.append(str(r.get('request_id'))); continue
        expected=r.get('response_sha256')
        if expected and sha256(p)!=expected: raw_hash_mismatch.append(str(r.get('request_id')))
    timelines=defaultdict(list)
    for r in parsed:
        if str(r.get('kind'))=='statuses' and int(r.get('http_status') or 0)==200 and not r.get('error'):
            timelines[str(r.get('handle') or '')].append(r)
    cursor_chain={}
    for handle, seq in timelines.items():
        seq.sort(key=lambda r:(dt(str(r['requested_at_utc'])),int(r.get('page') or 0)))
        breaks=[]; page_gaps=[]
        for prev,nxt in zip(seq,seq[1:]):
            pp=int(prev.get('page') or 0); np=int(nxt.get('page') or 0)
            if np==pp: continue  # successful retry/repeated page is not a pagination step
            if np!=pp+1: page_gaps.append({'from_page':pp,'to_page':np})
            if str(nxt.get('cursor_in') or '') != str(prev.get('cursor_out') or ''):
                breaks.append({'from_page':pp,'to_page':np,'cursor_in_matches_previous_out':False})
        cursor_chain[handle]={'successful_timeline_pages':len(seq),'page_number_gaps':page_gaps,
                              'cursor_chain_breaks':breaks,
                              'first_page':int(seq[0].get('page') or 0) if seq else None,
                              'last_page':int(seq[-1].get('page') or 0) if seq else None}
    return {'ledger_rows':len(parsed),'request_ids_unique':all(n==1 for k,n in ids_seen.items() if k),
            'blank_request_ids':ids_seen.get('',0),'http_status_counts':dict(Counter(str(r.get('http_status')) for r in parsed)),
            'api_code_counts':dict(Counter(str(r.get('api_code')) for r in parsed)),
            'error_rows':sum(bool(r.get('error')) or int(r.get('http_status') or 0)>=400 for r in parsed),
            'raw_body_missing_or_unreferenced_count':len(raw_missing),'raw_body_hash_mismatch_count':len(raw_hash_mismatch),
            'retry_attempt_rows':sum(int(r.get('attempt') or 1)>1 for r in parsed),
            'cursor_input_rows':sum(bool(r.get('cursor_in')) for r in parsed),
            'cursor_output_rows':sum(bool(r.get('cursor_out')) for r in parsed),
            'page_rows':sum(str(r.get('kind'))=='statuses' for r in parsed),
            'successful_timeline_pages':sum(len(v) for v in timelines.values()),
            'cursor_chain_break_count':sum(len(v['cursor_chain_breaks']) for v in cursor_chain.values()),
            'page_number_gap_count':sum(len(v['page_number_gaps']) for v in cursor_chain.values()),
            'cursor_chain_by_handle':dict(sorted(cursor_chain.items())),
            'request_ids_with_duplicate_rows':sum(1 for k,n in ids_seen.items() if k and n>1)}

def build(project: Path, out: Path) -> dict[str,Any]:
    run=project/RUN; cont=project/CONT; seed=project/SEED
    manifest=read_json(run/'run_manifest.json'); cmanifest=read_json(cont/'continuation_manifest.json')
    sample=read_csv(run/'sample_manifest.csv'); crosswalk=read_csv(seed)
    ids={str(r['x_user_id']) for r in sample}; seed_ids={str(r['x_user_id']) for r in crosswalk}
    if len(ids)!=12 or len(sample)!=12 or not ids<=seed_ids: raise ValueError('allowlist is not exactly 12 confirmed seed IDs')
    if int(manifest['account_count'])!=12 or int(cmanifest['account_count'])!=12 or int(cmanifest['new_account_ids_added'])!=0:
        raise ValueError('run manifest allowlist expansion invariant failed')
    if any(r.get('temporal_link_status')!='snapshot_only_not_as_of_validated' for r in crosswalk if str(r['x_user_id']) in ids):
        raise ValueError('unexpected temporal crosswalk status')
    start=dt(manifest['target_start_inclusive_utc']); end=dt(manifest['target_end_exclusive_utc'])
    tweets=read_jsonl(cont/'combined_tweets_in_window.jsonl')
    result=analyze_tweets(ids,tweets,start,end)
    coverage=read_csv(cont/'combined_coverage.csv')
    if {str(r['x_user_id']) for r in coverage} != ids or len(coverage)!=12: raise ValueError('coverage does not match fixed allowlist')
    per=[]; monthly=[]
    for c in coverage:
        uid=str(c['x_user_id']); counts=result['counts'][uid]
        row={'x_user_id':uid,'handle':c['handle'],'authored_original_posts':counts['original_observations'],
             'authored_reply_posts':counts['reply_observations'],'authored_quote_posts':counts['quote_observations'],
             'repost_observations_excluded_from_authored_text':counts['repost_observations'],
             'authored_posts_total':counts['authored_posts'],'nonempty_authored_text_posts':counts['nonempty_authored_text_posts'],
             'earliest_visible_authored_post_utc':result['earliest'].get(uid,''),'latest_visible_authored_post_utc':result['latest'].get(uid,''),
             'valid_timeline_pages':c['valid_timeline_pages'],'unique_tweets_in_window_reported':c['unique_tweets_in_window'],
             'reached_start_boundary':c['reached_start_boundary'],'pagination_to_target_boundary':c['pagination_to_target_boundary'],
             'timeline_exhausted_no_cursor':c['timeline_exhausted_no_cursor'],'pagination_order_nonincreasing':c['pagination_order_nonincreasing'],
             'stop_reason':c['stop_reason'],'truncated_or_uncertain':c['truncated_or_uncertain'],
             'coverage_interpretation':'observed_only; not complete-history claim'}
        per.append(row)
    month_names=sorted({month for (_,month) in result['monthly']})
    for uid in sorted(ids):
        for month in month_names:
            v=result['monthly'].get((uid,month),Counter())
            if not sum(v.values()): continue
            monthly.append({'x_user_id':uid,'month_utc':month,'original_posts':v['original'],
                            'reply_posts':v['reply'],'quote_posts':v['quote'],'authored_posts_total':sum(v.values())})
    edge_rows=result['edge_records']
    edgepair_months=defaultdict(set)
    for (s,t,rel),months in result['edge_months'].items(): edgepair_months[(s,t,rel)]=set(months)
    summaries=read_json(cont/'combined_summary.json')
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'offline_authorized_confirmed_seed_timeline_audit',
      'network_requests':0,'paid_queries_usd':0,'candidate_ids_read_or_promoted':False,
      'scope':{'confirmed_seed_wallet_x_pairs':len(ids),'seed_crosswalk_temporal_status':'snapshot_only_not_as_of_validated',
               'target_start_inclusive_utc':start.isoformat(),'target_end_exclusive_utc':end.isoformat()},
      'reported_collector_summary':summaries,
      'recomputed_timeline':{'input_rows':result['input_rows'],'deduplicated_verified_in_window_rows':result['deduped_rows'],
         'stable_id_owner_errors':result['bad_owner'],'out_of_window_rows':result['out_window'],'missing_timestamp_rows':result['missing_time'],
         'invalid_kind_counts':dict(result['invalid_kind']),'post_kind_counts':{k:sum(r[f'authored_{k}_posts'] if k!='repost' else r['repost_observations_excluded_from_authored_text'] for r in per) for k in KINDS},
         'authored_posts':sum(r['authored_posts_total'] for r in per),'nonempty_authored_text_posts':sum(r['nonempty_authored_text_posts'] for r in per),
         'accounts_with_any_authored_text':sum(r['nonempty_authored_text_posts']>0 for r in per),
         'monthly_authored_counts':{m:sum(sum(v.values()) for (u,mm),v in result['monthly'].items() if mm==m) for m in month_names}},
      'confirmed_id_interactions_observed':{'edge_events':len(edge_rows),'directed_pairs':len({(r['source_x_user_id'],r['target_x_user_id']) for r in edge_rows}),
         'nodes_incident':len({x for r in edge_rows for x in (r['source_x_user_id'],r['target_x_user_id'])}),
         'pairs_observed_in_multiple_months':sum(len(ms)>1 for ms in edgepair_months.values()),
         'relation_counts':dict(Counter(r['event_type'] for r in edge_rows)),
         'edge_semantics':'authored quotes to known stable IDs and replies resolved only when target tweet is locally present under a confirmed ID; reposts excluded; no claim of graph completeness'},
      'pagination':{'accounts_marked_truncated_or_uncertain':sum(str(r['truncated_or_uncertain']).lower()=='true' for r in coverage),
         'accounts_pagination_to_target_boundary':sum(str(r['pagination_to_target_boundary']).lower()=='true' for r in coverage),
         'accounts_start_boundary_flag_only':sum(str(r['reached_start_boundary']).lower()=='true' for r in coverage),
         'stop_reasons':dict(Counter(r['stop_reason'] for r in coverage))},
      'request_ledger_audit':audit_request_logs(project),
      'inputs':{},'outputs':{},
      'limitations':['Observed timeline rows are a lower bound, not complete history; pagination order violations make boundary flags uncertain.',
         'No followers/following endpoint was collected, so this is an interaction subgraph induced by visible authored quotes and locally resolvable replies only.',
         'No mention edges are reconstructed because stable mentioned-user IDs are not present in normalized records.',
         'Repost source-post timestamps are not repost-action timestamps; reposts are reported separately and excluded from authored text/temporal edges.',
         'Current wallet-X seed links remain snapshot-only and are not proven valid at each historical post time.',
         'No expansion candidate mapping, timeline, or social edge is treated as confirmed.']}
    input_paths=[RUN/'run_manifest.json',RUN/'sample_manifest.csv',RUN/'requests.jsonl',CONT/'continuation_manifest.json',CONT/'combined_summary.json',CONT/'combined_coverage.csv',CONT/'combined_tweets_in_window.jsonl',CONT/'continuation_requests.jsonl',SEED]
    report['inputs']={str(p):{'sha256':sha256(project/p),'bytes':(project/p).stat().st_size} for p in input_paths}
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'confirmed_seed_timeline_by_account.csv',per)
    write_csv(out/'confirmed_seed_timeline_monthly.csv',monthly,['x_user_id','month_utc','original_posts','reply_posts','quote_posts','authored_posts_total'])
    write_csv(out/'confirmed_seed_interaction_edges.csv',edge_rows,['source_x_user_id','target_x_user_id','event_type','created_at_utc','tweet_id','crosswalk_scope'])
    report['outputs']={name:sha256(out/name) for name in ['confirmed_seed_timeline_by_account.csv','confirmed_seed_timeline_monthly.csv','confirmed_seed_interaction_edges.csv']}
    rp=out/'audit_report.json';rp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(rp),'posts':report['recomputed_timeline'],'interactions':report['confirmed_id_interactions_observed'],'pagination':report['pagination'],'request_ledger_audit':report['request_ledger_audit']},ensure_ascii=False,indent=2))
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out-dir',type=Path,default=BASE/'current_goal_audit/authorized_seed_timeline_20260926')
    a=ap.parse_args();root=a.project_root.resolve();out=a.out_dir if a.out_dir.is_absolute() else root/a.out_dir
    build(root,out)
if __name__=='__main__': main()
