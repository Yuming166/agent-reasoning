## 1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)

Exploratory fallback only; this is not an Astra6 result or a final scientific conclusion.

| Branch | Verdict | Reason |
|---|---|---|
| **A: Evidence-Validity Gap** | **MODIFY** | The discovery audit motivates a gap, but intervention sensitivity is not semantic evidence validity. |
| **B: Behavioral Equifinality** | **HOLD** | No result yet demonstrates distinct hypotheses remaining observationally equivalent. |
| **C: Falsifiable Behavioral Hypothesis Induction** | **MODIFY** | Promising only if claims have explicit scope, horizon, consequence, and falsifier; V1 effectiveness remains NO-GO. |
| **D: Behavioral Hypothesis Revision** | **UNTESTED** | Intervention responsiveness is not sequential hypothesis retention or retraction. |
| **E: Predictability × Interpretability** | **KILL** | The current two-axis framing is generic and not independently operationalized as an NLP task. |
| **F: Identifiability-Aware Selective Inference** | **MODIFY** | Testable, but identifiability must be defined against observations and a hypothesis class; \(F\) alone is not a validated selector. |

The strongest next-test set is **A, F, and C**, in that order.

## 2. Strongest evidence

- Frozen Decision-State V1 failed the effectiveness gate: B4 macro log loss was **0.840193** versus **0.810633** for B0/M1, with the paired interval indicating deterioration.
- Evidence responsiveness passed on development, but did not transfer to predictive effectiveness. This is the clearest evidence that “responsive explanation” and “useful forecast” are separable.
- The discovery audit found essentially no simple ranking relationship between intervention sensitivity and incremental validity: Pearson **−0.0334**, Spearman **−0.0194**, and adjusted Pearson **−0.0383**.
- The audit is still discovery-only: it pools development/test rows, includes repeated wallets, and has no direct human label of claim validity, falsifiability, or identifiability.
- OW-010B independently failed the frozen structural-support gate; therefore a Temporal GNN, large latent-strategy experiment, or external-label expansion is not justified.

## 3. Strongest counterargument

The observed failure may be caused by feature miscalibration, autoregressive/activity proxies, target mismatch, or the B4 meta-head—not by invalid natural-language hypotheses.

Likewise, \(F\) measures response magnitude to interventions, while \(\Delta\) measures the loss difference between two prediction systems. Their near-zero correlation does not prove an “evidence-validity gap.” Without blinded semantic annotations and a new temporal holdout, A and F remain proxy hypotheses rather than established phenomena.

## 4. Cheapest decisive experiment

Run a small **V2-0 Claim/Identifiability Falsification Gate**, not a large LLM study.

- **Sample:** 240 newly reserved cases from the next chronological block after the frozen August cutoff: 120 development cases and 120 later holdout cases. Use at most one case per wallet per split; avoid wallet overlap across splits if feasible. If no later temporal data exists, do not substitute the August test.
- **Sampling:** Select before future outcomes are available, using activity bin, dominant event family, history length, event count, and other pre-outcome controls. Do not sample on \(\Delta\), success/failure, or future labels.
- **Target:** Keep the frozen 7-day address-behavior target and existing consequence schema unchanged.
- **Model call:** At most one frozen Qwen3.5-4B pass per case, producing an explicit claim, horizon, consequence/direction, confidence or abstention, and evidence pointer. No intervention battery, self-critique, prompt search, model-generated judging, or answer selection.
- **Controls:**  
  1. deterministic M1 recent-dynamics baseline;  
  2. candidate claim arm;  
  3. consequence-only structured arm versus full claim text;  
  4. random abstention gate at matched coverage;  
  5. `llm_top_probability`/`llm_abstain` gate;  
  6. historical B4 reported only as a frozen negative reference, not retuned.
- **Blinded annotation:** Two annotators independently label whether the claim is evidence-supported, text-to-schema entailed, scoped/falsifiable, and whether multiple behavioral hypotheses remain compatible with the observation. These labels are evaluation references, not model-generated evidence.
- **Primary metric:** At a coverage fixed on development, compute held-out paired macro-log-loss improvement of the gated candidate over M1, with a paired bootstrap interval. Compare against both random gating and the probability-only gate.
- **Branch readouts:**  
  - **A:** validity/entailment precision among accepted claims and whether valid claims have lower held-out loss than invalid claims.  
  - **C:** strict falsifiability and text-to-schema entailment; full text must add value over consequence-only output.  
  - **F:** selective risk at matched coverage; entropy/abstention must outperform random and probability-only selection.

## 5. Stop condition

Stop before scaling if any of the following occurs:

- The semantic annotation protocol fails its predeclared agreement threshold, or accepted claims have unusably low coverage.
- The candidate gate does not outperform random gating and the probability-only gate on development.
- Full-language output does not improve semantic precision over consequence-only output.
- On the untouched holdout, the candidate’s paired improvement interval includes zero, or it is not better than matched random/probability gating.
- Any holdout result requires changing the prompt, threshold, consequence schema, feature family, or meta-head.

A failure is a **NO-GO for expanding A/F/C**, not a claim that all language-based behavioral reasoning is impossible. A positive small-pilot result remains exploratory and requires a separately preregistered replication.

Deterministic boundaries: sampling, temporal split, target extraction, M1, schema checks, controls, gates, and metrics. Model boundaries: only the frozen one-pass hypothesis generation. The output remains an address-level actor proxy, not owner psychology, causal intent, or verified social exposure.

## 6. Literature/novelty verification still required

- Perform a dated title/abstract/code/data overlap audit for evidence-grounded explanation faithfulness, falsifiable hypothesis generation, non-identifiability/equifinality, belief or hypothesis revision, calibrated abstention, selective prediction, and financial/transaction forecasting.
- Verify whether A, C, or F reduces to an established task with new terminology rather than a new NLP problem.
- Check whether the proposed semantic labels, consequence schema, and identifiability criterion have prior operational definitions and benchmark precedents.
- Separately verify runnable baselines, data/schema availability, temporal joins, and leakage controls before making reproducibility or novelty claims.
- Do not report discovery evidence, intervention responsiveness, or a small pilot as confirmatory effectiveness or generalization.