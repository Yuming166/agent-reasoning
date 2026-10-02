#!/usr/bin/env python3
"""Build a leakage-aware wallet x cutoff influencer-text coverage matrix.

The match is deliberately narrow: a post entity is relevant only when its
normalized label matches a symbol in the frozen local token_map.csv and the
wallet has a pre-cutoff event for that exact contract.  No fuzzy symbol or
wallet-author inference is performed.
"""
from __future__ import annotations
import csv, hashlib, json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / 'data/raw/crypto_influencer_v5/dataset_52-person-from-2021-02-05_2023-06-12_21-34-17-266_with_sentiment.csv'
ENTITIES = ROOT / 'artifacts/influencer_context_audit_20260928/normalized_entities.csv'
CASES = ROOT / 'artifacts/motif_hypothesis_eventlevel_20260927/cases.jsonl'
EVENTS = ROOT / 'artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl'
TOKEN_MAP = ROOT / 'data/raw/prices/token_map.csv'
BASE_OUT = ROOT / 'artifacts/influencer_coverage_matrix_20260928_run04'

# Match the audit's frozen aliases plus symbols in the local contract map.
ALIASES = {
    'btc':'bitcoin','xbt':'bitcoin','bitcoin':'bitcoin', 'eth':'ethereum','ethereum':'ethereum',
    'weth':'weth','avax':'avalanche','avalanche':'avalanche','usdc':'usdc','usdt':'usdt',
    'dai':'dai','ape':'ape','looks':'looks','wool':'wool','strong':'strong','strngr':'strngr','ash':'ash',
    'matic':'polygon','polygon':'polygon','arb':'arbitrum','arbitrum':'arbitrum','op':'optimism','optimism':'optimism',
    'bnb':'binance_coin','binance':'binance_coin','sol':'solana','solana':'solana','doge':'dogecoin','dogecoin':'dogecoin',
    'ada':'cardano','cardano':'cardano','xrp':'xrp','dot':'polkadot','polkadot':'polkadot','link':'chainlink','chainlink':'chainlink',
    'uni':'uniswap','uniswap':'uniswap','ltc':'litecoin','litecoin':'litecoin','shib':'shiba_inu','shiba':'shiba_inu',
    'atom':'cosmos','cosmos':'cosmos','near':'near','ftm':'fantom','fantom':'fantom','trx':'tron','tron':'tron'
}

