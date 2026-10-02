#!/usr/bin/env python3
"""Bounded, unauthenticated Farcaster Hub pilot.

This script intentionally uses only a public read-only Farcaster Hub endpoint and
public Base JSON-RPC. It records raw responses, cursors, errors, and coverage;
it does not infer historical deletion absence from the current-index endpoints.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import requests

FARCASTER_EPOCH = datetime(2021, 1, 1, tzinfo=timezone.utc)
DEFAULT_HUB = "https://hub.pinata.cloud/v1"
DEFAULT_BASE_RPC = "https://mainnet.base.org"
UA = "exgraph-farcaster-pilot/0.1 (bounded research read-only collection)"


def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def cast_ts(seconds): return FARCASTER_EPOCH + timedelta(seconds=seconds)
def sha256_file(p: Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

class Fetcher:
    def __init__(self, root: Path, hub: str, timeout: float=20):
        self.root=root; self.hub=hub.rstrip('/'); self.timeout=timeout
        self.session=requests.Session(); self.session.headers.update({'User-Agent': UA, 'Accept':'application/json'})
        self.raw=root/'raw'; self.raw.mkdir(parents=True,exist_ok=True)
        (self.raw/'hub').mkdir(exist_ok=True); (self.raw/'base_rpc').mkdir(exist_ok=True)
        self.errors=[]
    def get(self, name: str, path: str, params: dict[str, Any]|None=None, raw_name: str|None=None):
        url=self.hub+path
        fn=(raw_name or name).replace('/','_').replace('?','_')+'.json'
        out=self.raw/'hub'/fn
        if out.exists():
            try: return json.loads(out.read_text())
            except Exception: pass
        rec={'request':{'url':url,'params':params},'fetched_at_utc':iso(now())}
        try:
            r=self.session.get(url,params=params,timeout=self.timeout)
            rec['status_code']=r.status_code; rec['headers']={'content-type':r.headers.get('content-type')}
            rec['body']=r.json() if r.headers.get('content-type','').startswith('application/json') else r.text[:1000000]
            out.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
            if r.status_code>=400:
                self.errors.append({'kind':'http','name':name,'status_code':r.status_code,'url':r.url,'body':r.text[:500]})
                return None
            return rec['body']
        except Exception as e:
            rec['error']=f'{type(e).__name__}: {e}'
            out.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
            self.errors.append({'kind':'exception','name':name,'url':url,'error':rec['error']})
            return None
    def paginate(self, endpoint: str, fid: int, page_size: int, reverse: bool=False, max_pages: int=20, tag: str=''):
        messages=[]; token=None; pages=[]; stop='max_pages'
        for i in range(max_pages):
            params={'fid':fid,'pageSize':page_size}
            if reverse: params['reverse']='true'
            if token: params['pageToken']=token
            name=f'{tag}_{fid}_{i:04d}'
            d=self.get(name, '/'+endpoint, params, raw_name=name)
            if not isinstance(d,dict): stop='request_or_payload_failed'; break
            batch=d.get('messages') or []
            messages.extend(batch); pages.append({'page':i,'count':len(batch),'request_params':params,'nextPageToken':d.get('nextPageToken')})
            nt=d.get('nextPageToken')
            if not nt: stop='cursor_exhausted'; break
            token=nt
        return messages, {'pages':pages,'stop_reason':stop,'message_count':len(messages),'endpoint':endpoint,'fid':fid}


def parse_eth_verifications(messages):
    out=[]
    for m in messages or []:
        data=m.get('data',{}); body=data.get('verificationAddAddressBody') or {}
        if data.get('type')=='MESSAGE_TYPE_VERIFICATION_ADD_ETH_ADDRESS' and body.get('protocol')=='PROTOCOL_ETHEREUM':
            out.append({'fid':data.get('fid'),'address':str(body.get('address','')).lower(),
                        'chain_id':body.get('chainId'),'protocol':body.get('protocol'),
                        'verification_add_timestamp':iso(cast_ts(data.get('timestamp',0))),
                        'farcaster_timestamp':data.get('timestamp'),'message_hash':m.get('hash'),
                        'signature_scheme':m.get('signatureScheme'),'deleted_at_utc':None,
                        'state':'present_in_current_hub_index','deletion_history_status':'not_exposed_by_current_endpoint'})
    return out

def parse_links(messages):
    out=[]
    for m in messages or []:
        d=m.get('data',{}); b=d.get('linkBody') or {}
        if d.get('type')=='MESSAGE_TYPE_LINK_ADD' and b.get('type')=='follow':
            out.append({'source_fid':d.get('fid'),'target_fid':b.get('targetFid'),
                        'link_type':'follow','add_timestamp_utc':iso(cast_ts(d.get('timestamp',0))),
                        'display_timestamp_utc':iso(cast_ts(b['displayTimestamp'])) if b.get('displayTimestamp') is not None else None,
                        'farcaster_timestamp':d.get('timestamp'),'message_hash':m.get('hash'),
                        'current_state':'present_in_current_hub_index','deleted_at_utc':None,
                        'deletion_history_status':'not_exposed_by_current_endpoint'})
    return out

def parse_casts(messages):
    out=[]
    for m in messages or []:
        d=m.get('data',{}); b=d.get('castAddBody') or {}
        if d.get('type')!='MESSAGE_TYPE_CAST_ADD': continue
        parent=b.get('parentCastId') or {}
        embeds=b.get('embeds') or []
        out.append({'fid':d.get('fid'),'hash':m.get('hash'),'timestamp_utc':iso(cast_ts(d.get('timestamp',0))),
                    'farcaster_timestamp':d.get('timestamp'),'text':b.get('text',''),
                    'parent_fid':parent.get('fid'),'parent_cast_hash':parent.get('hash'),
                    'parent_url':b.get('parentUrl'),'mentions':b.get('mentions') or [],
                    'embeds':embeds,'cast_type':b.get('type'),'state':'present_in_current_hub_index'})
    return out

def parse_reactions(messages):
    out=[]
    for m in messages or []:
        d=m.get('data',{}); b=d.get('reactionBody') or {}
        if d.get('type')!='MESSAGE_TYPE_REACTION_ADD': continue
        target=b.get('targetCastId') or {}
        out.append({'source_fid':d.get('fid'),'target_fid':target.get('fid'),'target_cast_hash':target.get('hash'),
                    'reaction_type':b.get('type'),'timestamp_utc':iso(cast_ts(d.get('timestamp',0))),
                    'message_hash':m.get('hash'),'state':'present_in_current_hub_index'})
    return out

def rpc_nonce(session, raw_dir: Path, address: str, timeout=15):
    payload={'jsonrpc':'2.0','id':1,'method':'eth_getTransactionCount','params':[address,'latest']}
    p=raw_dir/f'{address}.json'
    if p.exists():
        try: d=json.loads(p.read_text()); return d
        except Exception: pass
    rec={'request':{'url':DEFAULT_BASE_RPC,'json':payload},'fetched_at_utc':iso(now())}
    try:
        r=session.post(DEFAULT_BASE_RPC,json=payload,timeout=timeout)
        rec['status_code']=r.status_code; rec['body']=r.json()
    except Exception as e: rec['error']=f'{type(e).__name__}: {e}'
    p.write_text(json.dumps(rec,indent=2))
    return rec

def write_json(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def write_csv(p, rows, fields):
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='artifacts/farcaster_pilot_20260926')
    ap.add_argument('--hub',default=DEFAULT_HUB)
    ap.add_argument('--discovery-fids',type=int,default=1000)
    ap.add_argument('--target-fids',type=int,default=150)
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--page-size',type=int,default=100)
    ap.add_argument('--max-pages',type=int,default=20)
    ap.add_argument('--window-start',default='2026-01-01T00:00:00Z')
    ap.add_argument('--window-end',default='2026-09-26T00:00:00Z')
    args=ap.parse_args(); root=Path(args.out); root.mkdir(parents=True,exist_ok=True)
    started=now(); fetch=Fetcher(root,args.hub)
    write_json(root/'run_config.json',{'started_at_utc':iso(started),'hub':args.hub,'base_rpc':DEFAULT_BASE_RPC,'discovery_fids':args.discovery_fids,'target_fids':args.target_fids,'workers':args.workers,'page_size':args.page_size,'max_pages':args.max_pages,'window_start':args.window_start,'window_end':args.window_end,'paid_queries_usd':0,'auth_used':False})
    source='''# Farcaster public-hub pilot source and access record\n\n- Collection source: public Farcaster Hub HTTP API at `https://hub.pinata.cloud/v1`.\n- Collection mode: unauthenticated read-only HTTP GET; no Dune, Neynar, paid API, or API key was used.\n- Chain source: public Base JSON-RPC `https://mainnet.base.org`, read-only `eth_getTransactionCount`; no API key.\n- Raw responses, request parameters, cursors, failures, and UTC collection timestamps are retained under `raw/`.\n- Hub current-index endpoints expose currently indexed records; this pilot does **not** infer that `deleted_at = null` means an edge or verification never had a delete event.\n- Public accessibility is not a grant of redistribution rights. The pilot retains source metadata and should not publish raw text or raw signatures without a separate terms/licensing review.\n- Historical as-of completeness is not claimed.\n'''
    (root/'SOURCE_AND_ACCESS.md').write_text(source)
    # Discover a bounded FID list from shard 1.
    fids=[]; token=None; fids_pages=[]
    while len(fids)<args.discovery_fids and len(fids_pages)<20:
        params={'shard_id':1,'page_size':min(5000,args.discovery_fids-len(fids))}
        if token: params['page_token']=token
        # /fids is not under the same endpoint query conventions; use direct call and retain response.
        fn=f'fids_{len(fids_pages):04d}.json'; url=args.hub+'/fids'
        try:
            r=fetch.session.get(url,params=params,timeout=fetch.timeout)
            rec={'request':{'url':url,'params':params},'fetched_at_utc':iso(now()),'status_code':r.status_code,'body':r.json()}
            (root/'raw'/'hub'/fn).write_text(json.dumps(rec,indent=2))
            if r.status_code>=400: raise RuntimeError(r.text[:500])
            d=rec['body']; batch=d.get('fids',[]); fids.extend(batch); token=d.get('nextPageToken'); fids_pages.append({'params':params,'count':len(batch),'nextPageToken':token})
            if not token: break
        except Exception as e:
            fids_pages.append({'params':params,'error':f'{type(e).__name__}: {e}'}); break
    fids=list(dict.fromkeys(fids))[:args.discovery_fids]
    write_json(root/'discovered_fids.json',{'fids':fids,'pages':fids_pages,'count':len(fids)})
    # Discovery: current Ethereum verifications and follow links; no casts yet.
    def discover(fid):
        vm,vc=fetch.paginate('verificationsByFid',fid,args.page_size,False,args.max_pages,'verification')
        lm,lc=fetch.paginate('linksByFid',fid,args.page_size,False,args.max_pages,'link')
        return fid,vm,vc,lm,lc
    discovered=[]; t0=time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fs=[ex.submit(discover,int(fid)) for fid in fids]
        for fut in as_completed(fs):
            discovered.append(fut.result())
    eth=[]; links=[]; coverage=[]
    for fid,vm,vc,lm,lc in sorted(discovered):
        e=parse_eth_verifications(vm); l=parse_links(lm); eth.extend(e); links.extend(l)
        coverage.append({'fid':fid,'verification_pages':vc['pages'],'verification_stop_reason':vc['stop_reason'],'verification_messages':len(vm),'eth_verification_count':len(e),'link_pages':lc['pages'],'link_stop_reason':lc['stop_reason'],'link_messages':len(lm),'follow_count':len(l)})
    # Score candidates based on explicit current verification, follows, internal degree, not identity inference.
    pool=set(fids); deg={fid:0 for fid in fids}; internal={fid:0 for fid in fids}
    for l in links:
        if l['source_fid'] in deg: deg[l['source_fid']]+=1
        if l['target_fid'] in pool:
            internal[l['source_fid']]=internal.get(l['source_fid'],0)+1
            if l['target_fid'] in deg: deg[l['target_fid']]+=1
    byfid={fid:[] for fid in fids}
    for e in eth: byfid.setdefault(e['fid'],[]).append(e)
    # EVM addresses are case-normalized, deduplicated per FID.
    candidates=[]
    for fid in fids:
        addrs=sorted({e['address'] for e in byfid.get(fid,[]) if e['address'].startswith('0x') and len(e['address'])==42})
        score=(min(len(addrs),3)*100 + min(internal.get(fid,0),50)*5 + min(deg.get(fid,0),100) + (10 if internal.get(fid,0)>0 else 0))
        if addrs: candidates.append({'fid':fid,'eth_addresses':addrs,'eth_verification_count':len(addrs),'internal_follow_degree':internal.get(fid,0),'follow_degree':deg.get(fid,0),'selection_score':score})
    candidates.sort(key=lambda x:(-x['selection_score'],x['fid']))
    selected=candidates[:args.target_fids]
    selected_fids={x['fid'] for x in selected}
    # Final collection: current links, casts in target window, replies/quotes, likes/recasts.
    final_links=[l for l in links if l['source_fid'] in selected_fids and l['target_fid'] in selected_fids]
    all_casts=[]; all_reactions=[]; final_cov=[]
    def collect(fid):
        cm,cc=fetch.paginate('castsByFid',fid,args.page_size,True,args.max_pages,'cast')
        like,lc1=fetch.paginate('reactionsByFid',fid,args.page_size,True,args.max_pages,'like')
        rec,lc2=fetch.paginate('reactionsByFid',fid,args.page_size,True,args.max_pages,'recast')
        return fid,cm,cc,like,lc1,rec,lc2
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fs=[ex.submit(collect,int(fid)) for fid in sorted(selected_fids)]
        for fut in as_completed(fs):
            fid,cm,cc,like,lc1,rec,lc2=fut.result()
            casts=parse_casts(cm); reactions=parse_reactions(like)+parse_reactions(rec)
            # Keep observations in requested window; preserve page coverage separately.
            s=datetime.fromisoformat(args.window_start.replace('Z','+00:00')); e=datetime.fromisoformat(args.window_end.replace('Z','+00:00'))
            casts=[c for c in casts if s<=datetime.fromisoformat(c['timestamp_utc'].replace('Z','+00:00'))<e]
            reactions=[x for x in reactions if s<=datetime.fromisoformat(x['timestamp_utc'].replace('Z','+00:00'))<e]
            all_casts.extend(casts); all_reactions.extend(reactions)
            final_cov.append({'fid':fid,'cast_pages':cc['pages'],'cast_stop_reason':cc['stop_reason'],'cast_messages_window':len(casts),'like_pages':lc1['pages'],'like_stop_reason':lc1['stop_reason'],'like_messages_window':sum(1 for x in reactions if x['reaction_type']=='Like'),'recast_pages':lc2['pages'],'recast_stop_reason':lc2['stop_reason'],'recast_messages_window':sum(1 for x in reactions if x['reaction_type']=='Recast')})
    # Base outbound nonce checks for selected verified addresses.
    rpc_s=requests.Session(); rpc_s.headers.update({'User-Agent':UA,'Accept':'application/json'})
    addresses=sorted({a for x in selected for a in x['eth_addresses']})
    nonce_rows=[]
    for addr in addresses:
        d=rpc_nonce(rpc_s,root/'raw'/'base_rpc',addr)
        body=d.get('body',{}) if isinstance(d,dict) else {}
        result=body.get('result') if isinstance(body,dict) else None
        try: nonce=int(result,16) if result is not None else None
        except Exception: nonce=None
        nonce_rows.append({'address':addr,'outbound_transaction_count_latest':nonce,'rpc_status_code':d.get('status_code'),'rpc_error':d.get('error'),'activity_signal':'outbound_nonce_positive' if nonce and nonce>0 else ('zero_or_unknown' if nonce==0 else 'unavailable'),'observed_at_utc':d.get('fetched_at_utc')})
    nonce_map={x['address']:x for x in nonce_rows}
    for x in selected:
        x['base_addresses']=[dict(nonce_map[a]) for a in x['eth_addresses']]
        x['base_outbound_nonce_positive']=any((nonce_map[a].get('outbound_transaction_count_latest') or 0)>0 for a in x['eth_addresses'])
        x['base_activity_evidence']='public_rpc_eth_getTransactionCount_only'
    # Outputs.
    write_csv(root/'fid_wallet_crosswalk.csv', [dict(fid=x['fid'],address=e['address'],chain_id=e['chain_id'],protocol=e['protocol'],verification_add_timestamp=e['verification_add_timestamp'],message_hash=e['message_hash'],deleted_at_utc=e['deleted_at_utc'],state=e['state'],deletion_history_status=e['deletion_history_status'],selection_member='true') for x in selected for e in byfid[x['fid']] if e['address'] in x['eth_addresses']], ['fid','address','chain_id','protocol','verification_add_timestamp','message_hash','deleted_at_utc','state','deletion_history_status','selection_member'])
    write_csv(root/'farcaster_follow_edges_current.csv',final_links,['source_fid','target_fid','link_type','add_timestamp_utc','display_timestamp_utc','farcaster_timestamp','message_hash','current_state','deleted_at_utc','deletion_history_status'])
    write_csv(root/'farcaster_casts_window.jsonl.csv',all_casts, list(all_casts[0].keys()) if all_casts else ['fid'])
    # Also JSONL for text fidelity.
    with (root/'farcaster_casts_window.jsonl').open('w') as f:
        for x in all_casts: f.write(json.dumps(x,ensure_ascii=False)+'\n')
    write_csv(root/'farcaster_reaction_edges_window.csv',all_reactions,['source_fid','target_fid','target_cast_hash','reaction_type','timestamp_utc','message_hash','state'])
    write_csv(root/'base_address_activity_nonce.csv',nonce_rows,list(nonce_rows[0].keys()) if nonce_rows else ['address'])
    write_csv(root/'discovery_coverage.csv',coverage,list(coverage[0].keys()) if coverage else ['fid'])
    write_csv(root/'selected_fids.csv',selected,list(selected[0].keys())+['base_addresses','base_outbound_nonce_positive','base_activity_evidence'] if selected else ['fid'])
    write_csv(root/'collection_coverage.csv',final_cov,list(final_cov[0].keys()) if final_cov else ['fid'])
    # quality stats
    selected_set=selected_fids; cast_fids={x['fid'] for x in all_casts}; social_nodes=set(selected_set)
    social_edges=final_links + [{'source_fid':x['source_fid'],'target_fid':x['target_fid']} for x in all_reactions if x.get('target_fid') in selected_set]
    # Reply/quote edges from selected casts.
    reply_edges=[]; quote_edges=[]
    for c in all_casts:
        if c.get('parent_fid') in selected_set:
            reply_edges.append({'source_fid':c['fid'],'target_fid':c['parent_fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'reply'})
        for emb in c.get('embeds') or []:
            # Hub embeds can carry castId in several JSON shapes.
            ci=emb.get('castId') if isinstance(emb,dict) else None
            if isinstance(ci,dict) and ci.get('fid') in selected_set:
                quote_edges.append({'source_fid':c['fid'],'target_fid':ci['fid'],'timestamp_utc':c['timestamp_utc'],'cast_hash':c['hash'],'edge_type':'quote'})
    write_csv(root/'farcaster_reply_edges_window.csv',reply_edges,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type'])
    write_csv(root/'farcaster_quote_edges_window.csv',quote_edges,['source_fid','target_fid','timestamp_utc','cast_hash','edge_type'])
    for x in reply_edges+quote_edges: social_edges.append(x)
    nodes_with_edges=set()
    for x in social_edges:
        if x.get('source_fid') is not None: nodes_with_edges.add(x['source_fid'])
        if x.get('target_fid') is not None: nodes_with_edges.add(x['target_fid'])
    report={'schema':'exgraph_farcaster_public_hub_pilot_v1','generated_at_utc':iso(now()),'source_hub':args.hub,'base_rpc':DEFAULT_BASE_RPC,'auth_used':False,'paid_queries_usd':0,'discovery_fids':len(fids),'candidate_fids_with_eth_verification':len(candidates),'selected_fids':len(selected),'selected_fids_with_positive_base_outbound_nonce':sum(1 for x in selected if x['base_outbound_nonce_positive']),'unique_verified_eth_addresses':len(addresses),'current_follow_edges_internal':len(final_links),'reply_edges_window_internal':len(reply_edges),'quote_edges_window_internal':len(quote_edges),'reaction_edges_window_internal':sum(1 for x in all_reactions if x.get('target_fid') in selected_set),'social_edges_total_internal':len(social_edges),'social_nodes_with_any_edge':len(nodes_with_edges),'selected_fids_with_window_casts':len(cast_fids),'window_casts':len(all_casts),'window_start_utc':args.window_start,'window_end_utc':args.window_end,'verification_deletion_history':'not_available_from_current_verificationsByFid_endpoint','follow_deletion_history':'not_available_from_current_linksByFid_endpoint','asof_ready':False,'limitations':['Current-index endpoints are not complete add/delete event histories.','Base activity is only outbound nonce evidence from public JSON-RPC, not a full transaction/transfer graph.','Selected FIDs are a bounded high-connectivity sample from the first shard listing, not population-representative.','Raw cast text and signatures require separate publication/terms review.'],'errors':fetch.errors,'output_files':[]}
    write_json(root/'quality_report.json',report)
    # manifest after outputs
    files=[]
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name not in ('manifest.json',): files.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
    write_json(root/'manifest.json',{'generated_at_utc':iso(now()),'files':files,'run_seconds':round(time.time()-t0,2),'errors':fetch.errors})
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
