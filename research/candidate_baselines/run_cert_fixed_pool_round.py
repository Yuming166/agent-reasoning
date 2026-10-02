#!/usr/bin/env python3
"""Fixed-pool certificate round for the Typed Temporal Motif Retriever.

Completes the interrupted 2026-09-30 round:
  1. schema/as-of audit (2022-03..2022-07 partitions only; August never opened)
  2. frozen per-case candidate pools = intersection of the three existing as-of
     pools (motif / graphmixer / typed_tgn); no target injection
  3. event-level temporal motif certificates + chain-specific features
  4. independent certificate validation
  5. matched-budget ranker variants x 3 seeds with negative controls
  6. paired case-level bootstrap vs the direct+global reference
  7. controlled evidence-sensitivity probe (remove certificate events, rescore)

Dev-only evaluation.  The frozen August holdout is untouched.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pickle, sys, time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as Fn

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motif_certificate_fixed_pool as cfp  # noqa: E402

ROOT = cfp.ROOT
DG_IDX = cfp.OLD_BASE_IDX                      # 14 direct+global columns of X_old
N_DG = len(DG_IDX)
N_CERT = len(cfp.CERT_FEATS)
CTX_DIM = 6
SEEDS = (0, 1, 2)
KS = (1, 5, 50, 100)


# ---------------------------------------------------------------- models
class MLPScorer(nn.Module):
    """Plain candidate-feature scorer with the shared aux heads."""
    def __init__(self, in_dim: int, hidden: int = 64):
        super().__init__()
        self.cand = nn.Sequential(nn.Linear(in_dim, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.activity = nn.Sequential(nn.Linear(CTX_DIM, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.open_world = nn.Sequential(nn.Linear(CTX_DIM, hidden), nn.GELU(), nn.Linear(hidden, 1))

    def forward(self, x, ctx):
        return (self.cand(x).squeeze(-1), None,
                self.activity(ctx).squeeze(-1), self.open_world(ctx).squeeze(-1))


class ResidualGateScorer(nn.Module):
    """direct+global base score plus a bounded, evidence-gated certificate residual.

    s = base(x_dg) + tanh(g(ctx, cert_evidence)) * cert_mlp(x_cert) * cert_valid_any
    The residual is exactly zero for candidates without a valid certificate.
    """
    def __init__(self, hidden: int = 64):
        super().__init__()
        self.base = nn.Sequential(nn.Linear(N_DG, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.certm = nn.Sequential(nn.Linear(N_CERT, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.gate = nn.Sequential(nn.Linear(CTX_DIM + 4, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.activity = nn.Sequential(nn.Linear(CTX_DIM, hidden), nn.GELU(), nn.Linear(hidden, 1))
        self.open_world = nn.Sequential(nn.Linear(CTX_DIM, hidden), nn.GELU(), nn.Linear(hidden, 1))

    def forward(self, x, ctx):
        x_dg, x_cert = x[:, :, :N_DG], x[:, :, N_DG:]
        evid = torch.stack([x_cert[:, :, 0], x_cert[:, :, 1], x_cert[:, :, 5], x_cert[:, :, 8]], dim=-1)
        gin = torch.cat([ctx.unsqueeze(1).expand(-1, x.shape[1], -1), evid], dim=-1)
        bounded = torch.tanh(self.gate(gin))
        valid = x_cert[:, :, 0:1]
        resid = bounded * self.certm(x_cert) * valid
        logits = self.base(x_dg).squeeze(-1) + resid.squeeze(-1)
        return logits, resid.squeeze(-1), self.activity(ctx).squeeze(-1), self.open_world(ctx).squeeze(-1)


VARIANTS = {
    'dg':            {'kind': 'mlp', 'feats': 'dg'},          # reference: direct+global (old cols)
    'cert':          {'kind': 'mlp', 'feats': 'cert'},        # real certificates only
    'dg_cert':       {'kind': 'mlp', 'feats': 'dg+cert'},     # concatenation
    'residual':      {'kind': 'residual', 'feats': 'dg+cert'},
    'dg_cert_perm':  {'kind': 'mlp', 'feats': 'dg+cert_perm'},# negative control
}


# ---------------------------------------------------------------- data prep
def case_matrix(case: dict, feats: str, seed: int) -> np.ndarray:
    x_dg = case['X_old'][:, DG_IDX]
    x_cert = case['X_cert']
    if feats == 'dg':
        return x_dg
    if feats == 'cert':
        return x_cert
    if feats == 'dg+cert':
        return np.concatenate([x_dg, x_cert], axis=1)
    if feats == 'dg+cert_perm':
        # Negative control: certificate features permuted across candidates within
        # the case.  Same dimensionality, marginal distribution, and budget; the
        # candidate-level semantics are destroyed.
        rng = np.random.default_rng(int(hashlib.sha1(f"{case['case_id']}|{seed}".encode()).hexdigest()[:8], 16))
        perm = rng.permutation(x_cert.shape[0])
        return np.concatenate([x_dg, x_cert[perm]], axis=1)
    raise ValueError(feats)


def collate(cases: List[dict], feats: str, seed: int, device: str):
    mats = [case_matrix(c, feats, seed) for c in cases]
    n_max = max(m.shape[0] for m in mats)
    d = mats[0].shape[1]
    x = torch.zeros(len(cases), n_max, d, device=device)
    mask = torch.zeros(len(cases), n_max, dtype=torch.bool, device=device)
    for i, m in enumerate(mats):
        x[i, :m.shape[0]] = torch.from_numpy(np.nan_to_num(m, nan=0.0, posinf=0.0, neginf=0.0)).to(device)
        mask[i, :m.shape[0]] = True
    ctx = torch.from_numpy(np.stack([np.nan_to_num(c['ctx'], nan=0.0) for c in cases])).to(device)
    y = torch.tensor([max(0, c['y_idx']) for c in cases], dtype=torch.long, device=device)
    active = torch.tensor([c['active'] for c in cases], dtype=torch.float32, device=device)
    ow = torch.tensor([1.0 if c.get('visibility') == 'open_world' else 0.0 for c in cases],
                      dtype=torch.float32, device=device)
    support = torch.tensor([c['y_idx'] >= 0 for c in cases], dtype=torch.bool, device=device)
    return x, mask, ctx, y, active, ow, support


# ---------------------------------------------------------------- metrics
def auc(scores, labels):
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(labels, scores)) if len(set(labels)) > 1 else None
    except Exception:
        return None


@torch.no_grad()
def evaluate(model, cases: List[dict], feats: str, seed: int, device: str, batch_size: int = 16,
             collect_pred: bool = False):
    model.eval()
    hits = {k: 0 for k in KS}
    hits_vis = defaultdict(lambda: {k: 0 for k in KS})
    active_vis = Counter()
    support_vis = Counter()
    rr5, mrr, rr5_vis, mrr_vis = 0.0, 0.0, defaultdict(float), defaultdict(float)
    active = support = 0
    act_s, act_y, ow_s, ow_y = [], [], [], []
    preds = []
    for start in range(0, len(cases), batch_size):
        chunk = cases[start:start + batch_size]
        x, mask, ctx, y, act, ow, sup = collate(chunk, feats, seed, device)
        logits, _, act_logit, ow_logit = model(x, ctx)
        logits = logits.masked_fill(~mask, -1e9)
        order = logits.argsort(dim=1, descending=True)
        act_s.extend(act_logit.cpu().tolist()); act_y.extend(act.cpu().tolist())
        for j, c in enumerate(chunk):
            if c['active']:
                ow_s.append(float(ow_logit[j].item())); ow_y.append(float(ow[j].item()))
            if collect_pred and c['split'] == 'dev':
                top = order[j, :100].cpu().tolist()
                preds.append({'case_id': c['case_id'], 'wallet': c['wallet'], 'cutoff': c['cutoff'],
                              'target': c['target'], 'visibility': c.get('visibility', ''),
                              'top_candidates': [c['pool'][k] for k in top]})
            if not c['active']:
                continue
            active += 1
            vis = c.get('visibility', '') or 'unknown'
            active_vis[vis] += 1
            if c['y_idx'] < 0:
                continue
            support += 1
            support_vis[vis] += 1
            pos = (order[j] == c['y_idx']).nonzero(as_tuple=False)
            if not len(pos):
                continue
            rank = int(pos[0].item()) + 1
            mrr += 1.0 / rank
            mrr_vis[vis] += 1.0 / rank
            if rank <= 5:
                rr5 += 1.0 / rank
                rr5_vis[vis] += 1.0 / rank
            for k in KS:
                if rank <= k:
                    hits[k] += 1
                    hits_vis[vis][k] += 1
    out = {
        'active': active, 'pool_support': support,
        'pool_support_rate': support / max(1, active),
        **{f'recall_at_{k}': hits[k] / max(1, active) for k in KS},
        **{f'recall_at_{k}_supported': hits[k] / max(1, support) for k in KS},
        **{f'hits_at_{k}': hits[k] for k in KS},
        'mrr': mrr / max(1, support), 'mrr_at_5': rr5 / max(1, support),
        'activity_auroc': auc(act_s, act_y),
        'open_world_auroc_active': auc(ow_s, ow_y),
        'by_visibility': {v: {'active': active_vis[v], 'support': support_vis[v],
                              **{f'recall_at_{k}': hits_vis[v][k] / max(1, active_vis[v]) for k in KS},
                              'mrr_at_5': rr5_vis[v] / max(1, support_vis[v])}
                          for v in sorted(active_vis)},
    }
    if collect_pred:
        out['_preds'] = preds
    return out


def train_variant(cases: List[dict], spec: dict, *, epochs: int, batch_size: int,
                  lr: float, seed: int, device: str):
    torch.manual_seed(seed); np.random.seed(seed)
    rng = np.random.default_rng(seed)
    train = [c for c in cases if c['split'] in ('train', 'train_expanded')]
    dev = [c for c in cases if c['split'] == 'dev']
    if spec['kind'] == 'mlp':
        in_dim = {'dg': N_DG, 'cert': N_CERT, 'dg+cert': N_DG + N_CERT,
                  'dg+cert_perm': N_DG + N_CERT}[spec['feats']]
        model = MLPScorer(in_dim).to(device)
    else:
        model = ResidualGateScorer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    history = []
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(train))
        tot = seen = 0
        for pos in range(0, len(order), batch_size):
            chunk = [train[k] for k in order[pos:pos + batch_size]]
            x, mask, ctx, y, active, ow, sup = collate(chunk, spec['feats'], seed, device)
            logits, _, act_logit, ow_logit = model(x, ctx)
            logits = logits.masked_fill(~mask, -1e9)
            rank_mask = sup & active.bool()
            rank_loss = (Fn.cross_entropy(logits[rank_mask], y[rank_mask])
                         if rank_mask.any() else logits.sum() * 0.0)
            act_loss = Fn.binary_cross_entropy_with_logits(act_logit, active)
            ow_mask = active.bool()
            ow_loss = (Fn.binary_cross_entropy_with_logits(ow_logit[ow_mask], ow[ow_mask])
                       if ow_mask.any() else ow_logit.sum() * 0.0)
            loss = rank_loss + 0.5 * act_loss + 0.5 * ow_loss
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += float(loss.item()) * len(chunk); seen += len(chunk)
        met = evaluate(model, dev, spec['feats'], seed, device, batch_size)
        met = {k: v for k, v in met.items() if k != '_preds'}
        history.append({'epoch': epoch, 'train_loss': tot / max(1, seen),
                        'recall_at_50': met['recall_at_50'], 'mrr_at_5': met['mrr_at_5']})
        print(json.dumps({'variant_train': spec, 'seed': seed, **history[-1]}), flush=True)
    final = evaluate(model, dev, spec['feats'], seed, device, batch_size, collect_pred=True)
    return model, history, final


# ---------------------------------------------------------------- certificate validation
def validate_certificates(out: Path) -> dict:
    path = out / 'event_certificates.jsonl'
    stats = {'total': 0, 'valid': 0, 'by_type': defaultdict(lambda: {'n': 0, 'valid': 0}),
             'violations': Counter()}
    with path.open() as f:
        for line in f:
            c = json.loads(line)
            stats['total'] += 1
            t = c['motif_type']
            stats['by_type'][t]['n'] += 1
            cutoff = pd.Timestamp(c['cutoff'], tz='UTC')
            evs = c['events']
            ok = True
            for e in evs:
                if pd.Timestamp(e['block_timestamp']) >= cutoff:
                    ok = False; stats['violations']['event_after_cutoff'] += 1
            w, cand = c['wallet'], c['candidate']
            def involves(e, a):
                return a in (e['from_address'], e['to_address'])
            if t == 'wallet_to_peer_to_candidate' and len(evs) == 2:
                e1, e2 = evs
                shared = {e1['from_address'], e1['to_address']} & {e2['from_address'], e2['to_address']}
                if not involves(e1, w): ok = False; stats['violations']['path_e1_wallet'] += 1
                if not involves(e2, cand): ok = False; stats['violations']['path_e2_candidate'] += 1
                if not shared: ok = False; stats['violations']['path_no_shared_peer'] += 1
                if pd.Timestamp(e1['block_timestamp']) > pd.Timestamp(e2['block_timestamp']):
                    ok = False; stats['violations']['path_time_order'] += 1
                if e1['transaction_hash'] == e2['transaction_hash']:
                    ok = False; stats['violations']['path_same_tx'] += 1
            elif t == 'shared_token_contract_wedge' and len(evs) == 2:
                e1, e2 = evs
                if not (e1['token_contract_address'] and e1['token_contract_address'] == e2['token_contract_address']):
                    ok = False; stats['violations']['wedge_token_mismatch'] += 1
                if not (involves(e1, w) or involves(e2, w)):
                    ok = False; stats['violations']['wedge_wallet_absent'] += 1
                if not (involves(e1, cand) or involves(e2, cand)):
                    ok = False; stats['violations']['wedge_candidate_absent'] += 1
            elif t == 'repeat_direct_interaction' and len(evs) == 2:
                e1, e2 = evs
                for e in evs:
                    if not (involves(e, w) and involves(e, cand)):
                        ok = False; stats['violations']['repeat_endpoint'] += 1
                if e1['transaction_hash'] == e2['transaction_hash']:
                    ok = False; stats['violations']['repeat_same_tx'] += 1
            else:
                if len(evs) != 2:
                    ok = False; stats['violations']['bad_event_count'] += 1
            stats['valid'] += int(ok)
            stats['by_type'][t]['valid'] += int(ok)
    res = {'total': stats['total'], 'valid': stats['valid'],
           'valid_rate': stats['valid'] / max(1, stats['total']),
           'by_type': {k: dict(v) for k, v in stats['by_type'].items()},
           'violations': dict(stats['violations'])}
    (out / 'certificate_validation.json').write_text(json.dumps(res, indent=2) + '\n')
    return res


# ---------------------------------------------------------------- sensitivity probe
@torch.no_grad()
def score_case(model, case: dict, feats: str, seed: int, device: str) -> np.ndarray:
    x, mask, ctx, y, act, ow, sup = collate([case], feats, seed, device)
    logits, _, _, _ = model(x, ctx)
    return logits[0].cpu().numpy()


def sensitivity_probe(ev: pd.DataFrame, cases: List[dict], model, seed: int,
                      device: str, out: Path, n_cases: int = 6, n_random: int = 5) -> dict:
    certs = defaultdict(list)
    with (out / 'event_certificates.jsonl').open() as f:
        for line in f:
            c = json.loads(line)
            certs[(c['case_id'], c['candidate'])].append(c)
    dev_active = [c for c in cases if c['split'] == 'dev' and c['active'] and c['y_idx'] >= 0]
    rows = []
    rng = np.random.default_rng(123)
    for case in dev_active:
        key = (case['case_id'], case['target'])
        if not certs.get(key):
            continue
        base_scores = score_case(model, case, 'dg+cert', seed, device)
        base_rank = int((base_scores > base_scores[case['y_idx']]).sum()) + 1
        if base_rank > 50:
            continue
        cutoff = pd.Timestamp(case['cutoff'], tz='UTC')
        hist = ev[ev.block_timestamp < cutoff]
        cert_eids = {e['event_id'] for c2 in certs[key] for e in c2['events']}
        w = case['wallet']
        wev = hist[hist.target_address == w]
        cert_rows = wev[wev.event_id.isin(cert_eids)]
        other_rows = wev[~wev.event_id.isin(cert_eids)]
        variants = {'remove_cert_events': hist[~hist.event_id.isin(cert_eids)]}
        for k in range(n_random):
            drop = other_rows.sample(n=min(len(cert_rows), len(other_rows)),
                                     random_state=int(rng.integers(1e9)))
            variants[f'remove_random_{k}'] = hist.drop(drop.index)
        rec = {'case_id': case['case_id'], 'wallet': w, 'cutoff': case['cutoff'],
               'target': case['target'], 'base_rank': base_rank,
               'n_cert_events': len(cert_eids), 'n_cert_rows_removed': len(cert_rows),
               'cert_types': sorted({c2['motif_type'] for c2 in certs[key]})}
        for name, h2 in variants.items():
            wsub = h2[h2.target_address == w]
            peers = set(wsub.loc[wsub.direction.eq('outgoing'), 'counterparty_address'])
            actors = {w} | set(case['pool']) | peers
            amap = cfp.actor_event_maps(h2, actors)
            outgoing_hist = h2[h2.direction.eq('outgoing')]
            gcnt = Counter(outgoing_hist.counterparty_address)
            r30 = outgoing_hist[outgoing_hist.block_timestamp >= cutoff - pd.Timedelta(days=30)]
            r7 = outgoing_hist[outgoing_hist.block_timestamp >= cutoff - pd.Timedelta(days=7)]
            gs = {'gcnt': gcnt, 'rcnt30': Counter(r30.counterparty_address),
                  'rcnt7': Counter(r7.counterparty_address),
                  'hub_degree': Counter({k: int(v) for k, v in outgoing_hist.groupby('counterparty_address')
                                         .target_address.nunique().items()})}
            sink: List[dict] = []
            F2, _ = cfp.compute_case_cert_features(case, h2, amap, gs, sink, Counter(), Counter())
            case2 = dict(case); case2['X_cert'] = F2
            s2 = score_case(model, case2, 'dg+cert', seed, device)
            new_rank = int((s2 > s2[case['y_idx']]).sum()) + 1
            rec[f'rank_{name}'] = new_rank
        rows.append(rec)
        print(json.dumps({'sensitivity_case': rec}), flush=True)
        if len(rows) >= n_cases:
            break
    (out / 'sensitivity_probe.json').write_text(json.dumps(rows, indent=2) + '\n')
    return {'cases': len(rows), 'rows': rows}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=6)
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--device', default='cuda:0')
    ap.add_argument('--smoke', type=int, default=0, help='limit cases per cutoff for smoke test')
    ap.add_argument('--skip-extract', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    stage = lambda **kw: print(json.dumps({'stage': kw}), flush=True)

    audit = cfp.schema_audit(args.out)
    stage(schema='done', partitions=len(audit['partitions']))

    ev_cache = args.out / 'events_cache.pkl'
    if ev_cache.exists():
        with ev_cache.open('rb') as f:
            ev = pickle.load(f)
    else:
        ev = cfp.load_events()
        with ev_cache.open('wb') as f:
            pickle.dump(ev, f, protocol=4)
    stage(events=len(ev))

    if (args.out / 'fixed_dataset_base.pkl').exists():
        with (args.out / 'fixed_dataset_base.pkl').open('rb') as f:
            fixed = pickle.load(f)
    else:
        fixed = cfp.build_fixed_dataset(args.out)
    if args.smoke:
        by_cut = defaultdict(list)
        for c in fixed:
            by_cut[c['cutoff']].append(c)
        fixed = [c for cut in sorted(by_cut) for c in by_cut[cut][:args.smoke]]
        stage(smoke_cases=len(fixed))
    stage(fixed_cases=len(fixed))

    if args.skip_extract and (args.out / 'cert_features_by_case.pkl').exists():
        with (args.out / 'cert_features_by_case.pkl').open('rb') as f:
            enriched = pickle.load(f)
    else:
        enriched = cfp.extract_cert_features(ev, fixed, args.out)
    stage(cert_features='done', cases=len(enriched))

    cert_val = validate_certificates(args.out) if (args.out / 'event_certificates.jsonl').exists() else None
    stage(certificate_validation=cert_val)

    # old proxy motif columns vs real certificate features (dev divergence)
    dev = [c for c in enriched if c['split'] == 'dev']
    proxy_cols = cfp.OLD_MOTIF_IDX
    cors = {}
    for j, name in enumerate(cfp.CERT_FEATS):
        v = np.concatenate([c['X_cert'][:, j] for c in dev])
        for pi in proxy_cols:
            u = np.concatenate([c['X_old'][:, pi] for c in dev])
            if u.std() > 1e-9 and v.std() > 1e-9:
                cors.setdefault(name, {})[cfp.OLD_FEATS[pi]] = float(np.corrcoef(u, v)[0, 1])
    div = {k: max(np.abs(list(v.values()))) for k, v in cors.items() if v}
    (args.out / 'proxy_vs_certificate_divergence.json').write_text(json.dumps(cors, indent=2) + '\n')
    stage(max_abs_corr_per_cert_feat=div)

    all_results: Dict[str, dict] = {}
    pred_frames = []
    for name, spec in VARIANTS.items():
        for seed in SEEDS:
            stage(variant=name, seed=seed, status='start')
            model, history, final = train_variant(enriched, spec, epochs=args.epochs,
                                                  batch_size=args.batch_size, lr=args.lr,
                                                  seed=seed, device=args.device)
            preds = final.pop('_preds', [])
            for p in preds:
                p.update({'variant': name, 'seed': seed})
                pred_frames.append(p)
            all_results[f'{name}#s{seed}'] = {'spec': spec, 'seed': seed,
                                              'history': history, 'final': final}
            if name == 'dg_cert' and seed == SEEDS[0]:
                torch.save({'state_dict': model.state_dict()},
                           args.out / 'dg_cert_seed0_for_probe.pt')
                probe_model = model
    pred_rows = []
    for p in pred_frames:
        for rank, cand in enumerate(p['top_candidates'], 1):
            pred_rows.append({'variant': p['variant'], 'seed': p['seed'], 'case_id': p['case_id'],
                              'wallet': p['wallet'], 'cutoff': p['cutoff'], 'target': p['target'],
                              'visibility': p['visibility'], 'rank': rank, 'candidate': cand})
    pd.DataFrame(pred_rows).to_csv(args.out / 'dev_case_predictions.csv', index=False)
    stage(predictions=len(pred_rows))

    # paired case-level bootstrap: dg_cert vs dg, hit@50 and MRR@5, pooled seeds;
    # per-case hit/mrr reconstructed from the saved predictions
    per = defaultdict(dict)
    for name in ('dg', 'dg_cert'):
        for seed in SEEDS:
            key = (name, seed)
            sub = [p for p in pred_frames if p['variant'] == name and p['seed'] == seed]
            for p in sub:
                if not p['target']:
                    continue
                hit50 = int(p['target'] in p['top_candidates'][:50])
                try:
                    rank = p['top_candidates'].index(p['target']) + 1
                except ValueError:
                    rank = 10 ** 9
                rr5 = 1.0 / rank if rank <= 5 else 0.0
                per[p['case_id']][key] = (hit50, rr5)
    rng = np.random.default_rng(7)
    case_ids = sorted(per)
    diffs_hit, diffs_rr = [], []
    B = 2000
    for _ in range(B):
        samp = rng.choice(case_ids, size=len(case_ids), replace=True)
        dh, dr = [], []
        for cid in samp:
            for seed in SEEDS:
                a = per[cid].get(('dg_cert', seed)); b = per[cid].get(('dg', seed))
                if a is None or b is None:
                    continue
                dh.append(a[0] - b[0]); dr.append(a[1] - b[1])
        diffs_hit.append(np.mean(dh)); diffs_rr.append(np.mean(dr))
    boot = {'dg_cert_minus_dg': {
        'hit_at_50_mean_diff': float(np.mean(diffs_hit)),
        'hit_at_50_ci95': [float(np.percentile(diffs_hit, 2.5)), float(np.percentile(diffs_hit, 97.5))],
        'mrr_at_5_mean_diff': float(np.mean(diffs_rr)),
        'mrr_at_5_ci95': [float(np.percentile(diffs_rr, 2.5)), float(np.percentile(diffs_rr, 97.5))],
        'note': 'case-level paired bootstrap pooled over seeds; hit@50 restricted to top-100 prediction dump'}}
    (args.out / 'paired_bootstrap.json').write_text(json.dumps(boot, indent=2) + '\n')
    stage(bootstrap=boot)

    sens = sensitivity_probe(ev, enriched, probe_model, SEEDS[0], args.device, args.out)
    stage(sensitivity={'cases': sens['cases']})

    summary = {
        'status': 'complete_train_dev_certificate_fixed_pool_round',
        'holdout_labels_materialized': False,
        'protocol': {
            'fixed_pool': 'per-case intersection of motif/graphmixer/typed_tgn as-of pools',
            'checkpoint_rule': 'final epoch, predeclared; no dev-based epoch selection',
            'seeds': list(SEEDS), 'epochs': args.epochs, 'batch_size': args.batch_size,
            'lr': args.lr, 'optimizer': 'AdamW', 'weight_decay': 1e-4,
            'negative_control': 'dg_cert_perm permutes certificate features across candidates within case',
        },
        'certificate_validation': cert_val,
        'results': {k: {'final': {m: v for m, v in r['final'].items()}} for k, r in all_results.items()},
        'paired_bootstrap': boot,
        'sensitivity_cases': sens['cases'],
        'elapsed_seconds': time.time() - t0,
        'args': vars(args) | {'out': str(args.out)},
    }
    (args.out / 'round_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'status': summary['status'], 'seconds': summary['elapsed_seconds'],
                      'out': str(args.out)}), flush=True)


if __name__ == '__main__':
    main()
