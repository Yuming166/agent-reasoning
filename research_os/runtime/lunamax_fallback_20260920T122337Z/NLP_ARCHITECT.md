## 1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)

Exploratory fallback only; these statuses do not change the frozen NO-GO decisions.

| Branch | Verdict | Required NLP-central reformulation |
|---|---|---|
| **A: Evidence-Validity Gap** | **MODIFY** | Evaluate whether a textual claim is supported, contradicted, or unsupported by cited pre-cutoff events, then compare its explicit future implication with outcomes. Intervention magnitude alone is insufficient. |
| **B: Behavioral Equifinality** | **HOLD** | Require competing language hypotheses that are observationally equivalent under the same event history but differ in future predicates or falsifiers. No equifinality has yet been demonstrated. |
| **C: Falsifiable Behavioral Hypothesis Induction** | **MODIFY** | Primary candidate. Generate address-level behavioral propositions with scope, horizon, evidence, future consequence, and an executable falsifier. This must be more than forecasting rewritten as prose. |
| **D: Behavioral Hypothesis Revision** | **UNTESTED** | Potentially strongest NLP direction, but requires sequential retain/qualify/retract/replace decisions after genuinely new evidence. Existing intervention responsiveness is not revision. |
| **E: Predictability × Interpretability** | **KILL** | The current two-axis framing is generic and does not require language. Retain only as descriptive diagnostics. |
| **F: Identifiability-Aware Selective Inference** | **MODIFY** | Define identifiability over competing linguistic hypotheses and evidence support; generic confidence gating or abstention is not enough. |

No branch currently merits **SUPPORT** as an established result. C is the smallest primary candidate; D is the most distinctive extension if C survives.

## 2. Strongest evidence

The deterministic frozen artifact establishes a separation between operational responsiveness and prospective usefulness:

- B4 worsened August test macro log loss relative to B0/M1: `0.840193` versus `0.810633`.
- July evidence responsiveness passed, but this did not produce future predictive effectiveness.
- Intervention sensitivity had essentially no monotonic relationship with the incremental loss proxy: Pearson `-0.0334`, Spearman `-0.0194`; the audit is discovery-only.
- Existing results therefore do not validate textual explanations, latent owner beliefs, causal intent, or persistent decision states.

The smallest genuinely NLP-centered object should be:

```text
H = (
  address-level_behavior_predicate,
  scope,
  time_horizon,
  polarity,
  evidence_event_ids,
  evidence_relation,
  future_event_predicate,
  falsifier,
  revision_action
)
```

The behavior predicate must describe observable address activity, not owner psychology. Evidence IDs and timestamps are deterministic inputs. The claim wording, evidence relation, and revision advice are model-generated proposals and must not be treated as gold labels.

## 3. Strongest counterargument

This representation could still be ordinary event forecasting, argument extraction, or structured classification with a textual wrapper. If removing the surface language leaves the same task, metrics, and conclusions, the contribution is cosmetic.

A second risk is that “support” and “falsification” may be judged only by another model. That would turn model-generated advice into pseudo-evidence. Human or rule-based labels are needed for the semantic relation, while event existence, temporal validity, future predicate firing, and falsifier firing should be deterministic.

The address-level boundary also remains binding: semantic claims cannot be interpreted as verified owner beliefs, transaction intent, causal provenance, or social exposure.

## 4. Cheapest decisive experiment

Run a small, no-new-LLM falsification pilot on a predeclared sample of development cases; do not inspect or retune the frozen August test.

For each case:

1. Construct one paraphrase-equivalent claim, one non-redundant alternative with the same observed evidence, and one contradiction.
2. Attach explicit pre-cutoff evidence IDs and manually label each relation as `supports`, `weakens`, or `insufficient`.
3. Compile each claim into a future event predicate and falsifier.
4. If testing revision, provide one subsequent evidence packet and require `retain`, `qualify`, `retract`, or `replace`.
5. Compare against a text-free template and lexical-similarity baseline.

The branch passes this gate only if:

- evidence references and temporal boundaries are deterministically valid;
- independent annotators agree on equivalence, evidence relation, and falsifier;
- non-redundant claims produce different executable implications rather than merely different wording;
- accepted claims can be evaluated on future events without outcome-conditioned selection;
- revision decisions have an auditable trigger.

Only after this gate should a small model pilot be considered on a new untouched temporal holdout. It must not be used to reopen or optimize the frozen B4 result.

## 5. Stop condition

Stop and kill the branch if any of the following occurs:

- paraphrases and genuinely different hypotheses cannot be separated beyond lexical or template baselines;
- claims cannot be compiled into deterministic future predicates and falsifiers;
- evidence alignment depends solely on model-generated judgments;
- revision reduces to confidence changes without proposition-level retain/qualify/retract behavior;
- the representation adds no value over a text-free event ontology;
- any result requires August-test retuning, future-outcome selection, leakage, or owner-psychology interpretation.

A failure of the pilot is a failure of the proposed NLP formulation, not evidence that all language-based behavioral research is ineffective.

## 6. Literature/novelty verification still required

Before claiming novelty, perform a dated title/abstract/code/data overlap audit covering:

- evidence-grounded claim verification and rationale faithfulness;
- natural-language hypothesis generation, falsification, and scientific reasoning;
- temporal event forecasting and future-oriented textual inference;
- belief revision, argumentation, and evidence-based update operators;
- selective prediction, abstention, uncertainty, and identifiability;
- behavioral or financial event forecasting using textual explanations.

For each close candidate, separately verify task definition, representation, evaluation target, code/data availability, minimal execution, and full end-to-end reproducibility. The novelty claim must be specific—such as executable address-level hypotheses with evidence links and falsifiers—and must not rely on the absence of an exact title match.