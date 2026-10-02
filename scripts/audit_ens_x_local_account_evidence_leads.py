#!/usr/bin/env python3
"""Offline exact-string lead scan for the frozen 60-row ENS-X probability sample.

This is not an adjudicator: it never changes manual verdicts or calls a local
match an ownership confirmation. Only candidate timeline records whose raw
captured response independently matches status ID, author ID and authored text
are considered. Reposts are excluded; raw replies/quotes are retained only when
that status's own authored text matches exactly.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/ens_x_crosswalk"
RAW_BASE = BASE / "overnight_ai_dataset_20260926/candidate_timeline_evidence"
DEFAULT_WB = BASE / "goal_audit_20260925/manual_review_workbook_231_v2.csv"
DEFAULT_OUT = BASE / "current_goal_audit/local_probability_sample_evidence_leads_20260926"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def rows(path: Path):
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def load_raw_status(raw_path: Path, tweet_id: str):
    try: root=json.loads(raw_path.read_text(encoding='utf-8'))
    except Exception: return None
    found=[]
    def walk(o):
        if isinstance(o,dict):
            if str(o.get('id',''))==str(tweet_id) and isinstance(o.get('author'),dict): found.append(o)
            for v in o.values(): walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(root)
    return found[0] if len(found)==1 else None

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workbook',type=Path,default=DEFAULT_WB)
    ap.add_argument('--out-prefix',type=Path,default=DEFAULT_OUT)
    a=ap.parse_args(); wb=a.workbook.resolve(); out=a.out_prefix.resolve()
    allrows=rows(wb)
    prob=[r for r in allrows if r.get('review_arm')=='stratified_probability_sample_60']
    if len(allrows)!=231 or len(prob)!=60: raise SystemExit('frozen workbook frame mismatch; refusing scan')
    if any(r.get('manual_verdict')!='pending' for r in allrows): raise SystemExit('source workbook is no longer all-pending; refusing scan')
    by_uid={r['x_user_id']:r for r in prob}
    source=RAW_BASE/'normalized_observed_statuses.jsonl'
    found=defaultdict(list); scanned=Counter(); raw_checked=0; raw_failed=0
    for ln,line in enumerate(source.open(encoding='utf-8'),1):
        try: post=json.loads(line)
        except Exception: continue
        uid=str(post.get('queried_user_id') or '')
        if uid not in by_uid: continue
        scanned[uid]+=1
        if post.get('timeline_owner_id_verified')!=uid: raw_failed+=1; continue
        if post.get('post_kind')=='repost' or post.get('is_repost') is True: continue
        text=post.get('authored_text')
        if not isinstance(text,str) or not text.strip(): continue
        rel=post.get('raw_response_file')
        if not rel: raw_failed+=1; continue
        raw=RAW_BASE/rel
        if not raw.is_file(): raw_failed+=1; continue
        st=load_raw_status(raw,str(post.get('tweet_id') or ''))
        if not st or str(st.get('author',{}).get('id',''))!=uid or st.get('reposted_by'):
            raw_failed+=1; continue
        rawtext=((st.get('raw_text') or {}).get('text') if isinstance(st.get('raw_text'),dict) else None) or st.get('text')
        if not isinstance(rawtext,str) or rawtext.strip()!=text.strip():
            raw_failed+=1; continue
        raw_checked+=1
        low=text.casefold()
        matches=[]
        addr=by_uid[uid]['address'].strip().casefold()
        if addr and addr in low: matches.append(('wallet_address_exact',addr))
        ens=(by_uid[uid].get('reverse_ens_name') or '').strip()
        if ens and ens.casefold() in low: matches.append(('ens_name_literal_casefold',ens))
        for kind,term in matches:
            found[uid].append({
                'x_user_id':uid,'address':by_uid[uid]['address'],'handle':by_uid[uid]['handle_at_profile_audit'],
                'candidate_ens_name':ens,'match_type':kind,'matched_term':term,
                'tweet_id':str(post.get('tweet_id') or ''),'tweet_url':f"https://x.com/i/status/{post.get('tweet_id')}",
                'created_at_utc':post.get('created_at_utc'),'post_kind':post.get('post_kind'),
                'author_uid_verified_in_normalized_record':uid,'author_uid_verified_in_raw_response':str(st.get('author',{}).get('id','')),
                'authored_text_excerpt':text[:500], 'raw_response_path':str(raw.relative_to(ROOT)),
                'raw_response_sha256':sha(raw),'normalized_source_line':ln,
                'evidence_class':'offline_literal_match_lead_not_adjudication',
                'limitations':'Exact text occurrence does not by itself establish wallet ownership; human must inspect account context and record dated evidence.'
            })
    out.parent.mkdir(parents=True,exist_ok=True)
    csvpath=out.with_suffix('.csv'); jsonpath=out.with_suffix('.json')
    fields=['x_user_id','address','handle','candidate_ens_name','match_type','matched_term','tweet_id','tweet_url','created_at_utc','post_kind','author_uid_verified_in_normalized_record','author_uid_verified_in_raw_response','authored_text_excerpt','raw_response_path','raw_response_sha256','normalized_source_line','evidence_class','limitations']
    with csvpath.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for uid in sorted(found):
            for r in found[uid]:w.writerow(r)
    counts={uid:scanned[uid] for uid in by_uid}
    match_counts=Counter(x['match_type'] for vals in found.values() for x in vals)
    report={
      'mode':'offline_frozen_probability_sample_literal_evidence_lead_scan_v1',
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'network_requests':0,'paid_queries_usd':0,'workbook_modified':False,'manual_verdicts_changed':False,
      'candidate_frame_rows':len(allrows),'probability_sample_rows':len(prob),'targeted_rows_excluded':171,
      'all_source_verdicts_pending':True,'source_workbook':str(wb.relative_to(ROOT)),'source_workbook_sha256':sha(wb),
      'normalized_candidate_timeline_source':str(source.relative_to(ROOT)),'source_sha256':sha(source),
      'probability_sample_accounts_with_any_local_normalized_status':sum(v>0 for v in counts.values()),
      'candidate_status_records_for_sample':sum(counts.values()),'raw_status_records_independently_checked':raw_checked,
      'raw_status_records_failed_or_unavailable':raw_failed,
      'accounts_with_exact_match_leads':len(found),'exact_match_lead_count':sum(map(len,found.values())),
      'lead_counts_by_type':dict(match_counts),'accounts_with_no_local_status':sum(v==0 for v in counts.values()),
      'per_account_local_status_counts':counts,
      'lead_csv':str(csvpath.relative_to(ROOT)),'lead_csv_sha256':sha(csvpath),
      'interpretation':'Discovery leads only. Exact address/name occurrence is not ownership proof; no verdict assigned. The 171-row targeted complement was excluded. Human reviewer must inspect source account content and capture evidence/seen time.'
    }
    jsonpath.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
