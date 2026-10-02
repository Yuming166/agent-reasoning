## 1. GATE_DECISION

**MODIFY.** Retain the deterministic 100-case sample and 20-case double-coded subset as an exploratory human gate, but do not begin annotation under the current worksheet.

The selection principle is defensible: case-level hash sampling is outcome-blind and does not use \(F\), \(\Delta\), model loss, success/failure, or August membership. However, the protocol has material flaws:

- **Unit mismatch:** the manifest says 100 cases and 300 worksheet rows, but the source audit reports a mean of `2.999666...` hypotheses per case. The worksheet row count must be computed from the selected records, not assumed.
- **Case/hypothesis ambiguity:** specify whether all valid hypotheses in each selected case are coded. The 20 double-coded cases must include all their hypothesis rows and all four consequence dimensions.
- **Incomplete blinding:** horizon, evidence labels, intervention labels, and recorded consequence categories can anchor judgments even when they do not reveal future outcomes.
- **No explicit exclusion of probabilities/ranks:** structured hypothesis probabilities, confidence scores, ranks, and model metadata must be prohibited explicitly.
- **Rubric ambiguity:** `unsupported` conflates absence of support with contradiction; `specific/generic` overlaps with semantic commitment; `relevant` is not defined at the correct evidence-label level.
- **Missing reliability rule:** the statistic, treatment of `unclear`/missing values, and failure threshold are not locked.
- **Ordering risk:** source/hash order or case-grouped rows can create fatigue and context carryover.
- **Cluster risk:** hash sampling is case-level, but repeated addresses can be selected more than once. This is not selection leakage, but it limits wallet-level generalization and requires cluster-aware reporting.

No semantic validity or reliability result exists yet.

## 2. BLINDING_AUDIT

| Item | Risk | Required repair |
|---|---|---|
| **Evidence labels** | They may anchor annotators toward accepting the proposition, creating circular validation. | Hide them during the primary text-only pass. Reveal them only afterward for a separate, secondary relevance code, one label at a time. |
| **Hypothesis probabilities/ranks/confidence** | Strong confirmation and severity anchoring; may reveal model certainty or downstream selection. | Exclude all structured probabilities, ranks, scores, confidence, and model metadata from both passes. A probability phrase inside the narrative remains part of the text and is coded as hedging. |
| **Horizon** | A separate horizon field can anchor specificity and consequence judgments. | Do not show the separate field during Pass A. Reveal it only in Pass B if needed for horizon compatibility. If it was derived using future information, never show it. |
| **Recorded consequence categories** | Not future-ground-truth leakage, but direct target-label anchoring. | Use a two-pass design: text-only commitment first; reveal recorded categories only after Pass A is submitted and locked. |
| **Intervention label** | Can prime expected self/market/placebo behavior. | Hide it during Pass A; use only in a secondary relevance/compatibility field. |
| **Case ordering** | Source order, hash order, or grouping by case can induce fatigue and carryover. | Apply a second deterministic opaque permutation to worksheet rows. Do not group by case, wallet, horizon, evidence label, split, or outcome. |
| **Case identity** | Raw IDs may encode wallet, time, or other metadata. | Use opaque annotation IDs and retain the case-to-row map outside the worksheet. The double-coded roster should use hidden case handles. |
| **Repeated wallets** | Not leakage, but the sample may overweight address-level actors. | Preserve the fixed sample; report wallet repetition and use case- and wallet-cluster sensitivity analyses. Do not claim owner-level or wallet-independent generalization. |
| **August/F/Delta/outcomes** | Could cause outcome-conditioned judgments or sample replacement. | Keep hidden until raw annotations, reliability, adjudication, and annotation hashes are locked. |

The exact sampling operation must also be fixed as UTF-8 canonicalization plus a deterministic tie-break, for example:

`SHA256(UTF8(case_id || "|semantic-gate-v1|"))`, sorted by `(hash, case_id)`.

No selected case may be replaced after inspecting semantic or outcome fields.

## 3. LOCKED_CODEBOOK

Before annotation, freeze a glossary defining every one of the four structured consequence dimensions and every allowed category. Annotators must not interpret opaque category names.

### Annotation unit

- **Case:** hidden bundle selected by the fixed case-level sample.
- **Hypothesis row:** every valid hypothesis in the selected case.
- **Dimension cell:** one hypothesis × one consequence dimension.
- The primary analysis should report both dimension-level results and equal-weight case summaries.

### Pass A: text-only semantic commitment

Show only the exact narrative hypothesis and a neutral glossary of the four dimensions. Do not show structured horizon, evidence labels, intervention labels, consequence outputs, probabilities, or outcomes.

For each dimension:

- `explicit`: clear dimension-specific proposition with an operational object/direction/action.
- `hedged`: dimension-specific proposition is present but conditional, probabilistic, or weakly modalized.
- `generic_or_no_commitment`: broad narrative without a dimension-specific operational commitment.
- `unclear`: wording or referent cannot be resolved.
- `not_applicable`: only if a structural, predeclared schema rule makes the dimension inapplicable; annotators cannot choose this ad hoc.

Record an exact text span for `explicit` and `hedged`. `NO_SPAN` is valid for `generic_or_no_commitment`; do not fabricate a supporting span.

### Pass B: recorded-output comparison

Unlock only after Pass A is submitted and cryptographically locked. Reveal the recorded consequence category and, if required, the structured horizon and evidence labels.

For each dimension:

- `entailed`: the recorded category follows from the text under ordinary literal reading.
- `unsupported`: the text does not commit to the recorded category, but does not state its opposite.
- `contradicted`: the text explicitly or unambiguously states the opposite category.
- `unclear`: the text or category definition is ambiguous.
- `not_applicable`: only a predeclared structural case.

