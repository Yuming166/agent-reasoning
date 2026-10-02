"""Classify 100-pair verification + weighted confirmation rate.

Rules (per reviewer):
- account exists != confirms. `account_confirms` ONLY if account side shows the
  ENS name (reverse_name / known name) or the ETH address in bio, display name,
  profile URL, or a visible tweet.
- Otherwise: account exists -> ens_only; missing/suspended/protected/fetch fail -> unverifiable.
- Account shows a DIFFERENT address or clearly different primary .eth name -> conflict.
"""
import json, re
from pathlib import Path
import pandas as pd

BASE = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SAMPLE = BASE/'artifacts/ens_x_crosswalk/verification_sample_v2.csv'
PARSED = BASE/'artifacts/ens_x_crosswalk/x_profiles_parsed.jsonl'
FRAME = BASE/'artifacts/ens_x_crosswalk/pairs_stratified_frame.csv'   # pool with strata
OUT = BASE/'artifacts/ens_x_crosswalk/verification_sample_v2_filled.csv'
SUMMARY = BASE/'artifacts/ens_x_crosswalk/verification_report_20260924.md'

VIEW_DATE = '2026-09-24'
ADDR_RE = re.compile(r'0x[a-fA-F0-9]{40}')
ADDR_ABBR_RE = re.compile(r'0x[a-fA-F0-9]{4,8}[.…\- ]{1,3}[a-fA-F0-9]{4,8}\b')
ETHNAME_RE = re.compile(r'\b([a-z0-9\-_]{1,64}(?:\.[a-z0-9\-_]{1,64})*\.eth)\b', re.I)

def texts_of(rec):
    parts = []
    for k in ('x_name', 'description'):
        v = rec.get(k)
        if v: parts.append(('profile_'+k, v))
    for u in (rec.get('profile_urls') or []):
        if u: parts.append(('profile_url', u))
    for t in rec.get('tweets') or []:
        if t.get('full_text'):
            parts.append(('tweet', t['full_text'] + ' || ' + ('https://x.com'+t['permalink'] if t.get('permalink') else '')))
    return parts

def evidence_for(rec, ens_name, address):
    """Return (matched, field, snippet) if account side confirms."""
    ens_l = (ens_name or '').strip().lower()
    addr_l = address.lower()
    addr_pre, addr_suf = addr_l[:8], addr_l[-6:]
    for field, txt in texts_of(rec):
        tl = txt.lower()
        if addr_l in tl:
            return True, field, 'full address: '+txt[:160]
        # abbreviated address form 0x1234…abcd
        if addr_pre in tl and addr_suf in tl:
            return True, field, 'abbreviated address: '+txt[:160]
        if ens_l and ens_l in tl:
            return True, field, 'ens name: '+txt[:160]
    return False, None, None

def conflict_check(rec, ens_name, address):
    addr_l = address.lower()
    found_addrs, found_names = set(), set()
    for field, txt in texts_of(rec):
        found_addrs.update(a.lower() for a in ADDR_RE.findall(txt))
        found_names.update(n.lower() for n in ETHNAME_RE.findall(txt))
    other_addrs = found_addrs - {addr_l}
    ens_l = (ens_name or '').strip().lower()
    other_names = found_names - {ens_l} if ens_l else found_names
    return sorted(other_addrs), sorted(other_names)

