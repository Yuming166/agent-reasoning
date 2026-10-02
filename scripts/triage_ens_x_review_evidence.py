#!/usr/bin/env python3
"""Offline evidence-location aid for the frozen ENS-X manual review sample.

This performs exact-string/phrase screening on already archived profile captures.
It does not issue requests, alter the frozen sample, or assign human verdicts.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def read_csv(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def sha(p: Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def norm(s): return (s or "").strip().casefold()
def has_exact(text, term): return bool(term and norm(term) in norm(text))

OWNERSHIP_PATTERNS = [
    ("my_wallet", re.compile(r"\bmy\s+(?:eth(?:ereum)?\s+)?wallet\b", re.I)),
    ("my_address", re.compile(r"\bmy\s+(?:eth(?:ereum)?\s+)?address\b", re.I)),
    ("my_ens", re.compile(r"\bmy\s+ens\b", re.I)),
    ("ens_label", re.compile(r"\bens\s*[:=]\s*", re.I)),
    ("wallet_label", re.compile(r"\bwallet\s*[:=]\s*", re.I)),
    ("address_label", re.compile(r"\baddress\s*[:=]\s*", re.I)),
]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--sample',required=True,type=Path)
    ap.add_argument('--packet',required=True,type=Path)
    ap.add_argument('--out-csv',required=True,type=Path)
    ap.add_argument('--out-json',required=True,type=Path)
    args=ap.parse_args()
    sample=read_csv(args.sample); packet=read_csv(args.packet)
    key=lambda r:(norm(r.get('address')), (r.get('x_user_id') or '').strip())
    s_by={key(r):r for r in sample}; p_by={key(r):r for r in packet}
    if len(sample)!=60 or len(s_by)!=60 or set(s_by)!=set(p_by):
        raise SystemExit('Fail closed: expected exact 60-row sample/packet pair match')
    findings=[]; exact_count=Counter(); phrase_count=Counter(); field_count=Counter()
    for pos,s in enumerate(sample,1):
        p=p_by[key(s)]
        fields={
            'display_name':p.get('captured_display_name',''),
            'bio':p.get('captured_bio_text',''),
            'website_url':p.get('captured_website_url',''),
            'website_display_url':p.get('captured_website_display_url',''),
        }
        ens=s.get('reverse_ens_name',''); addr=s.get('address','')
        ens_fields=[k for k,v in fields.items() if has_exact(v,ens)]
        addr_fields=[k for k,v in fields.items() if has_exact(v,addr)]
        terms=[]
        for fname,text in fields.items():
            for label,pat in OWNERSHIP_PATTERNS:
                if pat.search(text): terms.append(f'{fname}:{label}')
        matched_fields=sorted(set(ens_fields+addr_fields))
        for f in ens_fields: exact_count[f'ens_in_{f}']+=1
        for f in addr_fields: exact_count[f'address_in_{f}']+=1
        for x in terms: phrase_count[x]+=1
        field_count['any_exact_ens_or_address']+=bool(matched_fields)
        if addr_fields: hint='full_candidate_address_visible_in_profile_capture; inspect whether self-claim or third-party context'
        elif ens_fields: hint='candidate_ens_visible_in_profile_capture; inspect self-association context; display-name match alone is insufficient'
        else: hint='no exact candidate ENS/address in captured profile fields; inspect original account posts only if available'
        findings.append({
            'frozen_row_order':pos,'address':addr,'reverse_ens_name':ens,'x_user_id':s.get('x_user_id',''),
            'handle_at_profile_audit':s.get('handle_at_profile_audit',''),
            'sampling_stratum':s.get('sampling_stratum',''),'design_weight':s.get('design_weight',''),
            'events_2026':s.get('events_2026',''),'captured_stable_id_match':p.get('stable_id_match',''),
            'profile_capture_sha256':p.get('raw_profile_sha256_verified',''),
            'exact_ens_fields':';'.join(ens_fields),'exact_address_fields':';'.join(addr_fields),
            'ownership_phrase_locations':';'.join(terms),
            'display_name':fields['display_name'],'bio_text':fields['bio'],
            'website_url':fields['website_url'],'website_display_url':fields['website_display_url'],
            'reviewer_focus_hint':hint,'verdict':'','reviewer':'','reviewed_at_utc':'','evidence_notes':''
        })
    args.out_csv.parent.mkdir(parents=True,exist_ok=True); args.out_json.parent.mkdir(parents=True,exist_ok=True)
    with args.out_csv.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(findings[0])); w.writeheader(); w.writerows(findings)
    result={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'mode':'offline_exact_string_triage_only_no_network_no_collection_no_verdicts',
      'sample':{'path':str(args.sample),'sha256':sha(args.sample),'rows':len(sample)},
      'packet':{'path':str(args.packet),'sha256':sha(args.packet),'rows':len(packet)},
      'output_csv':str(args.out_csv),'output_csv_sha256':sha(args.out_csv),
      'rows':len(findings),'stable_id_matches':sum(r['captured_stable_id_match']=='true' for r in findings),
      'rows_with_any_exact_ens_or_address':sum(bool(r['exact_ens_fields'] or r['exact_address_fields']) for r in findings),
      'exact_string_occurrence_rows':dict(sorted(exact_count.items())),
      'ownership_phrase_presence_rows':dict(sorted(phrase_count.items())),
      'limits':['String presence is not ownership proof.','Display-name-only ENS strings are insufficient under the review protocol.','Website URLs may identify third parties or services; reviewers must inspect context.','This aid assigns no verdict and does not change the frozen sample.']
    }
    args.out_json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
