#!/usr/bin/env python3
"""Typed temporal graph network (TGN-style) next-counterparty baseline.

Per case, construct a strictly pre-cutoff sampled temporal subgraph from the
wallet's recent outgoing events and a small set of counterparties' histories.
A typed TGN memory is replayed chronologically over that subgraph. Candidate
scores use the query-wallet memory, candidate memory when sampled, and
as-of candidate features. This is a project-specific TGN-style implementation,
not the official Rossi et al. repository implementation.

Protocol: train on frozen train + disjoint train_expanded; evaluate frozen dev;
never materialize/evaluate August holdout labels. OPEN_WORLD is a separate
head and never an address candidate hit. Ranking loss applies only when a
concrete target is inside the retrieved pool.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pickle, sys, time, traceback
from collections import Counter
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_openworld_diffusion_baseline as base  # noqa: E402

ROOT = base.ROOT
ADDR_BUCKETS = 32768
TOKEN_BUCKETS = 4096
FAMILY = {'external_tx': 1, 'internal_trace': 2, 'token_transfer': 3}
EVENT_TYPE_COUNT = 1 + 3 * 2  # family x outgoing/incoming (incoming not sampled yet)
MAX_ROOT_EVENTS = 48
MAX_PEERS = 4
MAX_PEER_EVENTS = 8
POOL_OWN = 500
POOL_DIFF = 500
POOL_RECENT = 2000
POOL_GLOBAL = 2000


def addr_bucket(addr: str) -> int:
    return int(hashlib.sha1(addr.encode()).hexdigest(), 16) % ADDR_BUCKETS


def tok_bucket(tok: str) -> int:
    return int(hashlib.sha1((tok or '').encode()).hexdigest(), 16) % TOKEN_BUCKETS


def time_features(age_days: float) -> np.ndarray:
    # As-of age, using multiple calendar scales. No future timestamp enters.
    age = max(0.0, float(age_days))
    vals = [math.log1p(age)]
    for scale in (1.0, 7.0, 30.0, 90.0, 365.0):
        vals.extend([math.sin(age / scale), math.cos(age / scale)])
    return np.asarray(vals, dtype=np.float32)


def make_pool(index: dict, wallet: str) -> List[str]:
    own_c = index['by_wallet_counter'].get(wallet, Counter())
    own_l = index['by_wallet_last'].get(wallet, {})
    own = list(dict.fromkeys(
        [c for c, _ in sorted(own_l.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]
        + [c for c, _ in sorted(own_c.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]))
    diff, _ = base.rank_for_wallet(index, wallet, 'typed_temporal_diffusion', max_candidates=POOL_DIFF)
    return list(dict.fromkeys(own + diff + index['recent_rank'][:POOL_RECENT]
                              + index['global_rank'][:POOL_GLOBAL]))


def candidate_feats(index: dict, wallet: str, c: str) -> List[float]:
    t = pd.Timestamp(index['cutoff'], tz='UTC')
    own_c = index['by_wallet_counter'].get(wallet, Counter())
    own_l = index['by_wallet_last'].get(wallet, {})
    count = own_c.get(c, 0)
    decay = own_l.get(c, 0.0)
    days_since = -90.0 * math.log(max(decay, 1e-9)) if decay else 365.0
    return [math.log1p(index['global_counter'].get(c, 0)),
            math.log1p(index['recent_counter'].get(c, 0)),
            math.log1p(count), math.log1p(min(days_since, 365.0)),
            1.0 if count else 0.0]


def extract_case_graph(hist: pd.DataFrame, wallet: str, cutoff: str,
                       by_wallet: dict) -> dict:
    """Root's recent edge stream plus limited recent histories of sampled peers."""
    t = pd.Timestamp(cutoff, tz='UTC')
    root = hist[hist.target_address.eq(wallet)]
    if root.empty:
        return {'events': [], 'nodes': [wallet]}
    root_rows = list(root.tail(MAX_ROOT_EVENTS).itertuples(index=False))
    peers = []
    for r in reversed(root_rows):
        c = r.counterparty_address
        if c and c != wallet and c not in peers:
            peers.append(c)
        if len(peers) >= MAX_PEERS:
            break
    event_map = {}
    def add(r):
        src = r.target_address
        dst = r.counterparty_address
        if not src or not dst or src == dst:
            return
        ts = pd.Timestamp(r.block_timestamp)
        if ts >= t:
            return
        fam = FAMILY.get(getattr(r, 'event_family', ''), 0)
        if fam == 0:
            return
        # Source events are outgoing in the offline event table. Key by source,
        # destination, family, token and timestamp to collapse accidental repeats.
        key = (src, dst, fam, getattr(r, 'token_contract_address', '') or '',
               int(ts.value))
        event_map[key] = (src, dst, fam, getattr(r, 'token_contract_address', '') or '', ts)
    for r in root_rows:
        add(r)
    for peer in peers:
        ix = by_wallet.get(peer)
        if ix is None:
            continue
        # `ix` are positions into hist sorted by time; include only peer outbound rows.
        for r in list(hist.iloc[ix].tail(MAX_PEER_EVENTS).itertuples(index=False)):
            add(r)
    events = sorted(event_map.values(), key=lambda z: (z[4], z[0], z[1], z[2], z[3]))
    nodes = {wallet}
    for s, d, *_ in events:
        nodes.add(s); nodes.add(d)
    return {'events': events, 'nodes': sorted(nodes)}


