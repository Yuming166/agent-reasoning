"""Model helpers for Group D masking experiments (CPU, sklearn only).

All preprocessing is fit on train folds only (no leakage into eval).
Predicted probabilities are clipped to [eps, 1-eps] for stable NLL.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, log_loss

EPS = 1e-6


def clip(p: np.ndarray) -> np.ndarray:
    return np.clip(p, EPS, 1.0 - EPS)


def nll(y: np.ndarray, p: np.ndarray) -> float:
    p = clip(p)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def make_model(name: str, seed: int = 2022):
    if name == "logistic":
        return LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=seed)
    if name == "histgbm":
        return HistGradientBoostingClassifier(
            max_iter=250, learning_rate=0.1, max_leaf_nodes=31,
            l2_regularization=1.0, min_samples_leaf=20,
            early_stopping=True, validation_fraction=0.1, n_iter_no_change=15,
            random_state=seed,
        )
    raise ValueError(name)


class Pipeline:
    """Median-impute + scale (logistic only) wrapper so masking is explicit."""

    def __init__(self, model_name: str, seed: int = 2022):
        self.model_name = model_name
        self.seed = seed
        self.medians_: np.ndarray | None = None
        self.scaler_ = None
        self.model_ = None

    def _prep_X(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        if fit:
            self.medians_ = np.nanmedian(X, axis=0)
        X_imp = np.where(np.isnan(X), self.medians_, X)
        if self.model_name == "logistic":
            if fit:
                self.scaler_ = StandardScaler().fit(X_imp)
            return self.scaler_.transform(X_imp)
        return X_imp

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Pipeline":
        Xp = self._prep_X(X, fit=True)
        self.model_ = make_model(self.model_name, self.seed)
        self.model_.fit(Xp, np.asarray(y))
        return self

    def predict_proba1(self, X: np.ndarray) -> np.ndarray:
        Xp = self._prep_X(X, fit=False)
        return clip(self.model_.predict_proba(Xp)[:, 1])


def mask_features(X: np.ndarray, medians: np.ndarray, indices: np.ndarray | None = None) -> np.ndarray:
    """Replace selected rows (default all) with training-median baseline values."""
    X = np.asarray(X, dtype=float).copy()
    rows = np.arange(X.shape[0]) if indices is None else np.asarray(indices)
    X[rows, :] = medians[None, :]
    return X
