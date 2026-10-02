import json
import os
import pathlib
import subprocess

root = pathlib.Path("artifacts/cert_v2_timefix_20261001T200517Z")
assert json.loads((root / "extraction_complete.json").read_text())["invalid"] == 0
assert len(list((root / "shards").glob("*.pkl"))) == 7

gpu_text = subprocess.check_output(
    ["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
    text=True,
)
used = {int(a.strip()): int(b.strip()) for a, b in (line.split(",") for line in gpu_text.splitlines())}
assert used[1] < 500 and used[3] < 500, used

env = dict(os.environ, OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", PYTHONUNBUFFERED="1")
jobs = []
for worker, device in [(0, "cuda:1"), (1, "cuda:3")]:
    logfile = pathlib.Path(".tmp") / f"cert_v2_timefix_train_worker{worker}.log"
    log = logfile.open("w")
    args = [
        ".venv-cuda/bin/python",
        "-u",
        "research/candidate_baselines/train_certificate_v2.py",
        "--run",
        str(root),
        "--worker",
        str(worker),
        "--workers",
        "2",
        "--device",
        device,
    ]
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env)
    jobs.append((worker, proc, log))
    print(json.dumps({"worker": worker, "pid": proc.pid, "device": device, "log": str(logfile)}), flush=True)

(root / "training_processes.json").write_text(
    json.dumps([{"worker": worker, "pid": proc.pid} for worker, proc, _ in jobs], indent=2) + "\n"
)
codes = []
for worker, proc, log in jobs:
    code = proc.wait()
    log.close()
    codes.append(code)
    print(json.dumps({"worker": worker, "exit_code": code}), flush=True)
raise SystemExit(int(any(codes)))
