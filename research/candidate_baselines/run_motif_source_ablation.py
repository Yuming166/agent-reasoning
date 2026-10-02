#!/usr/bin/env python3
"""Frozen train/dev source ablation for the typed motif retriever.

This is a diagnostic, not a new headline model.  It reuses the existing
pre-cutoff motif feature cache and trains the same source-gated architecture
with controlled source masks.  Every variant uses the same cases, seed,
optimizer, epoch count, and final-checkpoint rule.
"""
from __future__ import annotations
import argparse, json, pickle, time
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

import motif_gated_retriever as m

VARIANTS = {
    "direct_only": ("direct",),
    "direct_diffusion": ("direct", "diffusion"),
    "direct_motif": ("direct", "motif"),
    "direct_global": ("direct", "global"),
    "all_four": ("direct", "diffusion", "motif", "global"),
}
SOURCE_ORDER = ("direct", "diffusion", "motif", "global")


class MaskedMotifGatedScorer(nn.Module):
    """Same scorer as the pilot, with an explicit source availability mask."""
    def __init__(self, enabled: Sequence[str], hidden: int = 64):
        super().__init__()
        self.enabled = tuple(enabled)
        self.direct = m.SourceMLP(len(m.DIRECT), hidden)
        self.diffusion = m.SourceMLP(3, hidden)
        self.motif = m.SourceMLP(3, hidden)
        self.global_prior = m.SourceMLP(len(m.GLOBL), hidden)
        self.gate = nn.Sequential(nn.Linear(len(m.CTX), hidden), nn.GELU(),
                                  nn.Linear(hidden, 4))
        self.activity = nn.Sequential(nn.Linear(len(m.CTX), hidden), nn.GELU(),
                                      nn.Linear(hidden, 1))
        self.open_world = nn.Sequential(nn.Linear(len(m.CTX), hidden), nn.GELU(),
                                        nn.Linear(hidden, 1))
        mask = torch.tensor([s in self.enabled for s in SOURCE_ORDER], dtype=torch.bool)
        self.register_buffer("source_mask", mask)

    def forward(self, x, ctx):
        source = torch.stack([
            self.direct(x[:, :, 0:8]),
            self.diffusion(x[:, :, [9, 10, 11]]),
            self.motif(x[:, :, [8, 12, 13]]),
            self.global_prior(x[:, :, 14:20]),
        ], dim=-1)
        gate_logits = self.gate(ctx).masked_fill(~self.source_mask, -1e9)
        gate = torch.softmax(gate_logits, dim=-1)
        contribution = source * gate.unsqueeze(1) * self.source_mask.to(source.dtype)
        logits = contribution.sum(dim=-1)
        return logits, contribution, gate, self.activity(ctx).squeeze(-1), self.open_world(ctx).squeeze(-1)


def auc(scores, labels):
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(labels, scores)) if len(set(labels)) > 1 else None
    except Exception:
        return None


@torch.no_grad()
def evaluate(model, cases: List[dict], device: str, batch_size: int = 32):
    model.eval()
    ks = [1, 5, 50, 100, 500, 2000]
    hits = {k: 0 for k in ks}
    active = support = 0
    act_scores, act_labels, ow_active = [], [], []
    gate_sum = np.zeros(4, dtype=np.float64)
    n_gate = 0
    for start in range(0, len(cases), batch_size):
        chunk = cases[start:start + batch_size]
        x, mask, ctx, y, act, ow, has = m.collate_retriever(chunk, device)
        logits, _, gate, act_logit, ow_logit = model(x, ctx)
        logits = logits.masked_fill(~mask, -1e9)
        order = logits.argsort(dim=1, descending=True)
        act_scores.extend(act_logit.cpu().tolist())
        act_labels.extend(act.cpu().tolist())
        gate_sum += gate.cpu().numpy().sum(axis=0)
        n_gate += gate.shape[0]
        for j, c in enumerate(chunk):
            if not c['active']:
                continue
            active += 1
            ow_active.append((float(ow_logit[j].item()), float(ow[j].item())))
            if not bool(has[j]):
                continue
            support += 1
            pos = (order[j] == y[j]).nonzero(as_tuple=False)
            if len(pos):
                rank = int(pos[0].item()) + 1
                for k in ks:
                    hits[k] += int(rank <= k)
    return {
        'active': active,
        'pool_support': support,
        'pool_support_rate': support / max(1, active),
        'recall_hits_supported': {str(k): hits[k] for k in ks},
        'recall_at_50_all_active': hits[50] / max(1, active),
        'recall_at_100_all_active': hits[100] / max(1, active),
        'recall_at_50_supported': hits[50] / max(1, support),
        'recall_at_100_supported': hits[100] / max(1, support),
        'activity_auroc': auc(act_scores, act_labels),
        'open_world_auroc_active': auc([s for s, _ in ow_active], [y for _, y in ow_active]),
        'mean_gate': (gate_sum / max(1, n_gate)).tolist(),
        'open_world_active_labels': int(sum(y for _, y in ow_active)),
    }