def sha256(p: Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def write_csv(p, rows, fields):
    with p.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def normalize(s):
    s=re.sub(r'[^a-z0-9_-]+','',str(s).lower().strip())
    return ALIASES.get(s,s) if s else ''

def parse_timestamp(s):
    return pd.Timestamp(s, tz='UTC')

def main():
    if BASE_OUT.exists():
        raise SystemExit(f'refusing to overwrite existing run directory: {BASE_OUT}')
    BASE_OUT.mkdir(parents=True)
    token = pd.read_csv(TOKEN_MAP, dtype=str)
    token['address'] = token.token_contract_address.str.lower()
    token['canonical_entity'] = token.symbol.map(normalize)
    token = token.drop_duplicates('address')
    map_by_entity = defaultdict(list)
    for r in token.itertuples(): map_by_entity[r.canonical_entity].append(r.address)

    # Use the full source history here, not only the June-August audit slice.
    # The coverage question is explicitly how much text was available before
    # each cutoff; restricting to the audit slice would make the June cutoff
    # artificially empty.
    src = pd.read_csv(POSTS, dtype={'created_at': str, 'new_coins': str})
    src['created_at_utc'] = pd.to_datetime(src['created_at'], utc=True)
    entity_rows = []
    for i, row in src.iterrows():
        raw = str(row.get('new_coins') or '').strip().strip('()[]{} ')
        for part in re.split(r'[,;|/]', raw):
            token_raw = re.sub(r'[^a-z0-9_-]+', '', part.strip().lower())
            if not token_raw:
                continue
            canonical = normalize(token_raw)
            entity_rows.append({'source_row': int(i), 'created_at_utc': row.created_at_utc, 'raw_entity': token_raw, 'canonical_entity': canonical})
    entities = pd.DataFrame(entity_rows)
    entities['matched_contracts'] = entities.canonical_entity.map(lambda x: '|'.join(map_by_entity.get(x, [])))
    entities['has_contract_mapping'] = entities.matched_contracts.ne('')
    entities['week_start_utc'] = entities.created_at_utc.map(lambda t: (t - pd.Timedelta(days=int(t.weekday()))).normalize())

    cases=[]
    with CASES.open() as f:
        for line in f:
            if line.strip(): cases.append(json.loads(line))
    case_df=pd.DataFrame([{'case_id':x['case_id'],'wallet':x['wallet'].lower(),'cutoff':x['cutoff'],'split':x['split']} for x in cases])
    case_df['cutoff_utc']=pd.to_datetime(case_df.cutoff, utc=True)

    # Exact contract history, strictly before cutoff, grouped by wallet.
    wallet_contract_events=defaultdict(list)
    event_rows=0
    with EVENTS.open() as f:
        for line in f:
            if not line.strip(): continue
            x=json.loads(line); event_rows+=1
            wallet=str(x.get('target_address') or '').lower()
            contract=str(x.get('token_contract_address') or '').lower()
            if wallet and contract: wallet_contract_events[wallet].append((parse_timestamp(x['block_timestamp']), contract))

    matrix=[]
    matched_pair_rows=[]
    for r in case_df.itertuples(index=False):
        cutoff=r.cutoff_utc
        hist_contracts={c for t,c in wallet_contract_events.get(r.wallet,[]) if t < cutoff}
        mapped_hist={c for c in hist_contracts if c in set(token.address)}
        pre=entities[entities.created_at_utc < cutoff]
        recent=pre[(pre.created_at_utc >= cutoff-pd.Timedelta(days=30))]
        def summarize(g):
            matched=g[g.has_contract_mapping & g.matched_contracts.map(lambda s: bool(set(str(s).split('|')) & mapped_hist if s else False)).astype(bool)]
            # Distinct source texts are identified by source_row from the frozen source.
            for x in matched.itertuples(index=False):
                matched_pair_rows.append({'case_id': r.case_id, 'wallet': r.wallet, 'cutoff': r.cutoff, 'scope': current_scope, 'source_row': int(x.source_row), 'created_at_utc': x.created_at_utc.isoformat(), 'canonical_entity': x.canonical_entity})
            return {
                'posts': int(g.source_row.nunique()),
                'weeks': int(g.week_start_utc.dt.date.nunique()),
                'entities': int(g.canonical_entity[g.canonical_entity.ne('')].nunique()),
                'mapped_posts': int(matched.source_row.nunique()),
                'mapped_weeks': int(matched.week_start_utc.dt.date.nunique()),
                'mapped_entities': int(matched.canonical_entity.nunique()),
                'mapped_post_rows': int(len(matched)),
            }
        current_scope='pre_cutoff'; a=summarize(pre)
        current_scope='last30d'; b=summarize(recent)
        matrix.append({'case_id':r.case_id,'wallet':r.wallet,'cutoff':r.cutoff,'split':r.split,'history_contracts_total':len(hist_contracts),'history_contracts_in_frozen_map':len(mapped_hist),
                       'pre_cutoff_posts':a['posts'],'pre_cutoff_weeks':a['weeks'],'pre_cutoff_entities':a['entities'],'pre_cutoff_mapped_posts':a['mapped_posts'],'pre_cutoff_mapped_weeks':a['mapped_weeks'],'pre_cutoff_mapped_entities':a['mapped_entities'],'pre_cutoff_mapped_entity_rows':a['mapped_post_rows'],
                       'last30d_posts':b['posts'],'last30d_weeks':b['weeks'],'last30d_entities':b['entities'],'last30d_mapped_posts':b['mapped_posts'],'last30d_mapped_weeks':b['mapped_weeks'],'last30d_mapped_entities':b['mapped_entities'],'last30d_mapped_entity_rows':b['mapped_post_rows']})
    fields=list(matrix[0]); write_csv(BASE_OUT/'wallet_cutoff_coverage.csv', matrix, fields)
    write_csv(BASE_OUT/'matched_wallet_post_links.csv', matched_pair_rows, ['case_id','wallet','cutoff','scope','source_row','created_at_utc','canonical_entity'])

    mdf=pd.DataFrame(matrix)
    summary=[]
    for cutoff,g in mdf.groupby('cutoff', sort=True):
        for scope in ('pre_cutoff','last30d'):
            post_col=f'{scope}_mapped_posts'; week_col=f'{scope}_mapped_weeks'; ent_col=f'{scope}_mapped_entities'
            links=pd.DataFrame([x for x in matched_pair_rows if x['cutoff']==cutoff and x['scope']==scope])
            summary.append({'cutoff':cutoff,'scope':scope,'wallet_cutoffs':len(g),'wallets_with_any_mapped_text':int((g[post_col]>0).sum()),'wallet_coverage_rate':round(float((g[post_col]>0).mean()),6),'mapped_post_count_sum':int(g[post_col].sum()),'mapped_post_count_mean':round(float(g[post_col].mean()),6),'mapped_post_count_median':float(g[post_col].median()),'mapped_weeks_sum':int(g[week_col].sum()),'wallet_cutoff_rows_with_any_mapped_week':int((g[week_col]>0).sum()),'mapped_entity_count_sum':int(g[ent_col].sum()),'wallet_cutoff_rows_with_any_mapped_entity':int((g[ent_col]>0).sum()),'distinct_matched_posts_global':int(links.source_row.nunique()) if len(links) else 0,'distinct_matched_weeks_global':int(pd.to_datetime(links.created_at_utc,utc=True).dt.tz_localize(None).dt.to_period('W-MON').nunique()) if len(links) else 0,'distinct_matched_entities_global':int(links.canonical_entity.nunique()) if len(links) else 0,'history_contracts_in_map_mean':round(float(g.history_contracts_in_frozen_map.mean()),6)})
    write_csv(BASE_OUT/'cutoff_coverage_summary.csv', summary, list(summary[0]))

    # Overall and entity-level diagnostics.
    mapped_entity_rows=entities[entities.has_contract_mapping].copy()
    write_csv(BASE_OUT/'mapped_text_entity_summary.csv', [
        {'canonical_entity': e, 'post_count': int(g.source_row.nunique()), 'mention_rows': int(len(g)), 'first_post_utc': g.created_at_utc.min().isoformat(), 'last_post_utc': g.created_at_utc.max().isoformat(), 'contract_count': len(map_by_entity[e]), 'contract_addresses': '|'.join(map_by_entity[e])}
        for e,g in mapped_entity_rows.groupby('canonical_entity', sort=True)
    ], ['canonical_entity','post_count','mention_rows','first_post_utc','last_post_utc','contract_count','contract_addresses'])

    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS','run_directory':str(BASE_OUT),'source_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in [POSTS,ENTITIES,CASES,EVENTS,TOKEN_MAP]},'cases':len(matrix),'unique_wallets':int(mdf.wallet.nunique()),'cutoffs':sorted(mdf.cutoff.unique()),'event_rows_scanned':event_rows,'frozen_contract_map_rows':len(token),'frozen_contract_map_symbols':sorted(token.canonical_entity.unique()),'matched_text_entities':sorted(mapped_entity_rows.canonical_entity.unique()),'ethereum_diagnostic':{'distinct_source_posts_all_time':int(src.index[src.new_coins.fillna('').str.lower().str.contains(r'ethereum|eth',regex=True)].nunique()),'distinct_entity_rows_all_time':int((entities.canonical_entity=='ethereum').sum()),'distinct_focus_posts_2022_06_08':int(entities[(entities.canonical_entity=='ethereum') & (entities.created_at_utc>=pd.Timestamp('2022-06-01',tz='UTC')) & (entities.created_at_utc<pd.Timestamp('2022-09-01',tz='UTC'))].source_row.nunique()),'distinct_focus_posts_raw_eth_2022_06_08':int(entities[(entities.raw_entity=='eth') & (entities.created_at_utc>=pd.Timestamp('2022-06-01',tz='UTC')) & (entities.created_at_utc<pd.Timestamp('2022-09-01',tz='UTC'))].source_row.nunique()),'distinct_focus_posts_raw_ethereum_2022_06_08':int(entities[(entities.raw_entity=='ethereum') & (entities.created_at_utc>=pd.Timestamp('2022-06-01',tz='UTC')) & (entities.created_at_utc<pd.Timestamp('2022-09-01',tz='UTC'))].source_row.nunique()),'matched_to_frozen_contract':False},'matching_rule':'strict normalized entity -> frozen token_map symbol -> exact wallet pre-cutoff token_contract_address','time_rule':'post created_at strictly before cutoff; chain block_timestamp strictly before cutoff','author_crosswalk_used':False,'causal_claim':False,'note':'This is coverage only; no predictive result or wallet exposure/reading claim.'}
    (BASE_OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    report=f'''# Wallet x cutoff influencer-text coverage matrix\n\n## Frozen matching rule\n\nA post is counted as wallet-history-relevant only if its normalized entity matches a symbol in `data/raw/prices/token_map.csv` and the wallet has an event with that exact contract address strictly before the cutoff. No fuzzy matching, author crosswalk, or causal interpretation is used.\n\n## Output\n\n- `wallet_cutoff_coverage.csv`: one row for each wallet x cutoff case ({len(matrix)} rows).\n- `cutoff_coverage_summary.csv`: per-cutoff coverage, separately for all pre-cutoff posts and the trailing 30-day window.\n- `mapped_text_entity_summary.csv`: mapped entity/post counts and contract provenance.
- `matched_wallet_post_links.csv`: the exact wallet-cutoff-to-post links used in the summary.\n- `manifest.json`: source hashes and matching policy.\n\n## Important boundary\n\nThe current chain window and the influencer data are only being aligned by exact contract mapping. Native `ethereum` text is not counted as matched unless a corresponding frozen contract mapping exists; an `ethereum` mention alone does not establish a wallet-asset match. This artifact therefore tests whether coverage is sufficient before launching the four-arm residual experiment.\n\n**Status: coverage experiment complete; predictive/LLM integration not yet run.**\n'''
    (BASE_OUT/'REPORT.md').write_text(report)
    print(json.dumps({'output':str(BASE_OUT),'rows':len(matrix),'wallets':int(mdf.wallet.nunique()),'cutoffs':sorted(mdf.cutoff.unique()),'status':'PASS'},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
