"""Wait for the existing extraction; launch only two explicitly selected GPUs."""
import json, os, pathlib, subprocess, time

root = pathlib.Path('artifacts/cert_v2_full_20260930T182723Z')
extract_pid = 4067242
while not (root / 'extraction_complete.json').exists():
    try:
        os.kill(extract_pid, 0)
    except ProcessLookupError:
        raise SystemExit('Extraction stopped without completion; preserving partial artifacts.')
    time.sleep(10)
assert json.loads((root / 'extraction_complete.json').read_text())['invalid'] == 0
gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'], text=True)
used = {int(a): int(b) for a, b in (line.split(',') for line in gpu.splitlines())}
assert all(used[i] < 500 for i in [1, 3]), ('Selected GPU is busy', used)
env = dict(os.environ, OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', PYTHONUNBUFFERED='1')
jobs = []
for worker, device in [(0, 'cuda:1'), (1, 'cuda:3')]:
    logfile = pathlib.Path('.tmp') / ('cert_v2_train_worker%d.log' % worker)
    log = logfile.open('w')
    args = ['.venv-cuda/bin/python', '-u', 'research/candidate_baselines/train_certificate_v2.py',
            '--run', str(root), '--worker', str(worker), '--workers', '2', '--device', device]
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env)
    jobs.append((worker, proc, log))
    print(json.dumps(dict(worker=worker, pid=proc.pid, device=device, logfile=str(logfile))), flush=True)
(root / 'training_processes.json').write_text(json.dumps([dict(worker=w, pid=p.pid) for w,p,l in jobs], indent=2))
codes = []
for worker, proc, log in jobs:
    code = proc.wait(); log.close(); codes.append(code)
    print(json.dumps(dict(worker=worker, exit_code=code)), flush=True)
raise SystemExit(int(any(codes)))
