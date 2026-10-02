# Matching Diagnostics (Frozen OW-009)

The CSV is a copy of the existing OW-009 diagnostic; no matching procedure was rerun or tuned.

| cutoff | treated entering | matched | unmatched | unique controls | reuse rate | before max SMD | after max SMD | covariates failing after |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2022-06-01 | 19 | 19 | 0 | 72 | 0.2421 | 1.0034 | 0.6575 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change |
| 2022-07-01 | 15 | 15 | 0 | 53 | 0.2933 | 1.4036 | 0.8699 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;activity_change |
| 2022-08-01 | 18 | 18 | 0 | 66 | 0.2667 | 1.2657 | 0.4706 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change |
