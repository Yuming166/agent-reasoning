# CONDITIONAL_PHASE2_PROTOCOL

**Status: `CONDITIONAL_DRAFT_DO_NOT_EXECUTE`**

The runtime did not expose the contents of `CONDITIONAL_INPUTS.md`. Therefore, the semantics of M0–M5 are intentionally **not reconstructed or guessed** below. Before execution, copy the exact M0–M5 definitions, split boundaries, candidate-set rules, wallet-cluster definition, and any predeclared thresholds from `CONDITIONAL_INPUTS.md` into the frozen protocol.

No Phase 2 or Phase 3 execution is authorized by this draft. No Phase 1 annotations, submissions, future outcomes, prediction scores, or other project files are used.

## Objective

Evaluate whether each representation rung \(M_i,\ i\in\{0,\ldots,5\}\) improves next-counterparty prediction over:

1. its immediately preceding rung \(M_{i-1}\);
2. an architecture- and budget-matched semantic-null control; and
3. the designated input-defined baseline.

All comparisons must use the same eligible events, candidate support, temporal split, scoring implementation, random-seed set, and evaluation budget.

## Frozen protocol

For every rung:

- Use only the representation and auxiliary inputs explicitly allowed by `CONDITIONAL_INPUTS.md`.
- Freeze train/validation/test time boundaries before fitting.
- Fit scalers, vocabularies, embeddings, graph summaries, cluster assignments, and other learned transforms only on permitted historical data.
- Select hyperparameters and operating thresholds on validation data only.
- Evaluate the test period once under the frozen configuration.
- Use identical event and candidate support for every model and control.
- Record model identity, parameter count, training updates, inference budget, failed parses, missing probabilities, unsupported targets, and excluded events.
- Do not select the best rung after observing test outcomes. All pairwise comparisons must be declared in advance.

# BASELINE_MATRIX

The exact representation descriptions must be copied verbatim from `CONDITIONAL_INPUTS.md` before execution.

| Rung | Representation | Required comparison | Matched-complexity control | Primary interpretation |
|---|---|---|---|---|
| M0 | Input-defined M0 representation | M0 versus designated base, if distinct | `MC0`: same predictor template and budget with M0 information semantically neutralized | Establishes the minimum representation reference |
| M1 | Input-defined M1 representation | M1 versus M0 | `MC1`: M1-shaped semantic-null representation with matched capacity | Tests the incremental contribution of M1 |
| M2 | Input-defined M2 representation | M2 versus M1 | `MC2` | Tests the incremental contribution of M2 |
| M3 | Input-defined M3 representation | M3 versus M2 | `MC3` | Tests the incremental contribution of M3 |
| M4 | Input-defined M4 representation | M4 versus M3 | `MC4` | Tests the incremental contribution of M4 |
| M5 | Input-defined M5 representation | M5 versus M4 | `MC5` | Tests the incremental contribution of M5 |

## Matched-complexity controls

Each `MCi` should preserve, as closely as feasible:

- predictor backbone;
- trainable parameter count;
- representation dimensionality and number of input slots;
- optimizer, learning-rate schedule, batch size, and update count;
- early-stopping procedure;
- regularization and dropout;
- context, edge, token, or history budget;
- candidate-generation and negative-sampling budget;
- random-seed set;
- inference-time computation budget.

The semantic content should be neutralized without changing shape or capacity. The exact null operation must be declared before execution. Possible input-compatible controls include:

- within-training-period permutation preserving marginal feature distributions;
- time-bin-preserving permutation for temporal fields;
- degree- and time-preserving graph rewiring;
- frequency-matched replacement for text or categorical fields;
- masking or replacement with training-only draws;
- a lower-rung representation padded to the higher rung’s input shape.

A capacity-matched control is not a substitute for an adjacent-rung comparison. Claims about a rung require both:

\[
M_i \; \text{versus} \; M_{i-1}
\]

and

\[
M_i \; \text{versus} \; MC_i.
\]

# METRIC_DEFINITIONS

## Primary metric

For eligible event \(e\), let \(y_e\) be the observed next counterparty and \(p_M(y_e\mid x_e)\) the probability assigned by model \(M\). Use the predeclared log base; if the input file does not specify one, freeze natural logarithms before execution:

\[
\ell_e(M)=-\log p_M(y_e\mid x_e).
\]

For a model \(M_i\) and matched control \(C_i\), define the paired improvement:

\[
\widehat{\Delta}_{i,e}
=
\ell_e(C_i)-\ell_e(M_i).
\]

Positive values indicate lower log loss for \(M_i\). The event-weighted primary estimate is:

\[
\widehat{\Delta}_{i,\mathrm{event}}
=
\frac{1}{N}
\sum_{e=1}^{N}
\widehat{\Delta}_{i,e}.
\]

Primary comparisons:

- \(M_i\) versus \(M_{i-1}\);
- \(M_i\) versus \(MC_i\).

Report the estimate, 95% confidence interval, number of eligible events, number of wallet clusters, and support coverage.

## Wallet-cluster inference

Events from the same wallet cluster are not independent observations. Inference must therefore resample or model wallet clusters rather than treating all events as independent.

