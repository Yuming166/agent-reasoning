# Conditional Phase 2 design inputs — do not execute

Question: does richer natural-language claim structure add information beyond simpler representations?

M0: recent-dynamics numeric baseline only.
M1: M0 + structured consequence only.
M2: M0 + template verbalization.
M3: M0 + full natural-language claim.
M4: M0 + claim + evidence pointer + scope/horizon + falsifier + qualification.
M5: text-ablated structured representation with exactly the same non-language fields as M4.

Primary comparisons: M4 vs M0/M1/M2/M5 and M3 vs M1.
Metrics: macro log loss, Brier, calibration error, per-target log loss, paired bootstrap,
wallet-cluster bootstrap. No threshold tuning from Phase 1 is allowed.
Synthetic-only power effect sizes: 0.005, 0.010, 0.020, 0.030 delta log loss.
