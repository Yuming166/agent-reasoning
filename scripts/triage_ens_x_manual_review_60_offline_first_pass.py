#!/usr/bin/env python3
"""Create a conservative, offline first-pass aid for the frozen 60 ENS-X pairs.

This does not adjudicate identity, modify the frozen sample, access the network,
or authorize collection. Official manual_verdict is deliberately left blank.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_SAMPLE_SHA256 = "8aedc9e24309052f7a42ce5e7712cf463aeacbfdc5012f00444674b26834e030"
EXPECTED_PACKET_SHA256 = "3825939022b0ec177af4cf2c57624c0a28cbb2cf3dcded90ebcdadb034a6ea84"
PACKET_REL = Path("artifacts/ens_x_crosswalk/state_audit_20260925/manual_review_packet_60.csv")
SAMPLE_REL = Path("artifacts/ens_x_crosswalk/expansion_decision_20260925/candidate_review_stratified_sample_60.csv")
OUT_REL = Path("artifacts/ens_x_crosswalk/state_audit_20260925/offline_first_pass_review_60_20260925.csv")
SUMMARY_REL = Path("artifacts/ens_x_crosswalk/state_audit_20260925/offline_first_pass_review_60_20260925.json")

# Human-readable routing notes for evidence requiring semantic/context review.
# These are leads, not identity verdicts.
SPECIAL = {
    "cindo.eth": (
        "explicit_address_plus_ens_in_bio_review_signature",
        "Profile bio contains the exact candidate address and links to an Etherscan verifySig page and app.ens.domains/cindo.eth. This is the strongest account-side lead in the captured profile, but the signature payload and signer-to-stable-X-ID linkage were not independently checked offline; keep pending.",
        "Human reviewer should inspect the signed message and verify it binds this exact address/ENS to the account owner; archive the attributable evidence and date."
    ),
    "felesof.eth": (
        "explicit_address_plus_ens_in_bio",
        "Profile bio labels `ewm: felesof.eth` and includes the exact candidate address. This is a strong direct self-association lead, but the archived profile snapshot alone is not an independent human verdict and is not historical as-of evidence.",
        "Human reviewer should inspect the live/account-attributable source, record evidence URL/capture and date, then independently adjudicate."
    ),
    "deployer.zerolend.eth": (
        "ens_in_bio_with_explicit_ens_label",
        "Bio says `Creator of @zerolendxyz (ENS: deployer.zerolend.eth)` and the profile links to a Zapper page for that ENS name. This is explicit account-side ENS self-reference, but the address ownership and account identity still require review.",
        "Verify the X account is the relevant creator and that the ENS name resolves to the sampled address; record direct evidence."
    ),
    "samedinoir.eth": (
        "ens_in_bio_self_reference_phrase",
        "Bio ends with `Welcome — samedinoir.eth`, a self-referential account-side name lead; it does not explicitly state wallet ownership.",
        "Check whether an attributable account post/profile explicitly connects this ENS name to the account and sampled address."
    ),
    "steampink.eth": (
        "ens_in_bio_name_only",
        "Bio contains the exact ENS name after general crypto/Web3 self-description; no wallet address or explicit ownership label is present in the captured text.",
        "Seek direct account-side ownership wording or a signed message; otherwise retain ENS-only/pending."
    ),
    "tewshi.eth": (
        "ens_in_bio_name_only",
        "Bio contains `tewshi.eth` and the profile links to a personal-looking website, but the captured bio does not explicitly say the ENS/address is owned by this account.",
        "Inspect the linked site only if an authorized reviewer can document its account attribution; do not infer ownership from string presence."
    ),
    "badtimemachine.eth": (
        "multiple_ens_names_in_bio_context",
        "Bio includes several ENS/domain strings and describes the account as a domainer; the candidate name appears in that context, which may refer to a domain rather than the sampled wallet.",
        "Inspect account-side posts for an explicit wallet/name self-association; distinguish domain promotion from wallet ownership."
    ),
    "efp.eth": (
        "organization_or_protocol_identity_review",
        "Profile identifies as `Ethereum Follow Protocol | efp.eth`; this appears to be an organization/protocol account, so individual wallet ownership cannot be inferred from the name string.",
        "If the project accepts organizational accounts, verify the official account-to-protocol link and the sampled wallet's role separately."
    ),
    "dohmain.eth": (
        "profile_name_mismatch_domain_trader_context",
        "Candidate reverse name is dohmain.eth, while the captured display name is eelonmusk.eth and the bio says the account likes ENS domains and buys/sells them. The sampled address link is on ENS Vision. This raises ambiguity, not a proven conflict.",
        "Check for direct evidence that this stable X ID controls the sampled address/name; do not convert the mismatch into conflict without contrary ownership evidence."
    ),
    "designer.eth": (
        "display_name_match_bio_names_different_ens",
        "Display name is designer.eth, but bio says humanoid.eth; the cached reply praising designer.eth is not a self-ownership statement. Profile website points to a wallet page, which alone does not establish ownership.",
        "Require direct account-side evidence linking designer.eth and the exact sampled wallet; keep the cached praise excluded as confirmation."
    ),
}

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def read_csv(p: Path):
    with p.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',type=Path,default=Path('.'))
    ap.add_argument('--out-csv',type=Path,default=None)
    ap.add_argument('--out-json',type=Path,default=None)
    a=ap.parse_args(); root=a.project_root.resolve()
    sample=root/SAMPLE_REL; packet=root/PACKET_REL
    if sha256(sample)!=EXPECTED_SAMPLE_SHA256: raise SystemExit('frozen sample SHA-256 mismatch; refusing')
    if sha256(packet)!=EXPECTED_PACKET_SHA256: raise SystemExit('manual packet SHA-256 mismatch; refusing')
    samples=read_csv(sample); rows=read_csv(packet)
    if len(samples)!=60 or len(rows)!=60: raise SystemExit('expected exactly 60 frozen rows and packet rows')
    if not rows or 'review_state' not in rows[0]: raise SystemExit('unexpected packet schema')
    if any(r.get('review_state')!='pending_manual_verdict' for r in rows): raise SystemExit('packet is not uniformly pending')
    if len({(r['address'].lower(),r['x_user_id']) for r in rows})!=60: raise SystemExit('duplicate pair keys')
    if len({(r['address'].lower(),r['x_user_id']) for r in samples})!=60: raise SystemExit('duplicate frozen sample keys')
    sample_by_key={(r['address'].lower(),r['x_user_id']):r for r in samples}
    out=[]; cats=Counter()
    for r in rows:
        sr=sample_by_key.get((r['address'].lower(),r['x_user_id']))
        if sr is None: raise SystemExit('packet row absent from frozen sample')
        checks={
          'reverse_ens_name':(r['reverse_ens_name'],sr['reverse_ens_name']),
          'handle':(r['captured_handle'],sr['handle_at_profile_audit']),
          'stratum':(r['sampling_stratum'],sr['sampling_stratum']),
          'design_weight':(r['design_weight'],sr['design_weight']),
          'raw_profile_path':(r['raw_profile_relative_path'],sr['profile_raw_file']),
          'raw_profile_sha256':(r['raw_profile_sha256_expected'],sr['profile_raw_sha256']),
        }
        bad=[k for k,(x,y) in checks.items() if x!=y]
        if bad: raise SystemExit(f'packet/sample mismatch for {r["reverse_ens_name"]}: {bad}')
        address=r['address'].lower(); ens=r['reverse_ens_name']; handle=r['captured_handle']; uid=r['x_user_id']
        raw_rel=r['raw_profile_relative_path']; raw=root/raw_rel
        if not raw.is_file(): raise SystemExit(f'missing raw profile: {raw_rel}')
        raw_hash=sha256(raw)
        if raw_hash != r['raw_profile_sha256_expected'] or raw_hash != r['raw_profile_sha256_verified']:
            raise SystemExit(f'raw profile hash mismatch: {raw_rel}')
        if r['captured_x_user_id'] != uid or r['stable_id_match'] != 'true':
            raise SystemExit(f'stable ID mismatch: {ens} @{handle}')
        bio=r['captured_bio_text'] or ''; display=r['captured_display_name'] or ''; website=r['captured_website_url'] or ''
        blob='\n'.join([display,bio,website]).casefold(); ensc=ens.casefold()
        if ens in SPECIAL:
            category,note,next_step=SPECIAL[ens]
        elif address in bio.casefold():
            category='exact_wallet_in_bio_context_review'
            note='Captured account bio contains the exact candidate address. Presence alone does not establish ownership; inspect wording, neighboring links, and account attribution.'
            next_step='Human reviewer must assess whether the account explicitly presents this as its own wallet; capture direct evidence and date.'
        elif address in website.casefold():
            category='exact_wallet_in_profile_website_link'
            note='Profile website URL contains the exact candidate address on a third-party/site URL. A link chosen by an account may still point to another party or asset; ownership is unproven.'
            next_step='Inspect destination context and independent account-side statement; do not confirm from URL string alone.'
        elif ensc in bio.casefold():
            category='exact_ens_in_bio_context_review'
            note='Captured bio contains the exact candidate ENS name, but no row-specific explicit ownership context was identified in this first pass.'
            next_step='Human reviewer should determine whether wording is self-association or mere mention and seek an explicit wallet link.'
        elif ensc in (r['captured_website_display_url'] or '').casefold() or ensc in website.casefold():
            category='exact_ens_in_profile_website_link'
            note='Candidate ENS appears in a profile website field; the destination/context has not been independently inspected.'
            next_step='Verify destination attribution and whether it ties the ENS to this stable X ID and sampled address.'
        elif ensc in display.casefold():
            category='exact_ens_display_name_only'
            note='Candidate ENS appears in the captured display name only; this is a self-selected label but not sufficient by itself to establish control of the sampled wallet.'
            next_step='Seek an account-side post, bio statement, or signed proof explicitly connecting the stable X ID to this ENS/address.'
        else:
            category='no_usable_account_side_link_in_capture'
            note='No sufficiently direct candidate-to-account evidence identified in the captured profile fields.'
            next_step='Human reviewer may inspect attributable account posts; otherwise keep unverifiable/pending, not negative.'
        cats[category]+=1
        out.append({
          'address':r['address'],'reverse_ens_name':ens,'x_user_id':uid,'captured_handle':handle,
          'sample_stratum':r['sampling_stratum'],'design_weight':r['design_weight'],
          'profile_url':r['profile_url_from_capture'],'profile_snapshot_at_utc':r['profile_snapshot_at_utc'],
          'raw_profile_relative_path':raw_rel,'raw_profile_sha256':raw_hash,
          'evidence_field_excerpt':json.dumps({'display_name':display,'bio':bio,'website_url':website},ensure_ascii=False),
          'offline_first_pass_category':category,'offline_first_pass_note':note,'human_followup':next_step,
          'formal_manual_verdict':'','formal_evidence_url_or_capture_id':'','formal_reviewer':'','formal_reviewed_at_utc':'',
          'status':'AI_offline_first_pass_only_pending_human_review'
        })
    out_csv=a.out_csv or root/OUT_REL; out_json=a.out_json or root/SUMMARY_REL
    out_csv.parent.mkdir(parents=True,exist_ok=True); out_json.parent.mkdir(parents=True,exist_ok=True)
    fields=list(out[0])
    with out_csv.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
    summary={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'mode':'offline_ai_first_pass_navigation_aid_not_human_adjudication',
      'network_requests':0,'paid_queries':0,'collection_resumed':False,
      'frozen_sample_path':str(SAMPLE_REL),'frozen_sample_sha256':sha256(sample),
      'manual_packet_path':str(PACKET_REL),'manual_packet_sha256':sha256(packet),
      'packet_to_sample_pairs_matched':60,
      'rows':len(out),'raw_profile_hashes_verified':len(out),'stable_x_ids_verified':len(out),
      'formal_verdicts_assigned':0,'all_formal_verdicts_blank':all(not r['formal_manual_verdict'] for r in out),
      'candidate_frame_scope':'the 60-row frozen probability sample from the 231 exact-string candidate frame only; no population estimate produced',
      'category_counts':dict(sorted(cats.items())),
      'output_csv':str(out_csv.relative_to(root) if out_csv.is_relative_to(root) else out_csv),
      'output_csv_sha256':sha256(out_csv),
      'limits':['Profile snapshots are account-side captures but are not independent human verdicts.','AI first-pass categories are navigation/prioritization only; no mapping is promoted.','No current-page/network verification or historical as-of inference was performed.','Do not compute weighted confirmation rates from this file.']
    }
    out_json.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