For cluster \(c\), define:

\[
\bar{\Delta}_{i,c}
=
\frac{1}{n_c}
\sum_{e\in c}
\widehat{\Delta}_{i,e}.
\]

Report both:

1. **Event-weighted delta**, which reflects deployment on the observed event mix.
2. **Cluster-balanced delta**:

\[
\widehat{\Delta}_{i,\mathrm{cluster}}
=
\frac{1}{G}
\sum_{c=1}^{G}
\bar{\Delta}_{i,c},
\]

where \(G\) is the number of eligible wallet clusters.

The primary confidence interval should use one of the following predeclared methods:

- cluster bootstrap, resampling complete wallet clusters;
- cluster-robust standard errors;
- a paired cluster-level randomization test;
- a small-cluster method if the number of clusters is limited.

Event-level bootstrap alone is not valid for the primary inferential claim.

Report:

- \(G\), total events, and events per cluster;
- minimum, median, and maximum cluster size;
- largest-cluster share of events;
- cluster-balanced and event-weighted estimates;
- the fraction of clusters with positive paired improvement;
- heterogeneity across clusters.

If wallet-cluster assignments are unavailable, outcome-derived, or constructed using future information, the corresponding comparison must not be asserted.

## Secondary metrics

Secondary metrics must be fixed before test evaluation and cannot replace the primary metric:

- top-\(k\) hit rate for the input-defined values of \(k\);
- mean reciprocal rank or another predeclared rank metric;
- Brier score;
- calibration error or reliability summaries;
- per-wallet and per-cluster log-loss distributions;
- support coverage: fraction of target events whose true counterparty is in the evaluated candidate set;
- abstention or invalid-prediction rate, if applicable;
- parameter count, runtime, memory, and inference budget as complexity diagnostics.

Metrics requiring a candidate ranking must exclude or separately report events where the target is outside candidate support. Such events must not be silently treated as incorrect predictions for one model and omitted for another.

## Multiple comparisons

The ladder contains multiple planned contrasts. Use a predeclared multiplicity procedure, such as Holm correction, over the stated adjacent-rung and matched-control comparisons. Do not report only the best-performing rung or the best uncorrected comparison.

## Leakage boundaries

The following are hard boundaries:

- No feature may use an event, edge, wallet state, cluster assignment, or text created after the prediction timestamp.
- The target event and any direct derivative of it must be excluded from the feature state.
- Future counterparties, future degrees, future communities, future embeddings, and future normalization statistics are prohibited.
- Candidate generation must be as-of the prediction time and identical across models.
- A target absent from candidate support is an out-of-support case, not a model-specific missing value.
- Hyperparameters, thresholds, and feature-selection choices must not use test outcomes.
- If a graph or cluster representation is transductive, that regime must be explicitly declared. If inductive generalization is intended, test wallets or test clusters must not be used during fitting.
- Wallet identifiers may not serve as an unannounced memorization channel.
- No annotation, submission, future outcome, or prediction score may be used to define clusters, choose representations, tune thresholds, or alter inclusion criteria.
- Any post-hoc matched-coverage or restricted-support analysis must be labeled secondary and cannot replace the frozen primary analysis.

# PHASE3_SHELL

The only permitted Phase 3 outputs are:

- `ASSERT`
- `QUALIFY`
- `ABSTAIN`

The shell is:

```text
verdict ∈ {ASSERT, QUALIFY, ABSTAIN}

if any integrity, leakage, support, parsing, split, or cluster-validity
condition is violated:
    verdict = ABSTAIN

else if all predeclared assertion conditions are satisfied:
    verdict = ASSERT

else:
    verdict = QUALIFY
```

## `ASSERT`

Use only when all of the following are true:

- the exact input-defined M0–M5 specification was frozen before evaluation;
- temporal and candidate-set leakage checks pass;
- the primary log-loss comparison is valid;
- the predeclared confidence interval supports a positive improvement;
- the effect meets the predeclared minimum meaningful delta, if one exists;
- the conclusion survives the predeclared multiplicity correction;
- the matched-complexity control does not show an equivalent gain attributable only to capacity or budget;
- wallet-cluster inference is available and consistent with the stated estimand;
- support coverage and missingness satisfy the predeclared rules;
- no result-driven subgroup, threshold, or representation choice was made.

`ASSERT` must identify the exact contrast: for example, “M4 versus M3” or “M5 versus MC5.” It must not assert that the entire ladder is superior unless that global claim was separately predeclared.

## `QUALIFY`

Use when the evaluation is valid but the evidence is limited, such as:

- positive point estimate but an interval that includes zero;
- insufficient power for the smallest planned effect;
- improvement present only for a predeclared support-restricted estimand;
- event-weighted improvement without consistent cluster-balanced improvement;
- heterogeneous cluster effects;
- secondary metrics improve while the primary metric is inconclusive;
- the matched-control comparison is inconclusive but no validity violation is present.

`QUALIFY` must state the restricted population, estimand, uncertainty, and unsupported stronger claim.

## `ABSTAIN`

Use when any of the following occurs:

- input definitions or split boundaries are missing or changed;
- future information may have entered features, clusters, candidates, or preprocessing;
- the target is not consistently in candidate support;
- prediction parsing or probability normalization is invalid;
- test outcomes influenced thresholds, hyperparameters, inclusion, or representation choice;
- wallet clusters cannot support valid inference;
- required logs or provenance are missing;
- a comparison was not predeclared;
- multiple-comparison handling is absent;
- the observed analysis cannot distinguish representation benefit from capacity, budget, or candidate-set differences.

# POWER_SIMULATION_PLAN

## Planning effects

Simulate paired synthetic log-loss improvements:

\[
\delta \in \{0,\ 0.005,\ 0.010,\ 0.020,\ 0.030\}.
\]

The four nonzero values are planning effects only. They are not claims about the data and must not be used to select a result after evaluation.

The null case \(\delta=0\) is required for type-I-error and false-positive calibration.

## Generative structure

Simulate paired event-level loss differences within wallet clusters:

\[
D_{ce}
=
\ell_{ce}(C)-\ell_{ce}(M)
=
\delta + u_c+\epsilon_{ce},
\]

where:

- \(c\) indexes wallet clusters;
- \(e\) indexes events within cluster \(c\);
- \(u_c\) is a cluster-level random effect;
- \(\epsilon_{ce}\) is event-level noise;
- the mean of \(D_{ce}\) is calibrated to the target \(\delta\).

Use the cluster-size distribution specified in `CONDITIONAL_INPUTS.md`. If it does not specify one, evaluate a prespecified grid of balanced and highly imbalanced cluster sizes rather than inventing a single empirical distribution.

At minimum, vary:

- number of independent wallet clusters;
- total eligible events;
- events per cluster;
- intra-cluster correlation;
- paired correlation between model and control losses;
- cluster-size imbalance;
- candidate-support coverage;
- missing or invalid prediction rate;
- number of simultaneous ladder comparisons.

If a physically valid probability-level simulation is required, generate paired probability vectors over the fixed candidate set and calibrate them to the target mean log-loss difference. Otherwise, direct paired-loss simulation is sufficient for planning the paired estimator.

## Sample-size grid

Evaluate sample size in both dimensions:

1. number of independent wallet clusters \(G\);
2. number of eligible events per cluster or total eligible events \(N\).

Do not treat a large number of events from a small number of wallets as equivalent to a large number of independent wallets. For approximately equal cluster size \(m\), use the design-effect diagnostic:

\[
N_{\mathrm{eff}}
\approx
\frac{Gm}{1+(m-1)\rho},
\]

where \(\rho\) is the intracluster correlation. This is a planning diagnostic, not a replacement for the cluster-based estimator.

## Simulation procedure

For each combination of effect size, cluster count, cluster-size pattern, correlation, support rate, and comparison:

1. Generate paired control/model losses.
2. Apply the exact planned eligibility and support rules.
3. Calculate the primary paired log-loss delta.
4. Apply the exact cluster-level inference procedure.
5. Apply the planned multiplicity correction.
6. Evaluate the frozen Phase 3 assertion conditions.
7. Record estimate, interval coverage, type-I error, power, cluster-balanced behavior, and false assertion rate.

Use at least 10,000 Monte Carlo repetitions per scenario cell; 20,000 is preferable for final planning tables. Use fixed, recorded random seeds. Do not execute this simulation as part of the current draft.

## Power targets

Before Phase 2, predeclare:

- the smallest scientifically meaningful effect;
- the target power, ordinarily 0.80, with 0.90 as a preferred sensitivity target;
- the confidence level;
- the multiplicity procedure;
- the minimum acceptable cluster count;
- the acceptable support and missingness limits.

The minimum planned sample size is the smallest cluster/event configuration reaching the target power for the smallest meaningful effect after cluster dependence and multiplicity correction. If the available design is underpowered, do not tune the analysis to compensate. The resulting Phase 3 state is limited to `QUALIFY` or `ABSTAIN` according to the frozen shell.

# STOP_RULES

Stop before execution if any of the following is unresolved:

1. Exact definitions of M0–M5 are unavailable.
2. The prediction timestamp and temporal split are not frozen.
3. The candidate-set construction is not identical across representations.
4. The wallet-cluster definition is missing, outcome-derived, or temporally contaminated.
5. The minimum meaningful delta or Phase 3 assertion rule is not predeclared.
6. The number of independent wallet clusters is unknown.
7. Power cannot be evaluated under cluster dependence.
8. The required matched-complexity control cannot be constructed.
9. The scoring unit, log base, or handling of unsupported targets is ambiguous.
10. Any Phase 1 annotation, submission, future outcome, or prediction score would need to be inspected to complete the design.

During execution, stop and produce `ABSTAIN` if:

- any leakage audit fails;
- model outputs are invalid or non-comparable;
- test-time support differs across models;
- event or cluster inclusion changes after seeing outcomes;
- a post-hoc threshold or representation is introduced;
- provenance, seeds, or evaluation logs are incomplete;
- the planned cluster inference cannot be reproduced.

This document remains a **conditional protocol shell only** until the exact contents of `CONDITIONAL_INPUTS.md` are available and reconciled.