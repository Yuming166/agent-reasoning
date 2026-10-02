## 1. Verdict by branch (A-F; SUPPORT / HOLD / MODIFY / KILL / UNTESTED)

*Exploratory fallback only; not an Astra6 result, preregistered result, or final scientific conclusion. No branch currently earns SUPPORT.*

- **A — MODIFY:** Retain only as an NLP problem if it evaluates semantic evidence alignment, not merely intervention sensitivity versus downstream loss.
- **B — HOLD:** Requires distinct natural-language hypotheses that remain compatible with the same observed events; current audits do not establish equifinality.
- **C — MODIFY:** Best core candidate: induce atomic, evidence-linked, future-facing hypotheses with explicit falsifiers. This does not reopen the frozen effectiveness NO-GO.
- **D — UNTESTED:** Requires sequential retain/weaken/retract/split decisions after genuinely new evidence; current intervention responses are insufficient.
- **E — KILL:** “Predictability × interpretability” is not an NLP contribution without a language-specific task or metric.
- **F — MODIFY:** Potentially viable as selective assertion/abstention over semantically valid claims, but must beat calibrated confidence at matched coverage.

## 2. Strongest evidence

- Deterministic frozen evidence remains negative: B4 macro log loss was **0.840193** versus **0.810633** for B0; the paired B0–B4 interval was entirely unfavorable to B4.
- Evidence responsiveness passed on development data, but this did not transfer to future predictive effectiveness.
- In the discovery audit, intervention sensitivity was almost unrelated to incremental validity: Pearson **−0.0334**, Spearman **−0.0194**, with positive mean degradation despite **53.65%** case-level gains.
- Therefore, response magnitude is not a semantic-validity certificate. The current evidence supports only the need for a better language-level measurement.
- Proposed tuple, not observed evidence:  
  `claim predicate + scope/time + evidence pointers + observable consequence/horizon + falsifier + optional revision action`.
  Missing fields must remain missing; analysts must not reconstruct them from prose.

## 3. Strongest counterargument

The proposed tuple may simply repackage established information extraction, entailment, fact verification, belief revision, argument mining, and selective prediction. “Falsifiable hypothesis” is not novel by naming alone.

Moreover, address behavior is only an actor proxy. Human annotators could silently inject owner intent or causal meaning that the data do not contain. Even perfect semantic alignment would not prove true psychology, causal intent, social exposure, persistent latent state, or predictive usefulness.

## 4. Cheapest decisive experiment

Run a **development-only, no-new-LLM-call falsification gate** on 100 randomly sampled existing July cases; leave the August test untouched.

1. Convert each existing output into the fixed tuple above. Do not rewrite prose to make it fit.
2. Apply deterministic checks:
   - evidence IDs/spans must fall inside the stated input window;
   - the consequence must map to a predeclared observable event and horizon;
   - the falsifier must be directionally incompatible with the claim;
   - duplicate or paraphrased claims must not be counted as distinct hypotheses.
3. Blindly annotate semantic non-redundancy, evidence alignment, consequence observability, and—after one blinded new-event vignette—retain/weaken/retract/split revision.
4. Use controls: paraphrase preservation, contradiction substitution, evidence shuffling, placebo evidence, and a confidence-only baseline.
5. Pass only if the representation is mostly complete, blind judgments are reliable, and semantic perturbations behave as predicted. If it passes, open a separately preregistered V2 on an untouched temporal holdout; do not reinterpret August.

Generated text is model advice/hypothesis. Event records, predeclared outcome mappings, and frozen losses are the deterministic evidence.

## 5. Stop condition

Stop the NLP branch—and do not run a large LLM experiment—if any of the following occurs:

- claims require analyst rewriting to obtain evidence, consequence, or falsifier fields;
- evidence shuffling or contradiction controls are indistinguishable from the original;
- annotators cannot reliably distinguish semantic duplicates from genuinely different hypotheses;
- the apparent signal is reproduced by confidence or formatting without the language fields;
- revision decisions are unsupported by new evidence;
- advancing would require inspecting or retuning the August test.

A passing semantic gate still cannot be reported as effectiveness, causal intent, owner psychology, or Level-2 relational expectation.

## 6. Literature/novelty verification still required

Complete a dated title/abstract/code/data overlap audit covering:

- evidence-grounded hypothesis generation and claim verification;
- semantic parsing, entailment, contradiction, and argument mining;
- falsifiable/scientific hypothesis generation and observable consequence specification;
- defeasible reasoning and sequential belief/hypothesis revision;
- calibrated selective prediction, abstention, uncertainty, and identifiability;
- temporal event forecasting using behavioral or transaction records.

The audit must determine whether the proposed tuple, falsifier/revision protocol, controls, and matched-coverage evaluation are genuinely distinct from existing work. Verify runnable implementations, datasets, annotation protocols, and licenses for the closest candidates. Do not claim novelty until this overlap and reproducibility check is complete.