For evidence labels, code **each label separately**:

- `relevant`
- `irrelevant`
- `unclear`

This is secondary and must not alter the primary alignment code.

`unclear` is a valid substantive judgment. Technical absence is `missing`, not `unclear`; missing values must never be silently imputed.

Annotators must not infer:

- true owner identity or owner belief;
- psychology, emotion, motivation, or causal intent;
- verified social exposure;
- future truth or predictive correctness;
- causality from the narrative;
- probability beyond what the text explicitly states;
- that model-produced consequence categories are ground truth.

Do not use an LLM judge.

## 4. RELIABILITY_PLAN

- Select the 20 double-coded cases using a second locked salt from the already frozen 100-case sample.
- Two annotators independently code **all valid hypothesis rows and all four dimensions** for those 20 cases.
- No discussion or adjudication occurs before reliability is computed.
- Pass A must be locked before either coder sees Pass B fields.

Report:

1. Raw exact agreement, both pooled and per consequence dimension.
2. Cohen’s \(\kappa\) for the nominal commitment and alignment labels, treating `unclear` as a real category.
3. Gwet’s AC1 as a prevalence-sensitive diagnostic when \(\kappa\) is distorted by a dominant label.
4. For multi-label evidence fields, per-label three-class agreement and \(\kappa\); optionally report exact set match as a secondary statistic.
5. Missingness and completion separately. A one-sided missing value counts as a completion disagreement; missing pairs are excluded from \(\kappa\) only with the denominator reported.
6. Confidence intervals by resampling whole cases, not individual rows. Wallet-cluster resampling is a sensitivity analysis because address-level observations are only actor proxies.

### Predeclared failure threshold

The reliability gate fails if any of the following occurs:

- pooled primary exact agreement `< 0.80`;
- pooled primary \(\kappa < 0.60`;
- any consequence dimension has exact agreement `< 0.70` or \(\kappa < 0.40`;
- technical missingness exceeds `5%` of required cells;
- \(\kappa\) is undefined and the corresponding label distribution is non-degenerate enough that agreement cannot be interpreted from exact agreement alone.

For the semantic gate itself, use a strict rule locked before coding:

- `entailed` alignment must be at least `80%` of all applicable dimension cells, with `unsupported`, `contradicted`, and `unclear` counting against alignment;
- the case-clustered 95% lower bound should be at least `70%`;
- `contradicted` should not exceed `5%`.

Failure stops the language-centered branch. Adjudication cannot convert a failed pre-adjudication reliability result into a pass.

## 5. ANALYSIS_PLAN

Before unblinding, compute only:

- label counts and proportions by dimension;
- commitment coverage (`explicit + hedged`);
- strict alignment, unsupported, contradicted, and unclear rates;
- case-level and dimension-level summaries;
- pre-adjudication reliability and missingness;
- case- and wallet-cluster uncertainty intervals.

After reliability is recorded, adjudicate disagreements using the locked codebook and preserve the raw annotations unchanged. Adjudicated labels may be used for the descriptive semantic gate, but not for the reliability estimate.

Only after annotations, reliability, adjudication, and hashes are locked may the hidden join to \(F\), \(\Delta\), split, or August membership be opened. Any resulting association is exploratory and descriptive only. It must not:

- select or replace cases;
- tune the semantic threshold;
- reopen or retune the August frozen test;
- be interpreted as causal effectiveness;
- be interpreted as true belief, intent, psychology, or social exposure;
- be promoted to the official claim or experiment ledger.

The existing pooled Pearson \(F,\Delta=-0.0334\), Spearman \(=-0.0194\), residualized Pearson \(=-0.0366\), and wallet-cluster CI `[-0.0807, 0.0140]` remain artifact-audit context, not annotation labels or human semantic ground truth.

## 6. IMPLEMENTATION_CHECKLIST

Prepare deterministic, non-generative files/scripts:

1. `semantic_gate_protocol_v2.md`  
   Exact estimand, hash canonicalization, two-pass blinding, codebook, thresholds, and claim boundaries.

2. `scripts/validate_semantic_gate_source.py`  
   Validate unique case IDs, schema, source fingerprint, actual hypothesis counts, and technical completeness.

3. `scripts/select_semantic_gate_sample.py`  
   Generate the fixed 100-case sample and independently selected 20-case double-code roster; record source and sample hashes.

4. `scripts/build_blind_worksheets.py`  
   Produce Pass A and locked Pass B worksheets with opaque IDs and deterministic row permutation.

5. `scripts/audit_semantic_gate_blinding.py`  
   Assert absence of IDs, wallets, dates, split, outcomes, F, Delta, losses, August flags, probabilities, ranks, and model metadata.

6. `scripts/validate_annotation_schema.py`  
   Enforce closed labels, exact-span rules, `unclear` versus `missing`, and structural `not_applicable`.

7. `scripts/score_semantic_gate_reliability.py`  
   Compute exact agreement, Cohen’s \(\kappa\), AC1 sensitivity, missingness, and case/wallet-cluster intervals.

8. `scripts/lock_and_hash_annotations.py`  
   Canonicalize and fingerprint raw Pass A, Pass B, reliability, and adjudication files.

9. `scripts/adjudicate_semantic_gate.py`  
   Run only after pre-adjudication reliability is frozen.

10. `scripts/unblind_secondary_audit.py`  
    Optional post-lock exploratory join to \(F\), \(\Delta\), and August membership; must not write to the official ledger.

No new model outputs should be generated.

```text
large_llm_experiment_allowed=false
promotion_to_official_ledger=false
official_astra_cycle_untouched=true
```

No files were modified.