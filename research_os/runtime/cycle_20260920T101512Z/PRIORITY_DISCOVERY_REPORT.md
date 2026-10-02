# Decision-State case-level Evidence–Validity discovery audit

This is a deterministic, discovery-only audit of frozen OOS predictions. It is not a confirmatory result and does not modify the V1 protocol or test set.

- OOS rows: **2000** ({'dev': 1000, 'test': 1000})
- F = frozen intervention sensitivity; Delta = B4 macro log-loss minus B0 macro log-loss.
- Pearson(F, Delta): **-0.0334**
- Spearman(F, validity proxy -Delta): **0.0194**
- Partial Pearson(F, Delta | predeclared controls): **-0.0383**
- Mean Delta: **0.023495**; median Delta: **-0.011282**
- B4 gain rate (Delta < 0): **0.536**; failure rate (Delta > 0): **0.464**

## Outputs

- `priority_case_level.csv`: case-level F/Delta and frozen descriptors.
- `priority_by_F_quintile.csv`: discovery strata by intervention sensitivity.
- `high_F_failure_cases.csv`: high-sensitivity cases where B4 degraded.
- `low_F_success_cases.csv`: low-sensitivity cases where B4 improved.

## Boundary

This audit cannot establish causality, true belief, owner psychology, generalization beyond the frozen panel, or a final paper claim. Any follow-up requires Astra6 adversarial review and a new preregistered protocol/untouched holdout.
