"""COMM group - pull day-level matched-matched primary edges (bounded).

One read-only BigQuery pull over [2022-03-03, 2022-09-01) UTC with partition
predicate + maximum_bytes_billed cap. Writes results/data/edges_day_20220303_20220901.csv.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research" / "community_temporal" / "src"))

def main() -> None:
    sql = (ROOT / "research" / "community_temporal" / "sql" / "edges_asof_day.sql").read_text()
    # reuse Group C's bounded client pattern (proxy + ADC, read-only)
    from bq_client import run_bounded_query
    t0 = time.time()
    rows = run_bounded_query(sql, max_bytes_billed=2 * 1024**3)
    out = ROOT / "research" / "community_temporal" / "results" / "data" / "edges_day_20220303_20220901.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("u,v,direction,month,day,weight\n")
        for r in rows:
            f.write(f"{r['u']},{r['v']},{r['direction']},{r['month']},{r['day']},{r['weight']}\n")
    print(f"[pull] wrote {len(rows)} rows -> {out} in {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
