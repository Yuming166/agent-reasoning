"""Plan B orchestrator: runs steps 2-6 in order, stops on first failure,
writes a final summary. Step 1 (selection) must already be complete.
"""
from pathlib import Path
import json, subprocess, sys, time

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
STEPS = [
    ('step2_cases', ['.tmp/planB_step2_cases.py'], ['parts/build_audit.json']),
    ('step3_features', ['.tmp/planB_step3_features.py'], ['features_audit.json']),
    ('step4_score', ['.tmp/planB_step4_score.py'], ['metrics/scoring_complete.json']),
    ('step5_selector', ['.tmp/planB_step5_selector_v2.py'], ['selector_v2/complete.json']),
    ('step6_retrain_gate', ['.tmp/planB_step6_retrain_gate.py'], ['retrain_gate/gate.json']),
]
env_extra = {'PYTHONPATH': 'research/candidate_baselines',
             'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'PYTHONUNBUFFERED': '1'}
log = (ROOT / '.tmp/planB_pipeline.log').open('a')

def run(name, script, expect):
    t = time.time()
    print(json.dumps({'step': name, 'start': True}), flush=True)
    log.write(json.dumps({'step': name, 'start': True}) + '\n'); log.flush()
    r = subprocess.run([str(ROOT / '.venv-cuda/bin/python'), '-u'] + script,
                       cwd=ROOT, env={**__import__('os').environ, **env_extra},
                       stdout=log, stderr=subprocess.STDOUT)
    ok = r.returncode == 0 and all((OUT / e).exists() for e in expect)
    print(json.dumps({'step': name, 'rc': r.returncode, 'ok': ok,
                      'secs': round(time.time() - t, 1)}), flush=True)
    log.write(json.dumps({'step': name, 'rc': r.returncode, 'ok': ok}) + '\n'); log.flush()
    return ok

for name, script, expect in STEPS:
    if not run(name, script, expect):
        log.write(json.dumps({'pipeline': 'failed', 'step': name}) + '\n'); log.flush()
        sys.exit(1)
log.write(json.dumps({'pipeline': 'complete'}) + '\n')
log.close()
print(json.dumps({'pipeline': 'complete'}), flush=True)