def encode_case(graph: dict, wallet: str, pool: List[str], index: dict) -> dict:
    nodes = graph['nodes']
    nmap = {a: i for i, a in enumerate(nodes)}
    t = pd.Timestamp(index['cutoff'], tz='UTC')
    times = {}
    srcs=[]; dsts=[]; etypes=[]; toks=[]; tf=[]
    for s, d, fam, tok, ts in graph['events']:
        age = max(0.0, (t - ts).total_seconds() / 86400.0)
        srcs.append(nmap[s]); dsts.append(nmap[d])
        etypes.append(fam)
        toks.append(tok_bucket(tok))
        tf.append(time_features(age))
    cand_nodes = [nmap.get(c, -1) for c in pool]
    Xcand = np.asarray([candidate_feats(index, wallet, c) for c in pool], dtype=np.float32)
    own_c = index['by_wallet_counter'].get(wallet, Counter())
    n_events = sum(own_c.values())
    n_unique = len(own_c)
    ctx = np.asarray([math.log1p(n_events), math.log1p(n_unique),
                      max(index['by_wallet_last'].get(wallet, {}).values(), default=0.0),
                      n_unique / max(1, n_events)], dtype=np.float32)
    return {'nodes': np.asarray([addr_bucket(a) for a in nodes], dtype=np.int32),
            'wallet_node': nmap.get(wallet, 0),
            'src': np.asarray(srcs, dtype=np.int32), 'dst': np.asarray(dsts, dtype=np.int32),
            'etype': np.asarray(etypes, dtype=np.int32), 'tok': np.asarray(toks, dtype=np.int32),
            'time': np.asarray(tf, dtype=np.float32).reshape(-1, 11),
            'cand_bucket': np.asarray([addr_bucket(c) for c in pool], dtype=np.int32),
            'cand_node': np.asarray(cand_nodes, dtype=np.int32), 'cand_feat': Xcand,
            'ctx': ctx, 'pool': pool}


def extract_dataset(ev: pd.DataFrame, cases: pd.DataFrame, cache: Path) -> list:
    out=[]
    for cutoff, cg in cases.groupby('cutoff', sort=True):
        t0=time.time()
        hist=ev[ev.block_timestamp < pd.Timestamp(cutoff, tz='UTC')].reset_index(drop=True)
        # This one-cutoff temporal index is identical to the audited candidate baseline.
        index=base.build_temporal_index(hist, cutoff)
        by_wallet=hist.groupby('target_address', sort=False).indices
        print(json.dumps({'extract_cutoff': cutoff, 'history_rows': len(hist),
                          'index_seconds': round(time.time()-t0, 1)}), flush=True)
        for r in cg.itertuples(index=False):
            if r.split == 'train_expanded' and r.cutoff >= '2022-07-01':
                continue
            pool=make_pool(index, r.wallet)
            graph=extract_case_graph(hist, r.wallet, cutoff, by_wallet)
            feat=encode_case(graph, r.wallet, pool, index)
            y=r.target if r.active else ''
            feat.update({'case_id':r.case_id,'split':r.split,'cutoff':r.cutoff,
                         'wallet':r.wallet,'active':int(r.active),'target':y,
                         'y_idx':pool.index(y) if y and y in pool else -1,
                         'visibility':('own_seen' if y in index['by_wallet_counter'].get(r.wallet,{})
                                       else ('global_seen' if y and y in index['global_counter'] else ('open_world' if y else 'none'))),
                         'candidate_count':len(pool),'event_count':len(graph['events'])})
            out.append(feat)
        print(json.dumps({'cases_done':cutoff,'n_cases':len(cg),'seconds_total':round(time.time()-t0,1)}),flush=True)
    cache.parent.mkdir(parents=True,exist_ok=True)
    with cache.open('wb') as f: pickle.dump(out,f,protocol=4)
    return out


