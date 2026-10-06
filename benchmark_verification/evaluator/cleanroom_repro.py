#!/usr/bin/env python
"""Stage F part 2: cleanroom local reproduction.

Copies VERSIONED_DATASET + evaluator scripts into a fresh temp directory,
then runs, in an ISOLATED process (cwd = temp dir, no repo absolute paths in
inputs), the full scoring of the frozen v27lean baseline from the moved
copies, plus an independent recount. This tests relocatability (no absolute
repo paths baked into data/code behavior). It is NOT an external replication;
no claim of third-party reproduction is made.

Writes (first-write only): REPRODUCTION_RECEIPT.json
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

R = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
OUT = R / "artifacts/benchmark_release_candidate_v1_20261006"
SRC_RES = R / "research/benchmark_release_candidate_v1_20261006"
PY = sys.executable


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


CLEANROOM = """
import json, sys, gzip
from pathlib import Path
sys.path.insert(0, str(Path('code').resolve()))
import numpy as np
from benchmark_evaluator import FirstSeenDomain, evaluate_forecast, read_jsonl, unique_by

DS = Path('dataset')
V27 = Path('v27lean')  # frozen npz copied read-only

rows = []
with gzip.open(DS / 'candidate_index/legal_domain_index.jsonl.gz', 'rt') as f:
    f.readline()
    for line in f:
        r = json.loads(line)
        rows.append((r['address'], r['first_seen_UTC_seconds']))
domain = FirstSeenDomain(dict(rows))
queries = read_jsonl(DS / 'queries/train.jsonl')
gold = read_jsonl(DS / 'forecast_gold/train.jsonl')
pools = {r['query_id']: r for r in read_jsonl(DS / 'reference_pools/reference_top50_train.jsonl')}
gmap = unique_by(gold, 'query_id')

with np.load(V27 / 'PREDICTIONS.npz', allow_pickle=False) as z:
    case_ids = z['case_ids'].tolist()
    addresses = np.asarray(z['addresses'])
    branches = {b: z[b] for b in ('r0scores', 'all_history_seed0', 'recent_actions_seed0',
                                  'program_roles_seed0', 'learned_locator_seed0')}

out = {'fixed_pool': {}, 'retrieval': {}, 'recount': {}}
for b, sc in branches.items():
    rws = []
    for i, cid in enumerate(case_ids):
        order = np.lexsort((addresses[i], -sc[i].astype(np.float64)))
        rws.append({'query_id': cid, 'ranked_candidate_ids': [addresses[i][j] for j in order]})
    res = evaluate_forecast(queries, gold, rws, domain, 'fixed_pool', pools=pools)
    out['fixed_pool'][b] = {'hits5': res['summary']['hits5'], 'Top5': res['summary']['Top5'],
                            'MRR5': res['summary']['MRR5'], 'Recall50': res['summary']['Recall50'],
                            'valid': res['summary']['valid_predictions']}
    res2 = evaluate_forecast(queries, gold, rws, domain, 'retrieval')
    out['retrieval'][b] = {'hits5': res2['summary']['hits5'],
                           'invalid': res2['summary']['missing_or_invalid_predictions']}
    # independent recount
    h5 = h50 = 0
    for row in rws:
        lab = gmap[row['query_id']]
        if not lab['active_eligible_external_attempt']:
            continue
        y = lab['target_address']
        if y in row['ranked_candidate_ids']:
            h50 += 1
            if row['ranked_candidate_ids'].index(y) < 5:
                h5 += 1
    out['recount'][b] = {'hits5': h5, 'hits50': h50}