def main():
    df = pd.read_csv(SAMPLE)
    recs = {}
    with open(PARSED) as f:
        for line in f:
            r = json.loads(line)
            recs[r['handle'].lower()] = r
    fx = {}
    with open(BASE/'artifacts/ens_x_crosswalk/fx_profiles_parsed.jsonl') as f:
        for line in f:
            r = json.loads(line)
            fx[r['handle'].lower()] = r
    pool = pd.read_csv(FRAME)
    val = pd.read_csv(BASE/'artifacts/ens_x_crosswalk/bidirectional_validation.csv')
    pool = pool.merge(val[['address','handle','status']], on=['address','handle'], how='left')
    statuses, exists, notes, uids, evdates = [], [], [], [], []
    for _, row in df.iterrows():
        h = str(row['handle']).lower()
        rec = dict(recs.get(h, {}))
        f = fx.get(h, {})
        # merge fxtwitter bio fields as additional evidence sources
        if f.get('fx_user_id'):
            rec.setdefault('x_user_id', f.get('fx_user_id'))
            if not rec.get('x_user_id'): rec['x_user_id'] = f.get('fx_user_id')
            for k in ('x_name','description'):
                if not rec.get(k): rec[k] = f.get(k)
            extra = [u for u in (f.get('profile_url'), f.get('banner_website')) if u]
            rec['profile_urls'] = (rec.get('profile_urls') or []) + extra
            rec.setdefault('followers_count', f.get('followers'))
            if not rec.get('screen_name'): rec['screen_name'] = f.get('screen_name')
            rec['_fx_ok'] = True
        ens = row['reverse_name'] if pd.notna(row['reverse_name']) else ''
        addr = row['address']
        err = rec.get('error')
        no_user = not rec.get('x_user_id')
        if no_user:
            exists.append('no_or_unknown')
            statuses.append('unverifiable')
            notes.append('account not resolvable on 2026-09-24 (syndication: %s; fxtwitter: %s)' % (err or rec.get('http_status'), f.get('error') or f.get('http_status')))
            uids.append(''); evdates.append(VIEW_DATE); continue
        uids.append(rec.get('x_user_id',''))
        exists.append('yes' if not rec.get('protected') else 'yes_protected')
        matched, field, snippet = evidence_for(rec, ens, addr)
        o_addrs, o_names = conflict_check(rec, ens, addr)
        if matched:
            statuses.append('account_confirms')
            notes.append(f'{field} matched ({snippet}) | x_user_id={rec.get("x_user_id")} | https://x.com/{rec.get("screen_name")}')
        elif o_addrs:
            statuses.append('conflict')
            notes.append(f'bio/urls show different address(es): {o_addrs[:2]} (may be token/contract addr; manual review advised) | x_user_id={rec.get("x_user_id")}')
        elif o_names and row['status']=='forward_only':
            # forward_only pairs have no confirmed name; different .eth shown is a failure-type signal
            statuses.append('ens_only')
            notes.append(f'account exists; shows .eth name(s) {o_names[:3]} but no on-chain match evidence | x_user_id={rec.get("x_user_id")}')
        else:
            statuses.append('ens_only')
            notes.append(f'account exists (followers={rec.get("followers_count")}); no address/ENS name visible | x_user_id={rec.get("x_user_id")}' + (f'; other names seen {o_names[:3]}' if o_names else ''))
        evdates.append(VIEW_DATE)
    df['x_account_exists'] = exists
    df['verification_status'] = statuses
    df['evidence_date'] = evdates
    df['evidence_note'] = notes
    df['x_user_id'] = uids
    df.to_csv(OUT, index=False)

    # ---- weighted confirmation rate for bidirectional_ok sample ----
    ok = df[df.status=='bidirectional_ok'].copy()
    ok['skey'] = list(zip(ok.recency, ok.activity, ok.multiplicity))
    pool_ok = pool[pool['status']=='bidirectional_ok'].copy()
    assert len(pool_ok)==12461, len(pool_ok)
    pool_ok['skey'] = list(zip(pool_ok.recency, pool_ok.activity, pool_ok.multiplicity))
    pool_counts = pool_ok.groupby('skey').size()
    samp_counts = ok.groupby('skey').size()
    ok['w'] = ok['skey'].map(lambda k: pool_counts.get(k, 0) / max(samp_counts.get(k, 1), 1))
    w_conf = ok.loc[ok.verification_status=='account_confirms','w'].sum()
    w_tot = ok['w'].sum()
    print('=== bidirectional_ok (71) ===')
    print(ok['verification_status'].value_counts())
    print(f'unweighted confirms: {(ok.verification_status=="account_confirms").sum()}/71')
    print(f'weighted confirms share: {w_conf/w_tot:.4f} (pool N={int(pool_counts.sum())}, weights normalized sum={w_tot:.1f})')
    print('=== forward_only (29) ===')
    print(df[df.status=='forward_only']['verification_status'].value_counts())
    print('=== x_account_exists overall ===')
    print(df['x_account_exists'].value_counts())
    df.to_csv(OUT, index=False)

if __name__ == '__main__':
    main()
