#!/usr/bin/env python3
"""Fit/evaluate the frozen deterministic B0/B1 baselines."""
from __future__ import annotations
import os

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / 'research/decision_state/results'
PROTO = ROOT / 'research/decision_state/protocol'

TARGETS = ['activity', 'active_days', 'counterparty_breadth', 'new_counterparties']
CLASSES = ['down', 'same', 'up']
SPLIT_DATE = {'train': '2022-06-01', 'dev': '2022-07-01', 'test': '2022-08-01'}


def one_hot_probs(values, eps=0.05):
    out = np.full((len(values), 3), eps / 2, dtype=float)
    for i, v in enumerate(values):
        if v in CLASSES:
            out[i, CLASSES.index(v)] = 1 - eps
    return out


def metric_block(y, p):
    valid = pd.Series(y).notna().to_numpy()
    yv = np.asarray(y)[valid]
    pv = np.asarray(p)[valid]
    yi = np.array([CLASSES.index(x) for x in yv])
    pred = np.array([CLASSES[int(i)] for i in np.argmax(pv, axis=1)])
    return {
        'n': int(len(yv)),
        'log_loss': float(log_loss(yi, pv, labels=list(range(3)))),
        'balanced_accuracy': float(balanced_accuracy_score(yv, pred)),
        'macro_f1': float(f1_score(yv, pred, labels=CLASSES, average='macro', zero_division=0)),
    }


def deterministic_direction(df, target):
    # Fixed, transparent 7-day-vs-prior-23-day trend proxy. Thresholds are
    # frozen at 10% relative change; this is an interpretable control, not a
    # hand-tuned state label.
    if target == 'activity':
        cur = pd.to_numeric(df['event_count_7d'], errors='coerce')
        prior = (pd.to_numeric(df['event_count_30d'], errors='coerce') - cur).clip(lower=0) * 7 / 23
    elif target == 'active_days':
        cur = pd.to_numeric(df['active_days_7d'], errors='coerce')
        prior = (pd.to_numeric(df['active_days_30d'], errors='coerce') - cur).clip(lower=0) * 7 / 23
    elif target == 'counterparty_breadth':
        cur = pd.to_numeric(df['score_unique_counterparties_7d'], errors='coerce')
        prior = (pd.to_numeric(df['unique_counterparties_30d'], errors='coerce') - cur).clip(lower=0) * 7 / 23
    elif target == 'new_counterparties':
        cur = pd.to_numeric(df['new_counterparties_7d'], errors='coerce')
        prior = pd.to_numeric(df['unique_counterparties_30d'], errors='coerce').clip(lower=0) * 7 / 30
    else:
        raise KeyError(target)
    ratio = (cur + 0.5) / (prior + 0.5)
    out = np.where(ratio > 1.10, 'up', np.where(ratio < 1/1.10, 'down', 'same'))
    return pd.Series(out, index=df.index)


