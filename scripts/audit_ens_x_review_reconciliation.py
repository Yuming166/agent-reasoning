#!/usr/bin/env python3
"""Audit joins between the 231 profile candidates and the frozen 60-row review.

Offline/read-only with respect to source data. Writes a JSON audit report and a
Markdown summary; never promotes candidates or edits the frozen review packet.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('artifacts/ens_x_crosswalk')
FILES = {
    'full_231': BASE / 'expansion_decision_20260925/candidate_review_full_231.csv',
    'frozen_sample_60': BASE / 'expansion_decision_20260925/candidate_review_stratified_sample_60.csv',
    'manual_packet_60': BASE / 'state_audit_20260925/manual_review_packet_60.csv',
    'profile_exact_candidates': BASE / 'profile_expansion_20260925/account_side_exact_match_candidates.csv',
    'evidence_triage_60': BASE / 'state_audit_20260925/manual_review_evidence_triage_60_20260925.csv',
}
KEY = ('address', 'x_user_id')
COMPARE = {
    ('frozen_sample_60', 'full_231'): ('handle_at_profile_audit','reverse_ens_name','events_2026','review_stratum','manual_verdict'),
    ('profile_exact_candidates', 'full_231'): ('handle_at_profile_audit','reverse_ens_name','events_2026','evidence_types','matched_terms','profile_raw_sha256'),
    ('manual_packet_60', 'frozen_sample_60'): ('handle_at_profile_audit','reverse_ens_name','events_2026','sampling_stratum','design_weight'),
    ('evidence_triage_60', 'frozen_sample_60'): ('handle_at_profile_audit','reverse_ens_name','events_2026','sampling_stratum','design_weight'),
}

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def load(path: Path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        if not r.fieldnames or not set(KEY).issubset(r.fieldnames):
            raise ValueError(f'{path}: missing key columns {KEY}')
        rows=list(r)
    keys=[(r['address'].strip().lower(),r['x_user_id'].strip()) for r in rows]
    dup=sorted(k for k,n in Counter(keys).items() if n>1)
    return rows,keys,dup

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',type=Path,default=Path.cwd())
    ap.add_argument('--output-dir',type=Path,default=BASE/'state_audit_20260925')
    a=ap.parse_args(); root=a.project_root.resolve(); out=a.output_dir
    if not out.is_absolute(): out=root/out
    tables={}; report={'generated_at_utc':datetime.now(timezone.utc).isoformat(), 'mode':'offline_review_reconciliation_audit_no_network_no_collection', 'candidate_promotion_performed':False,'files':{},'tables':{},'joins':{},'checks':[]}
    for name,rel in FILES.items():
        p=root/rel; rows,keys,dups=load(p)
        tables[name]=(rows,{k:r for k,r in zip(keys,rows)})
        report['files'][name]={'path':str(rel),'sha256':digest(p),'rows':len(rows)}
        report['tables'][name]={'unique_keys':len(set(keys)),'duplicate_key_count':len(dups),'duplicate_key_examples':[list(x) for x in dups[:5]]}
    for (left,right),fields in COMPARE.items():
        lrows,lidx=tables[left]; rrows,ridx=tables[right]; lk=set(lidx); rk=set(ridx); common=lk&rk
        mismatches={f:sum(lidx[k].get(f,'')!=ridx[k].get(f,'') for k in common) for f in fields}
        report['joins'][f'{left}_vs_{right}']={'left_rows':len(lrows),'right_rows':len(rrows),'matched_keys':len(common),'left_only':len(lk-rk),'right_only':len(rk-lk),'shared_field_mismatch_counts':mismatches}
    full=tables['full_231'][0]; sample=tables['frozen_sample_60'][0]; packet=tables['manual_packet_60'][0]; tri=tables['evidence_triage_60'][0]
    report['status_counts']={
      'full_231_manual_verdict':dict(Counter(r.get('manual_verdict','') or '<blank>' for r in full)),
      'frozen_60_manual_verdict':dict(Counter(r.get('manual_verdict','') or '<blank>' for r in sample)),
      'packet_review_state':dict(Counter(r.get('review_state','') or '<blank>' for r in packet)),
      'triage_verdict':dict(Counter(r.get('verdict','') or '<blank>' for r in tri)),
    }
    report['packet_raw_profile_hash_mismatches']=sum(r.get('raw_profile_sha256_expected','')!=r.get('raw_profile_sha256_verified','') for r in packet)
    report['checks']=[
      {'check':'all five inputs have unique address-stable-X-ID keys','pass':all(v['duplicate_key_count']==0 for v in report['tables'].values())},
      {'check':'231 exact-match candidates are unique and key-identical to full review frame','pass':len(tables['profile_exact_candidates'][1])==231 and set(tables['profile_exact_candidates'][1])==set(tables['full_231'][1])},
      {'check':'frozen 60 sample is a unique subset of 231 frame','pass':len(tables['frozen_sample_60'][1])==60 and set(tables['frozen_sample_60'][1])<=set(tables['full_231'][1])},
      {'check':'manual packet and evidence triage each map one-to-one to frozen 60','pass':set(tables['manual_packet_60'][1])==set(tables['frozen_sample_60'][1])==set(tables['evidence_triage_60'][1])},
      {'check':'shared source fields agree across joins','pass':all(v==0 for j in report['joins'].values() for v in j['shared_field_mismatch_counts'].values())},
      {'check':'raw profile hashes in manual packet verified','pass':report['packet_raw_profile_hash_mismatches']==0},
      {'check':'no manual verdict has been entered in frozen sample','pass':all(not r.get('manual_verdict','').strip() or r.get('manual_verdict')=='pending' for r in sample)},
    ]
    report['overall_pass']=all(x['pass'] for x in report['checks'])
    report['interpretation']='The 60-row review packet is the exact existing stratified sample of the 231-candidate frame. Candidate/profile artifacts reconcile one-to-one; they add evidence material but do not adjudicate identity. Pending rows remain candidates, not confirmed wallet-X links.'
    out.mkdir(parents=True,exist_ok=True)
    jp=out/'profile_candidate_review_reconciliation_20260925.json'; jp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    mp=out/'profile_candidate_review_reconciliation_20260925.md'
    lines=['# Profile-candidate to manual-review reconciliation','',f"Generated UTC: {report['generated_at_utc']}",'','## Result','',report['interpretation'],'',f"Overall integrity checks: **{'PASS' if report['overall_pass'] else 'FAIL'}**.",'','- Candidate promotion performed: **no**.','- Profile exact-match candidate rows: 231; manually reviewed sample rows: 60.','- Frozen sample rows are already represented in the existing packet; no new sample was created.','- Manual verdicts remain pending/blank; no population confirmation-rate estimate is available.','- Raw profile capture hashes in the packet match expected hashes: '+('yes' if report['packet_raw_profile_hash_mismatches']==0 else 'no')+'.','','## Join audit','','| Join | matched keys | left only | right only | shared-field mismatches |','|---|---:|---:|---:|---:|']
    for name,j in report['joins'].items(): lines.append(f"| {name} | {j['matched_keys']} | {j['left_only']} | {j['right_only']} | {sum(j['shared_field_mismatch_counts'].values())} |")
    lines += ['', '## Review state','',f"- Full frame manual verdicts: `{json.dumps(report['status_counts']['full_231_manual_verdict'],ensure_ascii=False)}`",f"- Frozen sample manual verdicts: `{json.dumps(report['status_counts']['frozen_60_manual_verdict'],ensure_ascii=False)}`",f"- Packet review states: `{json.dumps(report['status_counts']['packet_review_state'],ensure_ascii=False)}`",'', '## Input SHA-256','']
    for n,v in report['files'].items(): lines.append(f"- `{v['path']}` ({v['rows']} rows): `{v['sha256']}`")
    lines += ['', '## Checks','']
    for c in report['checks']: lines.append(f"- {'PASS' if c['pass'] else 'FAIL'} — {c['check']}")
    mp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'overall_pass':report['overall_pass'],'report_json':str(jp),'report_md':str(mp),'joins':report['joins'],'status_counts':report['status_counts']},indent=2))
    return 0 if report['overall_pass'] else 1
if __name__=='__main__': raise SystemExit(main())
