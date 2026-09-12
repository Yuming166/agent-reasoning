"""Embed Qwen summary texts with local Qwen3-Embedding-0.6B (1024-dim).

Embeds the RAW model output text (not the parsed JSON), so wallets whose JSON
failed to parse still contribute a semantic vector. Disk-cached / resumable.
Outputs results/qwen_embeddings_20220901.jsonl (+ .npy for the matrix).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def embed_texts(texts: list[str]) -> list[list[float]]:
    payload = {"model": config.EMBED_MODEL, "input": texts}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        config.EMBED_BASE + "/embeddings",
        data=body, headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(config.MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=config.TIMEOUT_S) as r:
                out = json.loads(r.read().decode())
            items = sorted(out["data"], key=lambda d: d["index"])
            return [it["embedding"] for it in items]
        except Exception as e:  # noqa: BLE001
            last = repr(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embed failed after {config.MAX_RETRIES}: {last}")


def main() -> None:
    summaries = []
    for line in open(config.SUMMARIES_JSONL, encoding="utf-8"):
        summaries.append(json.loads(line))

    done = {}
    if config.EMBEDDINGS_JSONL.exists():
        for line in open(config.EMBEDDINGS_JSONL, encoding="utf-8"):
            r = json.loads(line)
            done[r["target_address"]] = r
    todo = [s for s in summaries if s["target_address"] not in done]
    print(f"[embed] total={len(summaries)} cached={len(done)} todo={len(todo)}")

    BATCH = 16
    calls = 0
    fh = open(config.EMBEDDINGS_JSONL, "a", encoding="utf-8")
    try:
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            try:
                vecs = embed_texts([b["raw"] for b in batch])
            except Exception as e:  # noqa: BLE001
                print(f"[embed] FAIL batch {i}: {e}", flush=True)
                continue
            for b, v in zip(batch, vecs):
                fh.write(json.dumps({
                    "target_address": b["target_address"],
                    "dim": len(v),
                    "embedding": v,
                }, ensure_ascii=False) + "\n")
            fh.flush()
            calls += 1
            if (i // BATCH + 1) % 5 == 0:
                print(f"[embed] batches={i // BATCH + 1} calls={calls}", flush=True)
    finally:
        fh.close()

    rows = []
    for line in open(config.EMBEDDINGS_JSONL, encoding="utf-8"):
        rows.append(json.loads(line))
    n = len(rows)
    if n:
        mat = np.array([r["embedding"] for r in rows])
        np.save(config.EMBEDDINGS_NPY, mat)
        pd_addr = [r["target_address"] for r in rows]
        (config.RESULTS / "qwen_embedding_addresses_20220901.json").write_text(
            json.dumps(pd_addr, indent=2))
        stats_path = config.RESULTS / "call_stats_20220901.json"
        stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
        if calls > 0 or "n_embedding_calls" not in stats:
            stats.update({
                "phase2": "embedding",
                "embed_model": config.EMBED_MODEL,
                "embed_endpoint": config.EMBED_BASE,
                "n_embedded": n,
                "n_embedding_calls": calls,
                "embed_dim": int(mat.shape[1]),
                "embed_cache_path": str(config.EMBEDDINGS_JSONL),
                "embed_npy_path": str(config.EMBEDDINGS_NPY),
            })
            stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print("[resume] no new embedding calls; existing embedding stats preserved")
        print(f"[ok] embedded n={n} dim={mat.shape[1]} calls={calls} -> {config.EMBEDDINGS_NPY}")
    else:
        print("[warn] no embeddings produced; run summarize first")


if __name__ == "__main__":
    main()
