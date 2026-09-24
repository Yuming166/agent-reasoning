# Codex Response to Astra6 Hostile Review

**Date:** 2026-09-18 UTC
**Input:** `reports/ASTRA6_POSTHOC_CRITIQUE.json`
**Boundary:** no external wash/illicit labels were accessed or supplied

## Overall response

Astra6's hostile review is accepted. It does not identify a primary leakage violation or a result-selection violation, but it correctly narrows the scientific interpretation. The frozen data and model outputs support a bounded M1 predictive finding and do not support the preregistered M2 structural gate. No rerun, retuning, target redesign, cutoff selection, or model rescue will be performed after this review.

## Point-by-point response

### 1. “M1 is recent dynamics, not isolated temporal organization.”

**Accepted.** M1 combines inter-event gaps, burstiness, recent-vs-prior activity, counterparty novelty/turnover, and recent composition/direction. The model comparison establishes an incremental predictive contribution of this feature block, not a clean decomposition into temporal organization, recency, burstiness, or turnover. The result report therefore uses “M1 temporal/recent-dynamics” and explicitly avoids a stronger mechanistic label.

### 2. “M2 is below the 2% gate and not HGB-robust.”

**Accepted and decisive.** Ridge gives only `0.1338%` relative M2-over-M1 improvement with a positive absolute CI, while HGB gives `-0.0301%` with a CI crossing zero. The frozen rule requires at least 2% structural improvement and no model-family failure. M2 fails.

### 3. “Structural variables are activity/degree proxies.”

**Accepted as a major limitation.** The audit records Spearman correlations up to `0.963` for entropy versus unique counterparties and approximately `0.907` for rapid-forwarding count versus history/event count. Stratification and tail removal show that M1 is not confined to the largest wallets, but they do not establish orthogonality. No claim of independent structural information is made.

### 4. “Only one held-out cutoff limits temporal generalization.”

**Accepted.** July is development and August is the only frozen test. Similar M1 direction across July and August is a development-to-test replication, not a multi-period confirmation. The final report does not claim stable generalization beyond the available held-out cutoff.

### 5. “Repeated wallets dominate.”

**Accepted.** `13,989/14,683` August rows are repeated wallets and 694 have no eligible prior June/July row. The principal estimand is within-wallet temporal forecasting. The unseen analysis is descriptive and does not support identity-level generalization.

### 6. “Ridge alpha reached the grid boundary.”

**Accepted as a protocol limitation, not a violation.** All Ridge ladders selected `alpha=100`. The frozen experiment is not retuned after test inspection. A future design may predeclare a wider grid, but that would be a new experiment and cannot be used to revise the current conclusion.

### 7. “Aggregate QA is not a complete independent upstream re-audit.”

**Accepted.** OW-010B relies on the OW-010A data contract, source table manifests, executable key/count reconciliation, and compact aggregate checks. This supports the claim that the supplied substrate passed the declared QA; it is not a proof that no upstream source-query error is possible. The report keeps this distinction and does not elevate QA to an absolute guarantee.

### 8. “Do not open external validation.”

**Accepted.** The final decision is `NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`; OW-010C remains closed. Astra6's operational wording `MODIFY_BEFORE_EXTERNAL_VALIDATION` is recorded as a possible future disposition, not as permission to continue the current branch.

## Issues Astra6 did not change

- The discovery cohort remains defined without future-conditioned activity or matching eligibility.
- The target remains a signed multivariate change vector; scalar `S7` remains secondary.
- The pre-result score7 materialization amendment remains valid because it was made before primary result inspection and did not change the protocol.
- The reporting-only confound-audit repair remains disclosed and does not alter primary results.
- Negative controls remain informative but are not treated as proof of no confounding.

## Final Codex disposition

The strongest defensible claim is:

> Under the frozen event-level as-of substrate and chronological protocol, recent temporal/recent-dynamics features improve prediction of a signed seven-day future behavioral-change vector beyond the frozen M0 scale/activity/volume/degree baseline in the available August test. The conservative structural block M2_CORE does not provide the preregistered, model-family-robust incremental support needed to open external validation.

No stronger claim is made. The branch stops here.
