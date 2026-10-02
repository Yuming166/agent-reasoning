#!/usr/bin/env python3
"""Slow, resumable finalization for the bounded 37-FID Farcaster pilot.

No new candidate FIDs are added. Retries only current selected FIDs after the
first public-hub run hit 429s. Each retry response is saved separately.
"""
from __future__ import annotations
import csv,json,time,hashlib
from datetime import datetime,timezone,timedelta
from pathlib import Path
import requests
from run_farcaster_public_hub_pilot import parse_casts,parse_reactions,parse_links,cast_ts,iso,write_csv,write_json,sha256_file

ROOT=Path('artifacts/farcaster_pilot_20260926'); HUB='https://hub.pinata.cloud/v1'; UA='exgraph-farcaster-pilot/0.1 (bounded research read-only collection)'
START=datetime.fromisoformat('2026-01-01T00:00:00+00:00'); END=datetime.fromisoformat('2026-09-26T00:00:00+00:00')

def fetch(session, endpoint, fid, params, attempt):
    url=HUB+'/'+endpoint
    name=f'retry_{endpoint}_{fid}_{attempt:02d}.json'
    p=ROOT/'raw'/'hub'/name
    rec={'request':{'url':url,'params':params},'fetched_at_utc':iso(datetime.now(timezone.utc))}
    try:
        r=session.get(url,params=params,timeout=25); rec['status_code']=r.status_code
        try: rec['body']=r.json()
        except Exception: rec['body']=r.text[:1000000]
        p.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
        return rec
    except Exception as e:
        rec['error']=f'{type(e).__name__}: {e}'; p.write_text(json.dumps(rec,indent=2)); return rec

def paginate(session, endpoint, fid, reaction_type=None, max_pages=10):
    token=None; msgs=[]; pages=[]; errors=[]
    for pg in range(max_pages):
        params={'fid':fid,'pageSize':100,'reverse':'true'}
        if reaction_type: params['reaction_type']=reaction_type
        if token: params['pageToken']=token
        rec=None
        for attempt in range(1,6):
            rec=fetch(session,endpoint,fid,params,attempt)
            if rec.get('status_code')==200: break
            if rec.get('status_code')==429: time.sleep(2.0*attempt)
            else: break
        if rec.get('status_code')!=200:
            errors.append({'endpoint':endpoint,'fid':fid,'status_code':rec.get('status_code'),'error':rec.get('error'),'attempts':5 if rec.get('status_code')==429 else 1}); break
        d=rec.get('body') or {}; batch=d.get('messages') or []; msgs.extend(batch); token=d.get('nextPageToken')
        pages.append({'page':pg,'count':len(batch),'request_params':params,'nextPageToken':token,'status_code':200})
        # reverse=true yields newest first; stop after a page reaches before window start.
        ts=[m.get('data',{}).get('timestamp') for m in batch if m.get('data',{}).get('timestamp') is not None]
        if ts and min(cast_ts(x) for x in ts) < START: break
        if not token: break
        time.sleep(0.8)
    return msgs,pages,errors

