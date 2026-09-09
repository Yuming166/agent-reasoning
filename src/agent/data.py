"""Load the stratified LLM panel and build frozen, leakage-safe features.

Hard rule: truth_g_rank / stratum / activity / pop_weight / label-derived
quantities never enter a model or prompt. Candidate features are pre-snapshot.
"""
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PANEL_DIR = os.path.join(ROOT, "artifacts", "llm_panel_v1")
SNAPSHOTS = ["2022-06-01", "2022-07-01", "2022-08-01"]
EVENT_KEY = ["snapshot_date", "target_address", "target_sequence_index"]

# NOTE: cand_source one-hots must NOT be features: the positive has the
# unique source value 'positive', which would encode the label. Only numeric
# pre-snapshot behavioral features are allowed.
FEATURE_COLS = [
    "log_g_cnt", "log_g_rank", "log_personal_cnt", "log_days_since",
    "log_bridge_paths", "log_bridge_signal", "is_personal", "is_bridge",
]
META_COLS = EVENT_KEY + ["counterparty_address", "cp_type", "evt_cnt_90d",
                         "cp_entropy_90d", "cp_new_rate_30d", "active_days_90d",
                         "stratum", "activity", "pop_weight", "truth_g_rank"]


def load_panel():
    ev = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(PANEL_DIR, "events", "*.csv.gz")))],
                   ignore_index=True)
    ca = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(PANEL_DIR, "candidates", "*.csv.gz")))],
                   ignore_index=True)
    ev["block_timestamp"] = pd.to_datetime(ev["block_timestamp"], utc=True)
    return ev, ca


def add_features(ca: pd.DataFrame) -> pd.DataFrame:
    df = ca.copy()
    df["log_g_cnt"] = np.log1p(df["g_cnt"].clip(lower=0))
    df["log_g_rank"] = np.log(df["g_rank"].clip(lower=1))
    df["log_personal_cnt"] = np.log1p(df["personal_cnt"].clip(lower=0))
    df["log_days_since"] = np.log(df["days_since"].clip(lower=1))
    df["log_bridge_paths"] = np.log1p(df["bridge_paths"].clip(lower=0))
    df["log_bridge_signal"] = np.log1p(df["bridge_signal"].clip(lower=0))
    df["is_personal"] = (df["personal_cnt"] > 0).astype(float)
    df["is_bridge"] = (df["bridge_paths"] > 0).astype(float)
    return df


def join_meta(ev: pd.DataFrame, ca: pd.DataFrame) -> pd.DataFrame:
    return ca.merge(ev[META_COLS], on=EVENT_KEY, how="left")
