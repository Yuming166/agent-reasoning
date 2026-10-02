"""Plan B retrain gate (protocol section 1): retrain chain_all seed0 on the
SAME 2150 train cases from the frozen run, byte-identical loss/schedule
(F.cross_entropy over masked logits + .2 BCE activity + .2 BCE open-world,
AdamW lr 1e-3 wd 1e-4, batch 32, 6 epochs, grad-clip 5), then verify ranks on
the old 52 active dev cases match the frozen run exactly (max_rank_diff == 0).

This is a drift gate, not a training need: the training set is unchanged, so
the frozen model is the legitimate post-retrain model.
"""
from pathlib import Path
import json, pickle, sys, time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
sys.path.insert(0, str(ROOT / 'research/candidate_baselines'))
from certificate_models_v2 import Scorer
from train_certificate_v2 import prepare, collate

def dump(p, obj):
    tmp = Path(str(p) + '.tmp.' + str(__import__('os').getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    tmp.rename(p)

t0 = time.time()
device = torch.device('cuda:3')
stats = json.loads((RUN / 'normalization.json').read_text())

rows = []
for p in sorted((RUN / 'shards').glob('*.pkl')):
    with p.open('rb') as f:
        rows += pickle.load(f)
def deep_case(r):
    r = dict(r)
    for k in ['B', 'C', 'E', 'X', 'gm', 'ctx', 'seq']:
        r[k] = r[k].copy()
    return r

train = [deep_case(r) for r in rows if r['split'] != 'dev']
dev_all = [deep_case(r) for r in rows if r['split'] == 'dev']
dev_act = [r for r in dev_all if r['active']]
assert len(train) == 2150 and len(dev_act) == 52, (len(train), len(dev_act))
train = prepare(train, stats)  # same pre-normalization as the original training loop
print(json.dumps({'train': len(train), 'dev_active': len(dev_act)}), flush=True)

torch.manual_seed(0); np.random.seed(0)  # before Scorer(): init consumes torch RNG (as train_one)
model = Scorer('chain_all').to(device)
opt = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.0001)
rng = np.random.default_rng(0)
logs = []
for epoch in range(6):
    model.train(); order = rng.permutation(len(train)); losses = []; updates = 0
    for j in range(0, len(order), 32):
        sub = [train[k] for k in order[j:j + 32]]
        batch = collate(sub, device, 'chain_all', 0)
        opt.zero_grad(set_to_none=True)
        s, _, _, _, act, ow = model(batch)
        sup = batch['support']
        rankloss = (F.cross_entropy(s.masked_fill(~batch['mask'], -1e9)[sup],
                                    batch['target'][sup])
                    if sup.any() else s.sum() * 0)
        loss = (rankloss + .2 * F.binary_cross_entropy_with_logits(act, batch['active'])
                + .2 * F.binary_cross_entropy_with_logits(ow, batch['ow']))
        assert torch.isfinite(loss)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
        opt.step(); updates += 1; losses.append(float(loss.detach()))
    logs.append(dict(epoch=epoch + 1, loss=float(np.mean(losses)), updates=updates))
    print(json.dumps(logs[-1]), flush=True)

model.eval()
prep = prepare([deep_case(r) for r in dev_act], stats)
rec = pd.read_csv(RUN / 'models' / 'chain_all' / 'seed0' / 'case_predictions.csv')
old_rank = rec.set_index('case_id')['rank']
maxd = 0
with torch.no_grad():
    for start in range(0, len(prep), 8):
        sub = prep[start:start + 8]
        batch = collate(sub, device, 'chain_all', 0)
        s = model(batch)[0].cpu().numpy()
        for i, r in enumerate(sub):
            sc = s[i, :len(r['pool'])]
            order = np.argsort(-sc, kind='stable')
            rank = np.empty(len(sc), np.int32); rank[order] = np.arange(1, len(sc) + 1)
            new_rank = int(rank[r['y_idx']]) if r['y_idx'] >= 0 else -1
            maxd = max(maxd, abs(new_rank - int(old_rank.loc[r['case_id']])))
ok = maxd == 0
dump(OUT / 'retrain_gate' / 'gate.json',
     {'max_rank_diff': int(maxd), 'pass': bool(ok), 'train_log': logs,
      'secs': round(time.time() - t0, 1),
      'semantics': 'same 2150 train cases, same seed/lr/schedule/loss as frozen run; '
                   'gate = old-52 ranks byte-identical'})
print(json.dumps({'gate_max_rank_diff': int(maxd), 'pass': bool(ok)}), flush=True)
