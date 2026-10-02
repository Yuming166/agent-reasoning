#!/usr/bin/env python3
"""Offline rebuild after correcting Farcaster timestamp units.

Farcaster Hub timestamps are seconds since 2021-01-01, not milliseconds. This
script only reads already archived retry responses; it makes no network calls.
"""
import csv,json,glob
from pathlib import Path
from datetime import datetime,timezone,timedelta
from run_farcaster_public_hub_pilot import parse_casts,parse_reactions,parse_links,cast_ts,iso,write_csv,write_json,sha256_file
ROOT=Path('artifacts/farcaster_pilot_20260926'); START=datetime.fromisoformat('2026-01-01T00:00:00+00:00'); END=datetime.fromisoformat('2026-09-26T00:00:00+00:00')
def load_success(pattern):
 out={}
 for p in glob.glob(str(ROOT/'raw'/'hub'/pattern)):
  try:
   d=json.loads(Path(p).read_text())
   if d.get('status_code')==200: out[p]=d
  except: pass
 return out
def messages_for(fid, prefix):
 matches=[]
 for p,d in load_success(f'retry_{prefix}_{fid}_*.json').items():
  matches.append((p,d.get('body',{}).get('messages',[])))
 # Keep all successful attempts/pages, de-duplicate by message hash.
 seen={};
 for p,ms in matches:
  for m in ms:
   seen[m.get('hash') or json.dumps(m,sort_keys=True)]=m
 return list(seen.values()),matches