def main():
    prompt = pd.read_csv(RES / 'decision_state_prompt_cases.csv', low_memory=False)
    ev = pd.read_csv(RES / 'decision_state_eval_cases.csv', low_memory=False)
    df = prompt.merge(ev[['case_id'] + [f'y_{t}' for t in TARGETS]], on='case_id', validate='one_to_one')
    manifest = json.loads((RES / 'decision_state_case_manifest.json').read_text())
    m0 = manifest['m0_features']
    m1 = manifest['m1_features']
    # Retain only numeric as-of features and explicitly exclude market context
    # from M0/M1; market is reserved for the intervention prompt channel.
    def clean_feature_names(cols):
        return [c for c in cols if c in df.columns and c not in {'eth_close_asof','eth_return_1d','eth_return_7d','eth_volatility_7d','eth_drawdown_30d'}]
    m0 = clean_feature_names(m0)
    m1 = clean_feature_names(m1)
    for c in set(m1 + m0):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    train = df[df.split == 'train'].copy()
    dev = df[df.split == 'dev'].copy()
    fit = df[df.split.isin(['train', 'dev'])].copy()
    test = df[df.split == 'test'].copy()

    # Fit on train+dev after the fixed model contract is established; report
    # dev diagnostics separately and use test once for final predictions.
    pred_rows = df[['case_id','anchor_wallet','cutoff_date','split','activity_bin']].copy()
    summaries = []
    models = {}
    for baseline, feats in [('B0_M1', m1)]:
        for target in TARGETS:
            X_fit = fit[feats].replace([np.inf, -np.inf], np.nan)
            X_dev = dev[feats].replace([np.inf, -np.inf], np.nan)
            X_test = test[feats].replace([np.inf, -np.inf], np.nan)
            y_fit = fit[f'y_{target}']
            # Median imputation is fit on train+dev only and recorded; no future
            # outcome fields participate in the feature matrix.
            med = X_fit.median(numeric_only=True).fillna(0.0)
            X_fit = X_fit.fillna(med).fillna(0.0)
            X_dev = X_dev.fillna(med).fillna(0.0)
            X_test = X_test.fillna(med).fillna(0.0)
            model = HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                l2_regularization=1.0, random_state=42,
            )
            model.fit(X_fit, y_fit)
            models[(baseline,target)] = {'model': model, 'features': feats, 'median': med.to_dict()}
            # Align model probability columns to fixed class order.
            def predict_probs(X):
                raw = model.predict_proba(X)
                out = np.full((len(X),3), 1e-6, dtype=float)
                for j, cls in enumerate(model.classes_):
                    out[:, CLASSES.index(cls)] = raw[:,j]
                return out / out.sum(axis=1,keepdims=True)
            pdev, ptest = predict_probs(X_dev), predict_probs(X_test)
            for split_name, sub, p in [('dev',dev,pdev),('test',test,ptest)]:
                met=metric_block(sub[f'y_{target}'],p)
                met.update({'baseline':baseline,'target':target,'split':split_name})
                summaries.append(met)
            for split_name, sub, p in [('dev',dev,pdev),('test',test,ptest)]:
                for j, cls in enumerate(CLASSES):
                    pred_rows.loc[pred_rows.case_id.isin(sub.case_id), f'{baseline}__{target}__p_{cls}'] = p[:,j]

    # B1 deterministic proxy on all rows.
    for target in TARGETS:
        pred = deterministic_direction(df, target)
        probs = one_hot_probs(pred)
        for j, cls in enumerate(CLASSES):
            pred_rows[f'B1_DETERMINISTIC__{target}__p_{cls}'] = probs[:,j]
        for split_name, sub in [('dev',dev),('test',test)]:
            met=metric_block(sub[f'y_{target}'], probs[sub.index.to_numpy()])
            met.update({'baseline':'B1_DETERMINISTIC','target':target,'split':split_name})
            summaries.append(met)

    pred_rows.to_csv(RES / 'deterministic_baseline_predictions.csv', index=False)
    pd.DataFrame(summaries).to_csv(RES / 'deterministic_baseline_metrics.csv', index=False)
    model_manifest = {
        'protocol': 'decision_state_v1',
        'fit_rows': int(len(fit)),
        'train_rows': int(len(train)),
        'dev_rows': int(len(dev)),
        'test_rows': int(len(test)),
        'm0_features': m0,
        'm1_features': m1,
        'model': 'HistGradientBoostingClassifier',
        'hyperparameters': {'max_iter':200,'learning_rate':0.05,'max_leaf_nodes':15,'l2_regularization':1.0,'random_state':42},
        'classes': CLASSES,
        'targets': TARGETS,
    }
    (RES / 'deterministic_baseline_manifest.json').write_text(json.dumps(model_manifest, indent=2, ensure_ascii=False)+'\n')
    print(pd.DataFrame(summaries).to_string(index=False))

if __name__=='__main__':
    main()