def train_variant(cases: List[dict], enabled: Sequence[str], *, epochs: int,
                  batch_size: int, lr: float, seed: int, device: str):
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = np.random.default_rng(seed)
    train = [c for c in cases if c['split'] in ('train', 'train_expanded')]
    dev = [c for c in cases if c['split'] == 'dev']
    model = MaskedMotifGatedScorer(enabled).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    history = []
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(train))
        total = 0.0
        n_seen = 0
        for pos in range(0, len(order), batch_size):
            chunk = [train[k] for k in order[pos:pos + batch_size]]
            x, mask, ctx, y, active, ow, support = m.collate_retriever(chunk, device)
            logits, _, _, act_logit, ow_logit = model(x, ctx)
            logits = logits.masked_fill(~mask, -1e9)
            rank_mask = support & active.bool()
            rank_loss = (F.cross_entropy(logits[rank_mask], y[rank_mask])
                         if rank_mask.any() else logits.sum() * 0.0)
            act_loss = F.binary_cross_entropy_with_logits(act_logit, active)
            ow_mask = active.bool()
            ow_loss = (F.binary_cross_entropy_with_logits(ow_logit[ow_mask], ow[ow_mask])
                       if ow_mask.any() else ow_logit.sum() * 0.0)
            loss = rank_loss + 0.5 * act_loss + 0.5 * ow_loss
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += float(loss.item()) * len(chunk)
            n_seen += len(chunk)
        metrics = evaluate(model, dev, device, batch_size)
        rec = {'epoch': epoch, 'train_loss': total / max(1, n_seen), **metrics}
        history.append(rec)
        print(json.dumps(rec), flush=True)
    return model, history, train, dev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feature-cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=6)
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--device', default='cuda:1')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    with args.feature_cache.open('rb') as f:
        cases = pickle.load(f)
    all_results: Dict[str, dict] = {}
    for name, enabled in VARIANTS.items():
        vdir = args.out / name
        vdir.mkdir()
        print(json.dumps({'variant_start': name, 'enabled': enabled}), flush=True)
        model, history, train, dev = train_variant(
            cases, enabled, epochs=args.epochs, batch_size=args.batch_size,
            lr=args.lr, seed=args.seed, device=args.device)
        final = evaluate(model, dev, args.device, args.batch_size)
        torch.save({'state_dict': model.state_dict(),
                    'config': {'enabled_sources': list(enabled), 'features': m.FEATS,
                               'context': m.CTX, 'seed': args.seed,
                               'epochs': args.epochs, 'final_checkpoint': True}},
                   vdir / 'model.pt')
        (vdir / 'history.json').write_text(json.dumps(history, indent=2) + '\n')
        (vdir / 'final_metrics.json').write_text(json.dumps(final, indent=2) + '\n')
        all_results[name] = {'enabled_sources': list(enabled), 'final': final,
                             'history': history}
    manifest = {
        'status': 'complete_train_dev_source_ablation',
        'feature_cache': str(args.feature_cache),
        'cases': len(cases),
        'train_cases': sum(c['split'] in ('train', 'train_expanded') for c in cases),
        'dev_cases': sum(c['split'] == 'dev' for c in cases),
        'dev_active': sum(c['split'] == 'dev' and c['active'] for c in cases),
        'protocol': {
            'same_cases_seed_optimizer_and_final_checkpoint': True,
            'open_world_separate_from_concrete_address_hit': True,
            'all_features_pre_cutoff_from_existing_cache': True,
            'holdout_labels_materialized': False,
        },
        'args': vars(args) | {'feature_cache': str(args.feature_cache), 'out': str(args.out)},
        'variants': all_results,
        'elapsed_seconds': time.time() - t0,
    }
    (args.out / 'ablation_summary.json').write_text(json.dumps(manifest, indent=2) + '\n')
    rows = []
    for name, result in all_results.items():
        row = {'variant': name, 'enabled_sources': '+'.join(result['enabled_sources'])}
        row.update({k: v for k, v in result['final'].items() if not isinstance(v, (dict, list))})
        rows.append(row)
    pd.DataFrame(rows).to_csv(args.out / 'ablation_final_metrics.csv', index=False)
    print(json.dumps({'status': manifest['status'], 'out': str(args.out),
                      'seconds': manifest['elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    main()
