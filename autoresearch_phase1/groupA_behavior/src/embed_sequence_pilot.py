"""Sequence-embedding representation pilot (bounded).

Pulls the ordered action-symbol sequences for a deterministic subsample of
800 wallets (cutoff 2022-09-01, 90-day lookback), embeds them with a local
TF-IDF bag-of-n-grams (ngram 1-2), and compares clustering silhouette against
the handcrafted numeric representation on the SAME 800-wallet subset.

This is a pilot on a small bounded sample, NOT an effectiveness claim. It
demonstrates whether action ORDER adds cluster structure beyond aggregates.
Neural/LLM embeddings are out of scope here (see Group E); this uses local,
deterministic vectorization only (no GPU, no LLM calls).

Outputs:
  results/sequence_embedding_pilot.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
import bq_client  # noqa: E402
import cluster_personas as cp  # noqa: E402
import config  # noqa: E402

SEED = config.EMBED_SEED
N = config.EMBED_PILOT_N


def pull_sequences(wallets: list[str]) -> pd.DataFrame:
    addr_list = ", ".join(f"'{w}'" for w in wallets)
    sql = f"""
WITH targets AS (
  SELECT DISTINCT target_address
  FROM UNNEST([{addr_list}]) AS target_address
),
ev AS (
  SELECT e.target_address, e.block_timestamp, e.direction, e.self_transaction,
         e.event_family, e.block_number, e.transaction_index, e.event_index
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901` e
  JOIN targets t ON t.target_address = e.target_address
  WHERE e.block_timestamp >= TIMESTAMP('2022-06-03')
    AND e.block_timestamp <  TIMESTAMP('2022-09-01')
    AND e.sequence_role = 'primary'
),
sym AS (
  SELECT target_address,
    CASE WHEN self_transaction THEN 'S'
         WHEN event_family = 'external_tx' AND direction = 'outgoing' THEN 'ON'
         WHEN event_family = 'external_tx' AND direction = 'incoming' THEN 'IN'
         WHEN event_family = 'token_transfer' AND direction = 'outgoing' THEN 'OT'
         WHEN event_family = 'token_transfer' AND direction = 'incoming' THEN 'IT'
         ELSE 'X' END AS symbol,
    block_timestamp, block_number, transaction_index, event_index
  FROM ev
)
SELECT target_address,
  STRING_AGG(symbol, ' ' ORDER BY block_timestamp, block_number,
             transaction_index, event_index) AS seq
FROM sym
GROUP BY target_address
"""
    rows = bq_client.run_bounded_query(sql, max_bytes_billed=config.MAX_BYTES_BILLED)
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_parquet(config.RESULTS / "data" / "feature_matrix_20220901.parquet")
    rng = np.random.default_rng(SEED)
    wallets = df["target_address"].sample(n=N, random_state=SEED).tolist()
    print(f"[pilot] sampling {N} wallets (seed={SEED})")
    seq = pull_sequences(wallets)
    seq = seq.set_index("target_address")

    # --- sequence embedding ---
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X_emb = vec.fit_transform(seq["seq"])
    n_emb = X_emb.shape[1]
    print(f"[pilot] embedding dims (tfidf 1-2 gram) = {n_emb}")

    # --- numeric representation on the same subset ---
    sub = df[df["target_address"].isin(seq.index)].copy()
    sub = cp.add_derived(sub)
    X_num = cp.prepare_matrix(sub, [cp.ACTIVITY, cp.CAPITAL, cp.COUNTERPARTIES,
                                    cp.NETWORK, cp.TRAJECTORY])
    X_num.index = sub["target_address"]           # index = wallet address
    order = seq.index.tolist()                    # seq order from SQL
    X_num_np = X_num.reindex(order).to_numpy()
    X_emb_np = X_emb.toarray()                    # rows already in seq order

    def sil(X: np.ndarray, k: int = 5) -> float:
        lab = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X).labels_
        return float(silhouette_score(X, lab))

    out = {
        "cutoff": config.CUTOFF,
        "sample_scope": f"{N} deterministic wallets (seed {SEED}) from the 18,519-wallet bounded sample",
        "embedding": "local TF-IDF bag-of-2-gram action symbols (deterministic, no LLM/GPU)",
        "symbols_used": ["ON", "IN", "OT", "IT", "S", "X"],
        "n_embedding_dims": int(n_emb),
        "silhouette_numeric_k5": sil(X_num_np),
        "silhouette_sequence_embedding_k5": sil(X_emb_np),
        "mean_seq_len": float(seq["seq"].str.split().str.len().mean()),
        "n_wallets_with_seq": int(len(seq)),
    }
    (config.RESULTS / "sequence_embedding_pilot.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("[ok] wrote results/sequence_embedding_pilot.json")


if __name__ == "__main__":
    main()