def main():
    selected=list(csv.DictReader((ROOT/'selected_fids.csv').open()))
    fids=sorted({int(x['fid']) for x in selected})
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/json'})
    all_casts=[]; all_reactions=[]; final_links=[]; coverage=[]; errors=[]
    for idx,fid in enumerate(fids,1):
        cm,cp,ce=paginate(s,'castsByFid',fid); all_casts.extend([x for x in parse_casts(cm) if START<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<END]); errors.extend(ce)
        lm,lp,le=paginate(s,'linksByFid',fid); final_links.extend(parse_links(lm)); errors.extend(le)
        like,lip,lie=paginate(s,'reactionsByFid',fid,'Like'); rec,rep,ree=paginate(s,'reactionsByFid',fid,'Recast'); errors.extend(lie+ree)
        rr=parse_reactions(like)+parse_reactions(rec); all_reactions.extend([x for x in rr if START<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<END])
        coverage.append({'fid':fid,'cast_pages':cp,'cast_stop_reason':'window_boundary_or_cursor','cast_messages_window':sum(1 for x in all_casts if x['fid']==fid),'link_pages':lp,'link_stop_reason':'cursor_or_error','current_follow_messages':sum(1 for x in final_links if x['source_fid']==fid),'like_pages':lip,'recast_pages':rep,'reaction_messages_window':sum(1 for x in all_reactions if x['source_fid']==fid),'errors_for_fid':len([e for e in errors if e.get('fid')==fid])})
        print(f'{idx}/{len(fids)} fid={fid} casts={coverage[-1]["cast_messages_window"]} follows={coverage[-1]["current_follow_messages"]} reactions={coverage[-1]["reaction_messages_window"]}',flush=True)
        time.sleep(1.0)
    # Restrict links to selected frame.
    selected_set=set(fids); final_links=[x for x in final_links if x['source_fid'] in selected_set and x['target_fid'] in selected_set]
    write_csv(ROOT/'farcaster_casts_window.jsonl.csv',all_casts,list(all_casts[0].keys()) if all_casts else ['fid'])
    with (ROOT/'farcaster_casts_window.jsonl').open('w') as f:
        for x in all_casts:f.write(json.dumps(x,ensure_ascii=False)+'\n')
    write_csv(ROOT/'farcaster_follow_edges_current.csv',final_links,['source_fid','target_fid','link_type','add_timestamp_utc','display_timestamp_utc','farcaster_timestamp','message_hash','current_state','deleted_at_utc','deletion_history_status'])
    write_csv(ROOT/'farcaster_reaction_edges_window.csv',all_reactions,['source_fid','target_fid','target_cast_hash','reaction_type','timestamp_utc','message_hash','state'])
    write_csv(ROOT/'collection_coverage.csv',coverage,list(coverage[0].keys()) if coverage else ['fid'])
    # Add reply and quote edges from current window casts.
    replies=[]; quotes=[]
    for c in all_casts:
        if c.get('parent_fid') in selected_set: replies.append({'source_fid':c['fid'],'target_fid':c['parent_fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'reply'})
        for emb in c.get('embeds') or []:
            ci=emb.get('castId') if isinstance(emb,dict) else None
            if isinstance(ci,dict) and ci.get('fid') in selected_set: quotes.append({'source_fid':c['fid'],'target_fid':ci['fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'quote'})
    write_csv(ROOT/'farcaster_reply_edges_window.csv',replies,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type']); write_csv(ROOT/'farcaster_quote_edges_window.csv',quotes,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type'])
    social=final_links+all_reactions+replies+quotes; nodes=set();
    for x in social:
        if x.get('source_fid') is not None:nodes.add(x['source_fid'])
        if x.get('target_fid') is not None:nodes.add(x['target_fid'])
    report=json.loads((ROOT/'quality_report.json').read_text()); report.update({'generated_at_utc':iso(datetime.now(timezone.utc)),'selected_fids':len(fids),'current_follow_edges_internal':len(final_links),'reply_edges_window_internal':len(replies),'quote_edges_window_internal':len(quotes),'reaction_edges_window_internal':len(all_reactions),'social_edges_total_internal':len(social),'social_nodes_with_any_edge':len(nodes),'selected_fids_with_window_casts':len({x['fid'] for x in all_casts}),'window_casts':len(all_casts),'retry_finalization':True,'retry_errors':errors,'retry_error_count':len(errors),'collection_stop':'fixed_37_fid_allowlist_no_expansion'})
    write_json(ROOT/'quality_report.json',report)
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and p.name!='manifest.json':files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
    write_json(ROOT/'manifest.json',{'generated_at_utc':iso(datetime.now(timezone.utc)),'files':files,'retry_finalization':True,'error_count':len(errors)})
    print(json.dumps({k:report[k] for k in ['selected_fids','current_follow_edges_internal','reply_edges_window_internal','quote_edges_window_internal','reaction_edges_window_internal','social_edges_total_internal','social_nodes_with_any_edge','selected_fids_with_window_casts','window_casts','retry_error_count']},indent=2))
if __name__=='__main__':main()