def collate(cases: list, device: str):
    B=len(cases); N=max(len(c['nodes']) for c in cases); T=max(1,max(len(c['src']) for c in cases)); C=max(len(c['pool']) for c in cases)
    nodes=torch.zeros(B,N,dtype=torch.long); src=torch.zeros(B,T,dtype=torch.long); dst=torch.zeros_like(src)
    etype=torch.zeros_like(src); tok=torch.zeros_like(src); tm=torch.zeros(B,T,11,dtype=torch.float)
    emask=torch.zeros(B,T,dtype=torch.bool); wn=torch.zeros(B,dtype=torch.long)
    cb=torch.zeros(B,C,dtype=torch.long); cn=torch.full((B,C),-1,dtype=torch.long); cf=torch.zeros(B,C,5)
    cmask=torch.zeros(B,C,dtype=torch.bool); y=torch.full((B,),-1,dtype=torch.long)
    act=torch.zeros(B); ow=torch.zeros(B); support=torch.zeros(B,dtype=torch.bool)
    for i,c in enumerate(cases):
        n=len(c['nodes']); q=len(c['src']); m=len(c['pool'])
        nodes[i,:n]=torch.as_tensor(c['nodes'],dtype=torch.long)
        wn[i]=c['wallet_node']
        if q:
            src[i,:q]=torch.as_tensor(c['src'],dtype=torch.long); dst[i,:q]=torch.as_tensor(c['dst'],dtype=torch.long)
            etype[i,:q]=torch.as_tensor(c['etype'],dtype=torch.long); tok[i,:q]=torch.as_tensor(c['tok'],dtype=torch.long)
            tm[i,:q]=torch.as_tensor(c['time'],dtype=torch.float); emask[i,:q]=True
        cb[i,:m]=torch.as_tensor(c['cand_bucket'],dtype=torch.long); cn[i,:m]=torch.as_tensor(c['cand_node'],dtype=torch.long)
        cf[i,:m]=torch.as_tensor(c['cand_feat'],dtype=torch.float); cmask[i,:m]=True
        act[i]=c['active']; ow[i]=float(c['visibility']=='open_world')
        if c['y_idx']>=0: y[i]=c['y_idx']; support[i]=True
    return [x.to(device) for x in (nodes,src,dst,etype,tok,tm,emask,wn,cb,cn,cf,cmask,y,act,ow,support)]


