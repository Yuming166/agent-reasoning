"""Rerun only the three corrected GraphMixer seeds at the frozen budget."""
from pathlib import Path
import argparse, json, pickle, time
import torch
from train_certificate_v2 import prepare, train_one, dump


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--device',default='cuda:3');a=ap.parse_args()
    root=Path(a.run);start=time.time()
    # The existing workers have already loaded their inputs and do not use GM again.
    while not ((root/'graphmixer_correction.json').exists() and (root/'worker1_complete.json').exists()):
        time.sleep(5)
    correction=json.loads((root/'graphmixer_correction.json').read_text())
    assert correction['normalization_changed_keys']==['gm']
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=True
    cases=[]
    for p in sorted((root/'shards').glob('*.pkl')):
        with p.open('rb') as f:cases.extend(pickle.load(f))
    stats=json.loads((root/'normalization.json').read_text());cases=prepare(cases,stats)
    for seed in range(3):train_one(cases,stats,'graphmixer',seed,a.device,root)
    correction['status']='repaired_and_three_seeds_retrained'
    correction['retraining_seconds_including_wait']=time.time()-start
    dump(root/'graphmixer_correction.json',correction)
    dump(root/'graphmixer_retraining_complete.json',dict(status='complete',seeds=[0,1,2],epochs=6,optimizer_updates_per_run=408))


if __name__=='__main__':main()
