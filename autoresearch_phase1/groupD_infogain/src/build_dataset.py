"""Build the Group D experiment dataset from Group A's leak-safe as-of assets.

Outputs (results/):
  dataset_full_20220901.parquet   all 18,519 wallets at cutoff 2022-09-01
  dataset_subset_20220901.parquet representative bounded subset (default 3,000)

No BigQuery is needed here; Group A already materialized the as-of feature matrix.
Labels are fwd30 from wallet_asof_features_20220901 (label window [cutoff, cutoff+30d)).
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config as C


def load_feature_matrix() -> pd.DataFrame:
    df = pd.read_parquet(C.FEATURE_MATRIX)
    assert (df["snapshot_date"].astype(str) == C.CUTOFF).all(), "snapshot must be 2022-09-01"
    return df


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    for name, expr in C.TARGETS.items():
        df[name] = df.eval(expr).astype(int)
    return df


def add_volume_and_persona(df: pd.DataFrame) -> pd.DataFrame:
    # volume proxy = native_usd + token_usd_priced (as-of; NaN -> treat as 0 USD)
    df["volume_usd"] = df["native_usd"].fillna(0.0) + df["token_usd_priced"].fillna(0.0)
    # log1p volume for residual analysis
    df["log_volume_usd"] = np.log1p(df["volume_usd"])
    # persona assignments (community masking)
    pers = pd.read_csv(C.PERSONA)
    df = df.merge(pers, on=["target_address", "target_exgraph_node_id"], how="left")
    return df


def feature_columns(df: pd.DataFrame) -> list:
    known = set(C.ID_COLS + C.LABEL_COLS + list(C.TARGETS.keys()) +
                ["volume_usd", "log_volume_usd"] + C.PERSONA_COLS)
    cols = [c for c in df.columns if c not in known]
    # keep only numeric / boolean columns (drop any stray objects)
    keep = []
    for c in cols:
        if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]):
            keep.append(c)
    return keep


def make_subset(df: pd.DataFrame, n: int = C.SUBSET_N, seed: int = C.SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # stratified by primary target to preserve base rate
    strat = df[C.PRIMARY_TARGET]
    per_class = {v: max(1, int(n * (strat == v).mean())) for v in [0, 1]}
    idx = []
    for v, k in per_class.items():
        pool = df.index[strat == v].to_numpy()
        chosen = rng.choice(pool, size=min(k, len(pool)), replace=False)
        idx.append(chosen)
    idx = np.concatenate(idx)
    rng.shuffle(idx)
    return df.loc[idx].copy()


def main() -> None:
    df = load_feature_matrix()
    df = add_targets(df)
    df = add_volume_and_persona(df)
    feats = feature_columns(df)
    print(f"[build] full rows={len(df)} features={len(feats)}")
    for t in C.TARGETS:
        print(f"[build] {t}: pos_frac={df[t].mean():.3f}")
    df.to_parquet(C.RESULTS / "dataset_full_20220901.parquet", index=False)

    sub = make_subset(df, C.SUBSET_N, C.SEED)
    print(f"[build] subset rows={len(sub)} (target {C.PRIMARY_TARGET} pos_frac={sub[C.PRIMARY_TARGET].mean():.3f})")
    sub.to_parquet(C.RESULTS / "dataset_subset_20220901.parquet", index=False)

    # quick coverage sanity
    for col in ["volume_usd", "log_volume_usd"]:
        print(f"[build] {col} nonnull={sub[col].notna().sum()}")
    print("[build] feature cols sample:", feats[:5], "...")
    manifest = {
        "cutoff": C.CUTOFF,
        "lookback": C.LOOKBACK,
        "label_window": C.LABEL_WINDOW,
        "full_rows": int(len(df)),
        "subset_rows": int(len(sub)),
        "seed": C.SEED,
        "n_features": len(feats),
        "features": feats,
        "targets": C.TARGETS,
        "note": "features strictly before cutoff; labels fwd30 [cutoff, cutoff+30d); "
                "single-cutoff wallet-level split (no cross-window mixing)",
    }
    import json
    (C.RESULTS / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("[build] done -> results/dataset_*_20220901.parquet")


if __name__ == "__main__":
    main()