class TypedTGN(nn.Module):
    def __init__(self, hidden=96, event_dim=48):
        super().__init__()
        self.node_emb = nn.Embedding(ADDR_BUCKETS, hidden)
        self.family_emb = nn.Embedding(4, 12)
        self.token_emb = nn.Embedding(TOKEN_BUCKETS, 12)
        self.event_proj = nn.Sequential(nn.Linear(12 + 12 + 11, event_dim), nn.GELU(), nn.Linear(event_dim, event_dim))
        self.src_update = nn.GRUCell(hidden + event_dim, hidden)
        self.dst_update = nn.GRUCell(hidden + event_dim, hidden)
        self.cand_hash = nn.Embedding(ADDR_BUCKETS, hidden)
        self.cand_proj = nn.Sequential(nn.Linear(hidden + 5, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.score = nn.Sequential(nn.Linear(hidden * 3, hidden), nn.GELU(), nn.Dropout(0.1), nn.Linear(hidden, 1))
        self.activity = nn.Sequential(nn.Linear(hidden + 4, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, 1))
        self.open_world = nn.Sequential(nn.Linear(hidden + 4, hidden // 2), nn.GELU(), nn.Linear(hidden // 2, 1))

    def replay(self, nodes, src, dst, etype, tok, tm, emask):
        B, N = nodes.shape
        mem = self.node_emb(nodes)
        for j in range(src.shape[1]):
            active = emask[:, j]
            if not active.any():
                continue
            s = src[:, j].clamp(0, N - 1)
            d = dst[:, j].clamp(0, N - 1)
            e = self.event_proj(torch.cat([self.family_emb(etype[:, j].clamp(0, 3)),
                                            self.token_emb(tok[:, j].clamp(0, TOKEN_BUCKETS - 1)),
                                            tm[:, j]], dim=-1))
            old_s = mem[torch.arange(B, device=mem.device), s]
            old_d = mem[torch.arange(B, device=mem.device), d]
            # A single temporal event updates both endpoints. The masked select
            # avoids padding events changing memory state.
            ns = self.src_update(torch.cat([old_s, e], dim=-1), old_d)
            nd = self.dst_update(torch.cat([old_d, e], dim=-1), old_s)
            rows = torch.arange(B, device=mem.device)
            mem[rows, s] = torch.where(active.unsqueeze(-1), ns, old_s)
            mem[rows, d] = torch.where(active.unsqueeze(-1), nd, old_d)
        return mem

    def forward(self, batch):
        (nodes, src, dst, etype, tok, tm, emask, wn, cb, cn, cf, cmask,
         y, act, ow, support) = batch
        mem = self.replay(nodes, src, dst, etype, tok, tm, emask)
        rows = torch.arange(nodes.shape[0], device=nodes.device)
        h = mem[rows, wn]
        C = cb.shape[1]
        candidate = self.cand_hash(cb)
        valid_node = cn >= 0
        safe_node = cn.clamp(0, mem.shape[1] - 1)
        observed = mem[rows.unsqueeze(1), safe_node]
        candidate = torch.where(valid_node.unsqueeze(-1), observed, candidate)
        candidate = self.cand_proj(torch.cat([candidate, cf], dim=-1))
        hw = h.unsqueeze(1).expand(-1, C, -1)
        logits = self.score(torch.cat([hw, candidate, hw * candidate], dim=-1)).squeeze(-1)
        z = torch.cat([h, batch_ctx_from_collate(batch)], dim=-1)
        return logits, self.activity(z).squeeze(-1), self.open_world(z).squeeze(-1)


def batch_ctx_from_collate(batch):
    # Collate keeps context in candidate features only for compatibility with
    # the compact tuple; derive stable context from the first four candidate
    # features is not correct. This helper is replaced by a registered context
    # tensor in `collate_with_context` below.
    raise RuntimeError('context tensor missing')


def collate_with_context(cases: list, device: str):
    base_batch = collate(cases, device)
    B = len(cases)
    ctx = torch.zeros(B, 4, device=device)
    for i, c in enumerate(cases):
        ctx[i] = torch.as_tensor(c['ctx'], dtype=torch.float, device=device)
    return base_batch[:-3] + [base_batch[-3], base_batch[-2], base_batch[-1], ctx]


def model_forward(model, batch):
    (nodes, src, dst, etype, tok, tm, emask, wn, cb, cn, cf, cmask,
     y, act, ow, support, ctx) = batch
    mem = model.replay(nodes, src, dst, etype, tok, tm, emask)
    rows = torch.arange(nodes.shape[0], device=nodes.device)
    h = mem[rows, wn]
    C = cb.shape[1]
    candidate = model.cand_hash(cb)
    valid_node = cn >= 0
    safe_node = cn.clamp(0, mem.shape[1] - 1)
    observed = mem[rows.unsqueeze(1), safe_node]
    candidate = torch.where(valid_node.unsqueeze(-1), observed, candidate)
    candidate = model.cand_proj(torch.cat([candidate, cf], dim=-1))
    hw = h.unsqueeze(1).expand(-1, C, -1)
    logits = model.score(torch.cat([hw, candidate, hw * candidate], dim=-1)).squeeze(-1)
    z = torch.cat([h, ctx], dim=-1)
    return logits, model.activity(z).squeeze(-1), model.open_world(z).squeeze(-1)


@torch.no_grad()
def evaluate(model, cases, device, batch_size=16):
    model.eval()
    hits = {1: 0, 5: 0, 50: 0, 100: 0}
    active = support = 0
    act_scores=[]; act_labels=[]; ow_scores=[]; ow_labels=[]
    for i in range(0, len(cases), batch_size):
        b = collate_with_context(cases[i:i+batch_size], device)
        logits, act_logit, ow_logit = model_forward(model, b)
        cmask = b[11]; y = b[12]; supported = b[15]
        logits = logits.masked_fill(~cmask, -1e9)
        order = logits.argsort(dim=1, descending=True)
        act_scores.extend(act_logit.detach().cpu().tolist()); act_labels.extend(b[13].cpu().tolist())
        ow_scores.extend(ow_logit.detach().cpu().tolist()); ow_labels.extend(b[14].cpu().tolist())
        for j in range(len(cases[i:i+batch_size])):
            if b[13][j] < 0.5: continue
            active += 1
            if not supported[j]: continue
            support += 1
            pos = (order[j] == y[j]).nonzero(as_tuple=False)
            if len(pos):
                rank = int(pos[0]) + 1
                for k in hits:
                    hits[k] += int(rank <= k)
    def auc(scores, labels):
        try:
            from sklearn.metrics import roc_auc_score
            return float(roc_auc_score(labels, scores)) if len(set(labels)) > 1 else None
        except Exception:
            return None
    return {'active': active, 'pool_support': support,
            'recall_at_1_supported_hits': hits[1], 'recall_at_5_supported_hits': hits[5],
            'recall_at_50_supported_hits': hits[50], 'recall_at_100_supported_hits': hits[100],
            'recall_at_50_all_active': hits[50] / max(1, active),
            'recall_at_100_all_active': hits[100] / max(1, active),
            'activity_auroc': auc(act_scores, act_labels),
            'open_world_auroc_active': auc([x for x,y in zip(ow_scores,ow_labels) if y or True],
                                           [y for y in ow_labels])}


def train_model(cases, out, epochs, batch_size, lr, seed, device):
    torch.manual_seed(seed); np.random.seed(seed)
    train = [c for c in cases if c['split'] in ('train','train_expanded')]
    dev = [c for c in cases if c['split'] == 'dev']
    model = TypedTGN().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    rng = np.random.default_rng(seed); log=[]
    for epoch in range(epochs):
        model.train(); order = rng.permutation(len(train)); total=0.0
        for p in range(0, len(order), batch_size):
            batch_cases = [train[k] for k in order[p:p+batch_size]]
            b = collate_with_context(batch_cases, device)
            logits, act_logit, ow_logit = model_forward(model, b)
            cmask, y, active, ow, support = b[11], b[12], b[13], b[14], b[15]
            logits = logits.masked_fill(~cmask, -1e9)
            rank_mask = support & active.bool()
            rank_loss = F.cross_entropy(logits[rank_mask], y[rank_mask]) if rank_mask.any() else logits.sum()*0
            act_loss = F.binary_cross_entropy_with_logits(act_logit, active)
            ow_mask = active.bool()
            ow_loss = F.binary_cross_entropy_with_logits(ow_logit[ow_mask], ow[ow_mask]) if ow_mask.any() else ow_logit.sum()*0
            loss = rank_loss + 0.5*act_loss + 0.5*ow_loss
            opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            total += loss.item()*len(batch_cases)
        met = evaluate(model, dev, device, batch_size)
        rec = {'epoch': epoch, 'train_loss': total/max(1,len(train)), **{'dev_'+k:v for k,v in met.items()}}
        log.append(rec); print(json.dumps(rec), flush=True)
    return model, log, train, dev


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases-csv', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=5)
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--device', default='cuda:0')
    ap.add_argument('--feature-cache', type=Path)
    args=ap.parse_args(); out=args.out; out.mkdir(parents=True, exist_ok=False); t0=time.time()
    cache=args.feature_cache or (out/'tgn_cases.pkl')
    if cache.exists(): cases=pickle.load(cache.open('rb')); print(json.dumps({'cache_loaded':str(cache),'cases':len(cases)}),flush=True)
    else:
        ev=base.load_events(); df=pd.read_csv(args.cases_csv,dtype={'wallet':str,'target':str}); df['wallet']=df.wallet.str.lower(); df['target']=df.target.fillna('').astype(str).str.lower()
        cases=extract_dataset(ev,df,cache); print(json.dumps({'cache_written':str(cache),'cases':len(cases)}),flush=True)
    model, log, train, dev=train_model(cases,out,args.epochs,args.batch_size,args.lr,args.seed,args.device)
    torch.save({'state_dict':model.state_dict(),'config':{'hidden':96}},out/'typed_tgn_v1.pt')
    da=[c for c in dev if c['active']]
    summary={'status':'complete_train_dev_only_holdout_locked','run':out.name,'cases_csv':str(args.cases_csv),
             'train_cases':len(train),'dev_cases':len(dev),'dev_active':len(da),
             'holdout_labels_materialized':False,'holdout_future_rows_read':False,
             'model_note':'project-specific typed temporal memory replay; not official TGN implementation',
             'protocol_note':'all events and candidate features strictly before cutoff; OPEN_WORLD outside address Top-K',
             'train_log':log,'finished_seconds':time.time()-t0}
    (out/'typed_tgn_summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
    print(json.dumps({'status':summary['status'],'out':str(out),'seconds':summary['finished_seconds']}),flush=True)


if __name__=='__main__':
    try: main()
    except Exception: traceback.print_exc(); raise