def main():
 fids=sorted({int(r['fid']) for r in csv.DictReader((ROOT/'selected_fids.csv').open())}); sf=set(fids)
 all_casts=[]; all_reactions=[]; follows=[]; cov=[]
 for fid in fids:
  cm,cmraw=messages_for(fid,'castsByFid'); lm,lmraw=messages_for(fid,'linksByFid'); like,_=messages_for(fid,'reactionsByFid') # not used because filename ambiguous
  # Explicitly load Like/Recast from raw files.
  lmsgs=[]; rmsgs=[]
  for p,d in load_success(f'retry_reactionsByFid_{fid}_*.json').items():
   # request params distinguish type
   typ=((d.get('request') or {}).get('params') or {}).get('reaction_type')
   if typ=='Like': lmsgs.extend(d.get('body',{}).get('messages',[]))
   elif typ=='Recast': rmsgs.extend(d.get('body',{}).get('messages',[]))
  casts=parse_casts(cm); reactions=parse_reactions(lmsgs)+parse_reactions(rmsgs); links=parse_links(lm)
  all_casts.extend(casts); all_reactions.extend(reactions); follows.extend(links)
  dates=[datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00')) for x in casts]
  cov.append({'fid':fid,'cast_raw_messages':len(casts),'cast_raw_files':len(cmraw),'cast_min_observed_utc':iso(min(dates)) if dates else None,'cast_max_observed_utc':iso(max(dates)) if dates else None,'cast_page_tokens_present':any(bool(json.loads(Path(p).read_text()).get('body',{}).get('nextPageToken')) for p,_ in cmraw),'follow_current_messages':len(links),'reaction_observed_messages':len(reactions),'status':'observed_page_incomplete' if any(bool(json.loads(Path(p).read_text()).get('body',{}).get('nextPageToken')) for p,_ in cmraw) else 'cursor_exhausted_or_empty'})
 # current links internal; dedup
 fd={};
 for x in follows:
  if x['source_fid'] in sf and x['target_fid'] in sf: fd[(x['source_fid'],x['target_fid'],x['message_hash'])]=x
 follows=list(fd.values())
 # all observed reactions internal
 reactions=[x for x in all_reactions if x.get('source_fid') in sf and x.get('target_fid') in sf]
 casts_all=all_casts; casts_window=[x for x in casts_all if START<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<END]
 reactions_window=[x for x in reactions if START<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<END]
 replies=[]; quotes=[]
 for c in casts_all:
  if c.get('parent_fid') in sf: replies.append({'source_fid':c['fid'],'target_fid':c['parent_fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'reply'})
  for emb in c.get('embeds') or []:
   ci=emb.get('castId') if isinstance(emb,dict) else None
   if isinstance(ci,dict) and ci.get('fid') in sf: quotes.append({'source_fid':c['fid'],'target_fid':ci['fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'quote'})
 def inwindow(x): return START<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<END
 replies_window=[x for x in replies if inwindow(x)]; quotes_window=[x for x in quotes if inwindow(x)]
 for name,rows,fields in [
  ('farcaster_casts_observed_all.jsonl',casts_all,None),('farcaster_reaction_edges_observed_all.csv',reactions,['source_fid','target_fid','target_cast_hash','reaction_type','timestamp_utc','message_hash','state']),('farcaster_reply_edges_observed_all.csv',replies,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type']),('farcaster_quote_edges_observed_all.csv',quotes,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type']),('farcaster_reaction_edges_window.csv',reactions_window,['source_fid','target_fid','target_cast_hash','reaction_type','timestamp_utc','message_hash','state']),('farcaster_reply_edges_window.csv',replies_window,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type']),('farcaster_quote_edges_window.csv',quotes_window,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type'])]:
  p=ROOT/name
  if name.endswith('.jsonl'):
   with p.open('w') as f:
    for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
  else: write_csv(p,rows,fields)
 # Preserve window file too, now correctly parsed.
 with (ROOT/'farcaster_casts_window.jsonl').open('w') as f:
  for x in casts_window:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 write_csv(ROOT/'collection_coverage_rebuilt.csv',cov,list(cov[0].keys()) if cov else ['fid'])
 dates=[datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00')) for x in casts_all]
 report=json.loads((ROOT/'quality_report.json').read_text())
 report.update({'generated_at_utc':iso(datetime.now(timezone.utc)),'timestamp_unit':'seconds_since_2021-01-01T00:00:00Z','offline_rebuild_no_new_requests':True,'observed_casts_all_available_pages':len(casts_all),'observed_cast_fids_all_available_pages':len({x['fid'] for x in casts_all}),'observed_cast_min_utc':iso(min(dates)) if dates else None,'observed_cast_max_utc':iso(max(dates)) if dates else None,'window_casts':len(casts_window),'selected_fids_with_window_casts':len({x['fid'] for x in casts_window}),'current_follow_edges_internal':len(follows),'reaction_edges_observed_internal':len(reactions),'reply_edges_observed_internal':len(replies),'quote_edges_observed_internal':len(quotes),'reaction_edges_window_internal':len(reactions_window),'reply_edges_window_internal':len(replies_window),'quote_edges_window_internal':len(quotes_window),'social_edges_total_internal':len(follows)+len(reactions)+len(replies)+len(quotes),'social_nodes_with_any_edge':len({z for x in follows+reactions+replies+quotes for z in (x.get('source_fid'),x.get('target_fid')) if z is not None}),'coverage_note':'Only archived retry responses are used; page tokens indicate incomplete cast coverage for some FIDs.'})
 write_json(ROOT/'quality_report.json',report)
 files=[]
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and p.name!='manifest.json':files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
 write_json(ROOT/'manifest.json',{'generated_at_utc':iso(datetime.now(timezone.utc)),'files':files,'offline_rebuild':True,'network_requests':0})
 print(json.dumps({k:report[k] for k in ['timestamp_unit','selected_fids','observed_casts_all_available_pages','observed_cast_fids_all_available_pages','observed_cast_min_utc','observed_cast_max_utc','window_casts','current_follow_edges_internal','reaction_edges_observed_internal','reply_edges_observed_internal','quote_edges_observed_internal','social_edges_total_internal','social_nodes_with_any_edge']},indent=2))
if __name__=='__main__':main()
