#!/usr/bin/env python3
"""Find exact self-reference leads in already archived X timeline pages.

Offline only: no API/network calls, no verdict assignment, and no crosswalk update.
Retweets/repost payloads are excluded; each hit still needs human review.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_PACKET_SHA256 = "3825939022b0ec177af4cf2c57624c0a28cbb2cf3dcded90ebcdadb034a6ea84"
PACKET_REL = Path("artifacts/ens_x_crosswalk/state_audit_20260925/manual_review_packet_60.csv")
RAW_REL = Path("artifacts/ens_x_crosswalk/timeline_expansion_pilot_20260925/raw")
OUT_DIR_REL = Path("artifacts/ens_x_crosswalk/state_audit_20260925/authored_post_review_leads_60")

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def read_csv(path: Path):
    with path.open(newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))

def is_repost(post: dict) -> bool:
    return bool(post.get('retweeted_status') or post.get('reposted_by') or post.get('retweeted')) or post.get('type') in {'retweet','repost'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--packet',type=Path); ap.add_argument('--raw-root',type=Path); ap.add_argument('--out-dir',type=Path)
    a=ap.parse_args(); root=a.project_root.resolve()
    packet=(a.packet or root/PACKET_REL).resolve(); rawroot=(a.raw_root or root/RAW_REL).resolve(); outdir=(a.out_dir or root/OUT_DIR_REL).resolve()
    packet_hash=sha256(packet)
    if packet_hash != EXPECTED_PACKET_SHA256: raise SystemExit(f'frozen packet hash mismatch: {packet_hash}')
    sample=read_csv(packet)
    if len(sample)!=60 or len({(r['address'].lower(),r['x_user_id']) for r in sample})!=60: raise SystemExit('packet must contain 60 unique address/stable-X-ID pairs')
    details_by_key={}; summaries=[]; page_hashes={}; parser_errors=[]
    for r in sample:
        uid=r['x_user_id'].strip(); addr=r['address'].strip().lower(); ens=r['reverse_ens_name'].strip().lower()
        handle=r['handle_at_profile_audit'].strip().lstrip('@').lower(); account_dir=rawroot/handle
        pages=sorted(account_dir.glob('page_*_attempt_*.body')) if account_dir.exists() else []
        page_count=0; id_match_count=0; eligible=0; hit_ids=set(); address_hit_ids=set(); ens_hit_ids=set()
        for page in pages:
            page_count+=1; ph=sha256(page); page_hashes[str(page.relative_to(root))]=ph
            try: payload=json.loads(page.read_text(encoding='utf-8'))
            except Exception as e:
                parser_errors.append({'path':str(page.relative_to(root)),'error':str(e)}); continue
            for post in payload.get('results',[]) or []:
                author=post.get('author') or {}; author_id=str(author.get('id') or '').strip()
                if author_id==uid: id_match_count+=1
                if author_id!=uid or is_repost(post): continue
                eligible+=1; text=str(post.get('text') or ''); terms=[]
                if addr and addr in text.lower(): terms.append(('full_wallet_address',r['address']))
                if ens and ens in text.lower(): terms.append(('reverse_ens_name',r['reverse_ens_name']))
                if not terms: continue
                pid=str(post.get('id') or ''); hit_ids.add(pid)
                for kind,term in terms:
                    if kind=='full_wallet_address': address_hit_ids.add(pid)
                    if kind=='reverse_ens_name': ens_hit_ids.add(pid)
                    key=(uid,pid,kind)
                    if key not in details_by_key:
                        details_by_key[key]={'address':r['address'],'reverse_ens_name':r['reverse_ens_name'],'x_user_id':uid,'handle_at_profile_audit':r['handle_at_profile_audit'],'post_id':pid,'post_url':post.get('url') or '', 'created_at_raw':post.get('created_at') or '', 'created_timestamp':post.get('created_timestamp') or '', 'matched_term_type':kind,'matched_term':term,'authored_text':text,'author_id_in_capture':author_id,'raw_page_relative_path':str(page.relative_to(root)),'raw_page_sha256':ph,'manual_verdict':'pending','review_note':'Exact top-level text occurrence by matching stable author ID; human must assess self-reference, ownership, context, and evidence provenance.'}
        summaries.append({'address':r['address'],'reverse_ens_name':r['reverse_ens_name'],'x_user_id':uid,'handle_at_profile_audit':r['handle_at_profile_audit'],'sample_stratum':r['sampling_stratum'],'design_weight':r['design_weight'],'archived_timeline_pages':page_count,'top_level_posts_by_matching_author_id':id_match_count,'eligible_nonrepost_authored_posts_scanned':eligible,'authored_posts_with_exact_identity_term':len(hit_ids),'unique_exact_wallet_address_post_hits':len(address_hit_ids),'unique_exact_ens_post_hits':len(ens_hit_ids),'status':'candidate_authored_text_lead_pending_human_review' if hit_ids else ('no_exact_self_reference_in_available_captured_pages' if pages else 'no_archived_timeline_pages_for_candidate'),'manual_verdict':'pending'})
    outdir.mkdir(parents=True,exist_ok=True)
    detail_path=outdir/'authored_post_exact_match_leads.csv'; summary_path=outdir/'account_coverage_60.csv'; manifest_path=outdir/'audit_manifest.json'
    def write(path,data):
        with path.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]) if data else []); w.writeheader(); w.writerows(data)
    details=list(details_by_key.values())
    write(detail_path,details); write(summary_path,summaries)
    from collections import Counter
    counts=Counter(x['status'] for x in summaries)
    manifest={'audit_type':'offline_exact_identity_string_scan_in_archived_authored_timeline_posts','created_at_utc':datetime.now(timezone.utc).isoformat(),'network_requests':0,'rpc_requests':0,'database_queries':0,'paid_queries_usd':0,'crosswalk_modified':False,'verdicts_assigned':0,'frozen_packet':str(packet.relative_to(root)),'frozen_packet_sha256':packet_hash,'frozen_pairs':len(sample),'archive_raw_root':str(rawroot.relative_to(root)),'accounts_with_archived_pages':sum(x['archived_timeline_pages']>0 for x in summaries),'accounts_without_archived_pages':sum(x['archived_timeline_pages']==0 for x in summaries),'accounts_with_post_text_leads':sum(x['authored_posts_with_exact_identity_term']>0 for x in summaries),'status_counts':dict(counts),'pages_hashed':len(page_hashes),'source_page_sha256_by_path':page_hashes,'parser_errors':parser_errors,'details_csv':str(detail_path.relative_to(root)),'details_csv_sha256':sha256(detail_path),'summary_csv':str(summary_path.relative_to(root)),'summary_csv_sha256':sha256(summary_path),'interpretation':'Exact string matches in captured top-level post text are navigation leads only. Same stable author ID was required and repost payloads excluded. A match may refer to someone else and is not ownership confirmation. No hit means only absent from available captured pages. All 60 verdicts remain pending.'}
    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['frozen_pairs','accounts_with_archived_pages','accounts_without_archived_pages','accounts_with_post_text_leads','status_counts','pages_hashed','parser_errors','details_csv_sha256','summary_csv_sha256']},indent=2,ensure_ascii=False))
if __name__=='__main__': main()
