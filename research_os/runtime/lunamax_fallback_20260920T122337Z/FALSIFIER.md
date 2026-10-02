## 1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)

| Branch | Verdict | Falsifier’s assessment |
|---|---|---|
| **A: Evidence-Validity Gap** | **MODIFY** | The apparent gap is not established. \(F\) measures intervention-response magnitude, while \(\Delta\) measures predictive-loss change; prompt, activity, aggregation, split, and repeated-wallet effects remain plausible explanations. |
| **B: Behavioral Equifinality** | **UNTESTED** | No result shows that distinct behavioral hypotheses are equally compatible with the same observations. Ordinary calibrated uncertainty, rather than equifinality, remains the simpler explanation. |
| **C: Falsifiable Behavioral Hypothesis Induction** | **HOLD** | The frozen B4 effectiveness result is NO-GO. This branch survives only if explicit language claims with scope, horizon, and falsifiers add value beyond structured consequence vectors and recent-dynamics baselines. |
| **D: Behavioral Hypothesis Revision** | **UNTESTED** | Separate intervention prompts do not demonstrate sequential revision, qualification, retention, or retraction under time-ordered evidence. |
| **E: Predictability × Interpretability** | **KILL** | As a standalone contribution, the two-axis framing is generic and not demonstrably NLP-central. Existing outputs may remain descriptive controls, but this branch should not drive a new study. |
| **F: Identifiability-Aware Selective Inference** | **MODIFY** | Current \(F\) is intervention sensitivity, not identifiability. It must beat calibrated uncertainty, activity/history baselines, and prompt-variance controls at matched coverage. |

## 2. Strongest evidence

- The deterministic frozen result is negative: B4 macro log loss was **0.840193** versus **0.810633** for B0; the B4-minus-B0 degradation is **0.029560**, with the paired interval excluding improvement.
- July evidence responsiveness passed, but this did not transfer to frozen predictive effectiveness. This directly falsifies the inference “responsive intervention \(\Rightarrow\) useful behavioral signal.”
- The priority audit finds almost no ordering between intervention sensitivity and predictive degradation: Pearson \(=-0.0334\), Spearman \(=-0.0194\), and controlled Pearson \(=-0.0383\).
- OW-010B already found the structural increment over M1 below its frozen gate, while activity/degree and autoregressive explanations remain unresolved. M1 may partly reflect recent volume, persistence, or repeated-wallet structure.
- All textual hypotheses, consequence interpretations, and intervention responses are **model-generated advice**. They are not deterministic evidence of owner psychology, intent, social exposure, or causal provenance.

## 3. Strongest counterargument

The negative evidence may be comparing mismatched estimands rather than disproving semantic validity. Averaged JS response sensitivity and macro log-loss degradation need not align; B4 could be poorly calibrated or badly integrated even if some textual hypotheses are useful.

Likewise, activity confounding does not prove that no residual temporal structure exists, and failure of the frozen B4 protocol does not rule out a smaller language-centered task involving abstention, revision, or evidence auditing. These are legitimate redesign hypotheses, but they are not positive findings from the current artifacts.

## 4. Cheapest decisive experiment

Run an **artifact-first falsification gate with no new large LLM experiment**:

- **A:** Using existing outputs, decompose \(F\) by prompt/template, intervention type, consequence dimension, split, activity, history length, and wallet cluster. Recompute the \(F\)-versus-\(\Delta\) relation with OOS-only, activity-matched, wallet-clustered uncertainty. Kill A if the residual relation disappears or remains indistinguishable from zero.
- **B:** Define an explicit hypothesis class and equifinality criterion: two distinct hypotheses must have equivalent compatibility with the observed window but divergent, predeclared future consequences. Compare this against a calibrated entropy/ensemble-dispersion baseline. If entropy explains the ambiguity, or no such hypothesis pairs exist, kill B as equifinality.
- **C:** Strip each textual hypothesis to its structured consequence vector and compare against the full text under matched complexity. If free text adds no deterministic validity, calibration, or future-outcome information, kill the current induction formulation.
- **D:** Only after the artifact gate passes, run a small paired sequential test: confirmatory evidence, contradictory evidence, and irrelevant evidence in controlled temporal order. Require predeclared retain/qualify/retract behavior. Prompt-order artifacts or non-convergent final claims kill D.
- **E:** Remove language entirely and recompute the proposed predictability/interpretability analysis. If the result and contribution survive unchanged, that confirms E is not a distinct NLP task and remains killed.
- **F:** Decompose sensitivity into intervention, prompt-template, and repeat/stochastic components. Compare risk-coverage curves against `llm_top_probability`, entropy, abstention, activity, and history baselines on wallet-blocked OOS data. Kill F if it provides no residual selective benefit or is mainly prompt variance.

## 5. Stop condition

Stop the corresponding branch—and do not launch a large LLM study—if any of the following holds:

- the effect disappears after activity/autoregression, wallet-cluster, split, or prompt controls;
- ordinary calibrated uncertainty matches the proposed equifinality or identifiability signal;
- natural-language text adds nothing beyond structured consequences;
- “revision” is only sensitivity to prompt order or wording;
- the result requires inspecting August outcomes to select prompts, thresholds, or features;
- the claim requires owner intent, true belief, causal provenance, or verified social exposure;
- only selected discovery cases look favorable while the frozen aggregate result remains negative.

The August test remains immutable; no exploratory rescue should reopen OW-010C, justify a Temporal GNN, or convert the prior NO-GOs into positive evidence.

## 6. Literature/novelty verification still required

A dated title/abstract/code/data overlap audit is still required before any novelty claim. It should separately check:

- equifinality, observational equivalence, partial observability, causal non-identifiability, and aleatoric/epistemic uncertainty;
- selective prediction, abstention, conformal risk-coverage, and uncertainty calibration;
- prompt sensitivity, LLM reliability, explanation faithfulness, and counterfactual/contrastive explanation;
- belief revision, sequential hypothesis updating, evidence-based qualification, and retraction;
- financial transaction forecasting with activity, persistence, autoregressive, and repeated-entity controls.

For each nearest work, verify whether natural language is operationally central, whether the task requires explicit falsifiers or revision, and whether code/data run end to end. No exact citation or “no prior work exists” claim should be made before that audit.