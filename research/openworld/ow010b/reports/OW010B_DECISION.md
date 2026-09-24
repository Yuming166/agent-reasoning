# OW-010B Decision

**Date:** 2026-09-18 UTC
**Experiment:** OW-010B — Blind Incremental Temporal-Structural Signal Test
**Decision:** `NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`

## Decision basis

The frozen August test supports an M1-over-M0 predictive gain but not the preregistered structural-support criterion:

- Ridge M1-over-M0: `11.660%`, absolute paired 95% CI `[0.085655, 0.095335]`.
- Ridge M2_CORE-over-M1: `0.1338%`, absolute paired 95% CI `[0.000316, 0.001559]`, below the frozen `2%` gate.
- HGB M2_CORE-over-M1: `-0.0301%`, CI `[-0.001043, 0.000621]`.
- Negative controls did not reproduce the intended gains.
- Activity/degree audits do not eliminate the possibility that M1/M2 variables are scale and autoregression proxies.
- The test contains one frozen held-out cutoff and is dominated by repeated wallets.

## Operational disposition

- **Do not open OW-010C.** No external-label evaluation is authorized by this result.
- **Do not build a Temporal GNN.** The simple structural block did not pass the frozen gate.
- **Do not start latent-strategy/LLM inference.**
- **Do not retune the target, thresholds, feature block, model grid, cutoffs, or decision rule using the August result.**
- Preserve the M1 result as a bounded/provisional recent-dynamics forecasting finding.
- Classify M2 structural evidence as insufficient and exploratory.
- If the research continues, create a new preregistered amendment before any new result is inspected; it should separate recent activity/autoregression from temporal organization and address structural/activity collinearity.

## Status labels

```text
M1 recent-dynamics signal: PROVISIONAL_PREDICTIVE_FINDING
M2 structural signal: NO_GO_UNDER_FROZEN_GATE
OW-010C: CLOSED
Temporal GNN: NOT_JUSTIFIED
Wash-label access: FALSE
```

Astra6 used the compatible operational phrase `NO_GO_TO_OW010C under the frozen rule; MODIFY_BEFORE_EXTERNAL_VALIDATION` for a possible future redesign. The formal OW-010B decision field remains exactly:

```text
NO_GO_OPENWORLD_STRUCTURAL_SIGNAL
```
