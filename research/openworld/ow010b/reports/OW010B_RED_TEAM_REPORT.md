# OW-010B Red-Team Report

**Date:** 2026-09-18 UTC
**Role:** adversarial audit after the frozen primary analysis
**Conclusion:** structural branch fails; M1 is retained only as a bounded predictive finding

## Red-team question

Could the apparent incremental result be explained by future leakage, target construction, activity scale, wallet identity, temporal non-replication, model-selection artifacts, or ambiguous structural semantics rather than the claimed temporal/structural signal?

## Findings

| threat | assessment | evidence | disposition |
|---|---|---|---|
| Future event leakage into discovery features | no detected violation | OW-010A/OW-010B QA; strict pre-cutoff timestamps; physically separate evaluation table | claim of leakage-safe construction survives, subject to ordinary source-query audit limits |
| Future-conditioned inclusion | no | primary filter is `history_event_count_30d >= 1`; no future activity or matching filter | discovery population is not future-conditioned |
| Target leakage | no direct leakage, but target is autoregressive | target is future-minus-score-window; M1 includes score-window as-of features | valid forecasting design; limits mechanistic interpretation |
| Transformer/test contamination | no detected violation | fit transforms on June or June+July only | survives |
| Wallet-address identity feature | no | address used only for joins/audits; no raw counterparty IDs | survives |
| Repeated-wallet identity proxy | important limitation | 13,989/14,683 August test wallets are repeated | report as within-wallet forecasting; no identity-generalization claim |
| Activity confounding | unresolved/high | entropy/activity rho 0.963; rapid-forwarding/activity rho about 0.907; M1 gain persists in strata but not orthogonalized | M1 is provisional; M2 structural claim blocked |
| Volume/degree confounding | unresolved | gains persist by quartiles; added structure remains correlated with degree/activity | no independence claim |
| Target dominated by activity | partial concern | target has scale coordinates and composition coordinates; M0 controls scale, but recent-state variables are in M1 | report target as multivariate change, not pure surprise mechanism |
| Negative control artifact | not supported | permuted added features do not reproduce gains | supports, but does not rule out all confounding |
| Temporal overclaim | high | only one frozen held-out cutoff; July is development | no broad temporal-generalization claim |
| Hyperparameter boundary | medium | Ridge alpha=100 selected for all ladders | protocol limitation; do not repair post hoc |
| Model-family dependence | decisive for M2 | Ridge M2-M1 +0.134%; HGB M2-M1 -0.030% with CI crossing zero | structural gate fails |
| Ambiguous motif semantics | contained | M2_EXTENDED excluded; rapid forwarding is a bounded adjacency proxy | no motif-specific claim; no ablation available |
| Reporting-only implementation bug | repaired | first confound audit had index alignment issue; regenerated before report | disclose; primary results unaffected |
| Multiple testing / rescue | controlled | nested preregistered ladder and frozen decision rules; no post-result tuning | no rescue allowed |

## Primary numerical challenge

The strongest apparent structural number is the Ridge August M2_CORE-over-M1 improvement:

```text
absolute: 0.000916887
relative: 0.133750%
95% wallet-bootstrap CI: [0.000316163, 0.001558689]
```

This does not meet the frozen structural requirement of at least 2% relative reduction. The corresponding HGB result is:

```text
absolute: -0.000204546
relative: -0.030080%
95% wallet-bootstrap CI: [-0.001042654, 0.000620966]
```

The correct red-team interpretation is therefore not “a statistically positive Ridge coefficient proves structure.” It is “a very small Ridge residual is present in one model family, while the preregistered cross-family structural claim fails.”

## Target circularity audit

The target is a change from the score window to the future window. The feature ladder includes score-window activity and composition variables. This is not future leakage: all score-window variables are available before `t`. It is, however, an explicitly autoregressive setup. A model can improve by learning persistence, reversion, and recent-state-to-future-change relationships. This is scientifically acceptable for the stated predictive question but prevents interpreting M1 as a pure temporal-organization test.

A future design revision should predeclare a separation between:

- recent activity level and autoregression;
- temporal organization conditional on that level;
- structural proxies residualized against scale/degree.

That revision must not be selected using the present August outcome.

## Activity and degree audit

The M1 gain remains positive after fixed stratification and after excluding the training-defined top 5% activity tail. This weakens the simple explanation “the model only wins on the largest wallets.” It does not establish conditional independence because:

- activity strata are coarse;
- features remain highly correlated within strata;
- target components include activity change;
- the audit is descriptive and not a formally orthogonalized conditional-information estimate.

The structural features are especially vulnerable to being scale proxies. Counterparty entropy has Spearman correlation about `0.963` with unique counterparties, and rapid-forwarding count is about `0.907` with event count/history activity. This is sufficient to block a strong structural-mechanism claim even though the negative controls are clean.

## Wallet overlap audit

The August test is mostly repeated wallets. The unseen/no-prior-eligible-row group has 694 wallets, above the 500 descriptive floor, but it is not a separately powered temporal generalization study. Similar direction in both strata is useful descriptive evidence only.

## Decision under hostile review

- M1-over-M0: retain as a **provisional recent-dynamics predictive finding**.
- M2-over-M1: classify as **insufficient and exploratory**, not structural support.
- M2-over-M0: do not call it a structural result; it is inherited from M1.
- External validation: closed.
- GNN: not justified.
- Post-result tuning/rescue: prohibited.

The red-team conclusion matches Astra6's hostile review: `NO_GO_TO_OW010C under the frozen rule`, with any future continuation requiring `MODIFY_BEFORE_EXTERNAL_VALIDATION` through a new preregistered design.