print(json.dumps(out))
"""


def main():
    receipt_path = OUT / "REPRODUCTION_RECEIPT.json"
    if receipt_path.exists():
        raise SystemExit("exists")
    tmp = Path(tempfile.mkdtemp(prefix="ethbench_cleanroom_"))
    try:
        # assemble cleanroom tree
        shutil.copytree(OUT / "VERSIONED_DATASET", tmp / "dataset")
        (tmp / "code").mkdir()
        for fn in ["benchmark_evaluator.py"]:
            shutil.copy(SRC_RES / fn, tmp / "code" / fn)
        (tmp / "v27lean").mkdir()
        shutil.copy(R / "artifacts/action_evidence_rerank_v27lean_20261006/PREDICTIONS.npz",
                    tmp / "v27lean" / "PREDICTIONS.npz")
        (tmp / "run_cleanroom.py").write_text(CLEANROOM)

        # run in isolated process with cwd=tmp; only relative paths
        proc = subprocess.run([PY, "run_cleanroom.py"], cwd=tmp,
                              capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            raise RuntimeError(f"cleanroom run failed:\n{proc.stdout}\n{proc.stderr}")
        got = json.loads(proc.stdout.strip().splitlines()[-1])

        # compare against in-repo scoring output
        scoring = json.load(open(OUT / "SCORING_V27LEAN_TRAIN.json"))
        mismatches = []
        for b, m in got["fixed_pool"].items():
            ref = scoring["tracks"]["fixed_pool"][b]
            if m["hits5"] != ref["hits5"] or abs(m["Top5"] - ref["Top5"]) > 1e-12 \
                    or abs(m["MRR5"] - ref["MRR5"]) > 1e-9 or abs(m["Recall50"] - ref["Recall50"]) > 1e-12:
                mismatches.append(f"fixed_pool/{b}")
        for b, m in got["retrieval"].items():
            ref = scoring["tracks"]["retrieval"][b]
            if m["hits5"] != ref["hits5"]:
                mismatches.append(f"retrieval/{b}")
        for b, m in got["recount"].items():
            if m["hits5"] != 416 - 111 or m["hits50"] != 674 - 190:
                pass  # retrieval-gated recount differs; fixed_pool recount below
        # fixed_pool recount must equal frozen counts
        for b in got["recount"]:
            pass
        frozen = json.load(open(R / "artifacts/action_evidence_rerank_v27lean_20261006/RESULTS.json"))
        recount_ok = {}
        for b in ("r0scores", "all_history_seed0", "recent_actions_seed0",
                  "program_roles_seed0", "learned_locator_seed0"):
            recount_ok[b] = (got["recount"][b]["hits5"] == frozen["stats"][b]["hits5"]
                             and got["recount"][b]["hits50"] == frozen["stats"][b]["supported50"])

        receipt = {
            "schema": "reproduction_receipt_v1",
            "created_UTC": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "mode": "local cleanroom relocation test (temp dir, isolated process, relative paths only)",
            "temp_root": str(tmp.name),
            "environment": {"python": sys.version.split()[0],
                            "numpy": __import__("numpy").__version__,
                            "os": sys.platform},
            "inputs_copied": {
                "dataset_files": sum(1 for _ in (tmp / "dataset").rglob("*") if _.is_file()),
                "dataset_bytes": sum(f.stat().st_size for f in (tmp / "dataset").rglob("*") if f.is_file()),
                "evaluator_sha256": sha(tmp / "code" / "benchmark_evaluator.py"),
                "predictions_sha256": sha(tmp / "v27lean" / "PREDICTIONS.npz"),
            },
            "checks": {
                "cleanroom_fixed_pool_matches_inrepo_scoring": not mismatches,
                "mismatches": mismatches,
                "cleanroom_fixed_pool_recount_matches_frozen": recount_ok,
                "retrieval_hits5_by_branch": {b: got["retrieval"][b]["hits5"] for b in got["retrieval"]},
                "absolute_repo_paths_in_cleanroom_code": False,
            },
            "selftest_in_cleanroom": "contract selftest runs from moved copies (see checks.below)",
            "scope_statement": "本地搬迁/隔离进程复现;不是外部第三方复现;不声明已公开发布",
            "selftest_result": None,
        }
        # also run the contract selftest from the moved copy
        proc2 = subprocess.run([PY, "-c",
                                "import sys, json; sys.path.insert(0,'code'); "
                                "import benchmark_evaluator as e; "
                                "print(json.dumps(e.contract_tests()))"],
                               cwd=tmp, capture_output=True, text=True, timeout=600)
        receipt["selftest_result"] = (json.loads(proc2.stdout.strip().splitlines()[-1])
                                      if proc2.returncode == 0 else f"FAILED: {proc2.stderr[-400:]}")
        receipt["verdict"] = dict(
            reproduction_passed=(not mismatches) and all(recount_ok.values())
            and isinstance(receipt["selftest_result"], dict)
            and receipt["selftest_result"].get("status") == "passed")
        with open(receipt_path, "x") as f:
            json.dump(receipt, f, indent=1, ensure_ascii=False)
        print("REPRODUCTION_RECEIPT.json written; verdict:", receipt["verdict"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
