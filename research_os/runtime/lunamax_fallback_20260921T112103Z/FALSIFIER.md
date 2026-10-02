## 1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)

| Branch | Verdict | Falsifier’s assessment |
|---|---|---|
| **A: Evidence-Validity Gap** | **MODIFY** | The data support only a narrower claim: intervention responsiveness does not guarantee predictive usefulness. The current \(F\) may primarily measure prompt, format, or model instability rather than evidence validity. |
| **B: Behavioral Equifinality** | **HOLD** | No result yet shows two semantically distinct hypotheses that fit the same observations while making different future predictions. Ordinary calibrated uncertainty, activity, or autoregression remains a simpler explanation. |
| **C: Falsifiable Behavioral Hypothesis Induction** | **MODIFY** | The frozen B4 effectiveness result is NO-GO. Retain only as a task proposal requiring explicit scope, horizon, observable consequence, and falsifier; structured LLM features alone do not establish NLP centrality. |
| **D: Behavioral Hypothesis Revision** | **UNTESTED** | Evidence interventions are not sequential hypothesis revision. There is no demonstrated retention, qualification, or retraction of a prior linguistic commitment under genuinely new evidence. |
| **E: Predictability × Interpretability** | **KILL** | As currently defined, this is a generic two-axis comparison. Interpretability is not independently operationalized, and the contribution does not require language. |
| **F: Identifiability-Aware Selective Inference** | **MODIFY** | Identifiability must mean membership in an observational-equivalence set, not merely high entropy, JS distance, low confidence, or abstention. It must beat calibrated uncertainty and selective-prediction baselines at matched coverage. |

## 2. Strongest evidence

- The strongest deterministic result is the frozen effectiveness failure: B4 macro log loss was **0.840193** versus **0.810633** for B0, with B4 degradation \(+0.029560\) and the reported paired 95% interval entirely above zero. B4 also failed against B2.
- July intervention responsiveness passed operationally, but this did not transfer to frozen predictive effectiveness. The discovery audit likewise found almost no simple ordering: \(F\)-versus-\(\Delta\) Pearson \(=-0.0334\), Spearman \(=-0.0194\), and partial Pearson \(=-0.0383\).
- Mean case degradation was positive despite 53.65% case-level gains; the negative mean/median split suggests tail failures or subgroup concentration, not a general certificate. The selected 50 high-\(F\) failures and 50 low-\(F\) successes are not prevalence estimates.
- OW-010B already warns that the M1 gain and any apparent structural gain may be activity/scale/autoregression proxies, with repeated wallets and one frozen cutoff.
- The JS calculation is deterministic conditional on generated responses, but the responses themselves are model-generated advice, not evidence of owner psychology, intent, causal provenance, or a latent decision state.

## 3. Strongest counterargument

The observed \(F\)-versus-\(\Delta\) mismatch may not be an evidence-validity phenomenon at all. \(F\) measures output displacement under interventions, while \(\Delta\) measures downstream loss after feature integration; B4 could fail because of calibration, feature aggregation, or meta-head misspecification even when an individual hypothesis is defensible.

Likewise, the current activity controls are not proof of orthogonality. Categorical activity bins and count covariates may leave residual recency, event-rate, degree, last-event, wallet-specific, and repeated-row effects. A simple recent-dynamics model could therefore explain both apparent “structural” signal and heterogeneous LLM gains without invoking equifinality or identifiability.

## 4. Cheapest decisive experiment

Run a **two-stage falsification gate**, with no large LLM experiment:

1. **Deterministic artifact reanalysis first.** On the fixed artifacts, use one-row-per-wallet or wallet-blocked evaluation; exact/propensity-match on 7/30-day counts, recency, history length, event family, degree/activity, and split. Compare B0, B2, B4, and a deliberately explicit autoregressive baseline. Use wallet-blocked bootstrap and negative-control targets. Treat August results as post-hoc diagnostics only, not as a new development set.
2. **Only if the first gate is informative, run a small pre-registered prompt/evidence null test.** Cross actual evidence versus placebo evidence with original versus semantic-preserving prompt/format paraphrases, holding output schema, position, and token budget fixed. Estimate residual evidence sensitivity after subtracting prompt sensitivity.
3. **Equifinality kill test.** Count only cases with two semantically distinct hypotheses that both satisfy the same pre-outcome observation constraints but imply different pre-registered held-out consequences. Compare against a single calibrated predictive distribution, entropy, ensemble variance, and abstention at matched coverage. High uncertainty without distinct consequences is not equifinality.
4. **C/D language test.** Remove or template the natural-language explanation while preserving structured slots. For D, shuffle evidence order and test whether propositions are retained, qualified, or retracted differently from an irrelevant-evidence control.

## 5. Stop condition

- **A/F stop:** placebo or prompt-paraphrase JS is comparable to actual-evidence JS, or the residual evidence effect disappears.
- **B stop:** no reproducible pair of observationally equivalent but outcome-divergent hypotheses exists, or ordinary calibrated uncertainty matches the result at matched coverage.
- **C stop:** a rule/template or text-ablated system matches the LLM while preserving the same structured features, or explicit falsifiers are absent.
- **D stop:** evidence order, relevant evidence, and irrelevant evidence produce indistinguishable revision behavior.
- **Activity/autoregression stop:** B4/M2 gains vanish after wallet blocking and activity/recency matching, or a negative-control/autoregressive baseline reproduces them.
- **Global stop:** do not open OW-010C, build a Temporal GNN, or launch a large LLM study unless the prompt-null, activity/autoregression, and equifinality gates all survive. Any positive result obtained by retuning August remains post-hoc.

## 6. Literature/novelty verification still required

Before any novelty claim, perform a dated title/abstract/code/data overlap audit covering:

- behavioral equifinality, observational equivalence, inverse planning, partial observability, and ambiguous-intent modeling;
- falsifiable or executable natural-language hypothesis generation and evidence-grounded scientific reasoning;
- sequential belief revision, evidence-conditioned proposition updating, retraction, and qualification;
- selective prediction, abstention, calibration, risk-coverage, conformal methods, and uncertainty decomposition;
- explanation faithfulness, intervention-based evaluation, semantic consistency, and prompt sensitivity;
- temporal/address-level forecasting with activity, recency, degree, repeated-entity, and autoregressive confounds.

For each candidate, verify the exact task definition, hypothesis representation, intervention/null condition, labels, baselines, temporal split, code/data availability, and minimal runnable result. Novelty remains unestablished unless the surviving branch is operationally distinct from these existing formulations and the relevant kill tests pass.