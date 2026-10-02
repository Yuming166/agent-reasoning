# Autoresearch Phase II-A — Reasoning-Worthiness Discovery

**Targets:** NAACL 2027 / WWW 2027  
**Repository:** `Yuming166/agent-reasoning`  
**Phase-I baseline:** `1d2dfdd`

## 0. Mission

Convert the Phase-I results into one falsifiable research program:

> **Can we predict, before spending expensive reasoning compute, which Ethereum wallet-events will benefit most from trustworthy counterfactual reasoning?**

The core object is **reasoning-worthiness**, not generic wallet importance.

For event `e` at cutoff `t`:

`RV(e,t) = U_FullCF(e,t) - U_Cheap(e,t)`

where both systems see exactly the same information available at `t`, and utility is measured against the same future outcome. Treat this as **reasoning gain / incremental predictive utility**, not a causal effect.

NAACL 2027 explicitly covers AI/LLM Agents, Inference-Time Methods, LLM Efficiency, Reasoning in NLP/Language Models, Resources/Benchmarks/Evaluation, and Safety/Alignment. The official ARR deadline is October 12, 2026. Keep the project suitable for both NAACL and WWW: NAACL emphasizes trustworthy/inference-time reasoning; WWW emphasizes dynamic transaction networks, temporal prediction, and influence.

---

## 1. Phase-I starting point

Freeze unless an audit finds an error:

- leakage-audited temporal data preparation;
- EX-Graph mapped wallets;
- static graph features as priors only;
- repaired candidate pools;
- frozen cheap ranker;
- Full-CF FSM;
- NoCF ablation;
- strict parsing/fallback;
- token and latency logging;
- June–September corrected v2 evaluation;
- TGB validation, explicitly labelled as local protocol evaluation rather than official leaderboard submission.

Phase-I gives evidence that Full-CF can outperform Cheap, while the first learned budget gate was weak. Do **not** respond by merely trying more classifiers. First repair the supervision: the next object is reasoning gain.

---

# 2. Primary hypotheses

### H1 — Reasoning-worthiness is predictable

`P(RV > 0 | X_e,t)` should be predictable from information available before reasoning.

### H2 — Dynamic influence beats static importance

Future predictive spillover should be more useful than volume, activity, degree, weighted degree, PageRank, or k-core.

### H3 — Reasoning gain is heterogeneous

Full-CF should help disproportionately around difficult events such as new counterparties, behavioral regime changes, unusual interactions, graph disruption, and ambiguous evidence. These are hypotheses, not assumptions.

### H4 — Selective reasoning wins at matched budget

For fixed expensive-reasoning budget `B`:

`U(learned selector, B) > U(random selector, B)`

and ideally also beats static activity/centrality policies.

### H5 — Temporal generalization

A selector trained/tuned on earlier periods must improve August and the independent September temporal holdout.

---

# 3. Non-negotiable temporal protocol

Every pipeline must follow:

`features at t -> selection -> reasoning -> future outcome`

No future information may enter feature construction, router training, selection, or threshold tuning.

Primary chronological protocol:

- June: train/development;
- July: tuning;
- August: frozen primary test;
- September: independent temporal holdout.

Where feasible use rolling-origin evaluation. Never tune on August or September.

---

# 4. First task: Phase-I result audit

Create:

`research/phase2/PHASE1_RESULT_AUDIT.md`  
`research/phase2/phase1_result_registry.csv`

For all 11 Phase-I groups record:

- hypothesis;
- method;
- data/split;
- metric;
- baseline;
- gain;
- cost;
- leakage status;
- reproducibility;
- statistical support;
- paper relevance;
- decision.

Allowed decisions:

`KEEP_CORE`, `KEEP_ABLATION`, `KEEP_CONTEXT`, `REPRODUCE`, `DROP`, `BLOCKED`.

Also diagnose and, if necessary, rerun the June parsing anomaly before using June as router-training evidence.

---

# 5. Central Phase-II artifact: reasoning-gain dataset

Create:

`research/phase2/reasoning_gain_dataset.parquet`

One row per `(wallet, event, cutoff)`.

Minimum fields:

```text
event_id, wallet_id, cutoff_time
cheap_prediction, cheap_score, cheap_rank, cheap_correct
fullcf_prediction, fullcf_score, fullcf_rank, fullcf_correct
reasoning_gain, reasoning_gain_type
future_target, event_family, interaction_type
wallet_activity, wallet_volume, counterparty_recency, counterparty_novelty
degree_asof, weighted_degree_asof, pagerank_asof, community_features_asof
behavioral_state, behavioral_surprise, regime_change_score
future_spillover, future_spillover_horizon
reasoning_tokens, reasoning_latency, parse_success, fallback_used
```

All `*_asof` features must be computed using history available at the cutoff.

---

# 6. Reasoning-gain definitions

Do not rely on one target.

### Rank gain

`RV_MRR = MRR_FullCF - MRR_Cheap`

### Log-probability gain

When calibrated probabilities are available:

`RV_LL = log p_FullCF(y*) - log p_Cheap(y*)`

### Binary usefulness

`Z = 1[RV > delta]`

Pre-register `delta`, including zero and at least one positive threshold.

### Cost-normalized gain

`RV_cost = RV / (tokens + lambda * latency)`

Use this for efficiency, not as the sole primary metric.

**Do not call RV a causal treatment effect.** Use “reasoning gain”, “expected reasoning utility”, or “incremental predictive utility”.

---

# 7. Avoid circular supervision

The selector must not simply learn the final test metric.

Selector supervision may use:

- reasoning gain;
- downstream spillover;
- future influence;
- event difficulty.

Final evaluation should use:

- next-event ranking;
- future trajectory;
- downstream predictive utility;
- utility per reasoning budget.

At least one main selector target should not be identical to the final evaluation metric.

---

# 8. Dynamic predictive influence

For wallet `i` at cutoff `t`, estimate:

`I_i^(h)(t) = U(Y[t:t+h] | C_t, X_i) - U(Y[t:t+h] | C_t)`

Candidate horizons:

- 1h;
- 6h;
- 24h;
- 3d;

or event-count horizons when time windows are too sparse.

Call this **dynamic predictive influence** or **future predictive spillover**, not causal influence.

Candidate outcomes:

1. downstream new counterparties;
2. future flow;
3. future activity in reachable neighborhoods;
4. future event-family distribution;
5. future prediction utility;
6. future graph-state change.

Select the primary definition on development data only.

---

# 9. Volume-adjusted influence

Test:

`ResidualInfluence_i = I_i - E[I_i | Volume_i]`

Explicitly analyze:

- high-volume / low-influence;
- low-volume / high-influence;
- high-volume / high-influence;
- low-volume / low-influence.

A persistent low-volume/high-influence population would be especially valuable evidence.

---

# 10. Event-level reasoning-worthiness

Do not stop at wallet-level scores. Build:

`R_(i,e,t)`

Candidate pre-reasoning features:

### Novelty
- new counterparty;
- new contract;
- new event family;
- new path;
- first interaction after inactivity.

### Surprise
- deviation from wallet history;
- deviation from community history;
- deviation from temporal baseline.

### Regime change
Distance between current and historical behavioral states.

### Graph disruption
Local graph changes induced by the event.

### Ambiguity
- competing candidates;
- weak historical support;
- conflicting context.

All must be computed without future information.

---

# 11. Multi-agent research tournament

All groups use the same data contract, chronological splits, and frozen evaluation.

### Group A — Behavior
Frequency, recency, burstiness, entropy, behavioral transitions.

### Group B — Temporal graph
Dynamic degree, temporal PageRank, community change, bridge score, graph disruption.

### Group C — Predictive influence
Direct future-spillover estimators.

### Group D — Information gain
Approximate `H(Y|C_t) - H(Y|C_t,X_i)` with non-LLM models first.

### Group E — Event novelty
New counterparties/contracts/rare paths/regime transitions.

### Group F — Qwen semantic representation
Use local Qwen3.5-4B to extract structured behavioral state. No future outcomes.

### Group G — Reasoning-gain predictor
Directly predict `RV`.

### Group H — Hybrid selector
Combine influence, behavior, novelty, surprise, graph and semantic state.

### Group I — Strong baselines
Random, activity, volume, degree, PageRank, k-core, uncertainty-only, repeat-only, centrality, cheap-ranker uncertainty.

### Group J — External benchmark
Maintain TGB validation and standard temporal-graph baselines.

### Group K — Adversarial audit
Attempt to invalidate every promising selector, especially through leakage and volume confounds.

Before first submission, groups cannot inspect competitors' results. Afterward: critique, reproduce, tournament, ablate, prune.

---

# 12. Selector benchmark

For each cutoff, select exactly:

`K in {10, 25, 50, 100, 250, 500, 1000}`

Compare:

```text
Random
Volume
Activity
Degree
PageRank
Behavior
Dynamic Influence
Reasoning Value
Novelty
Uncertainty
Hybrid
Oracle (upper bound only)
```

The Oracle may use observed future reasoning gain only as an upper bound. Never present it as deployable.

---

# 13. Matched-budget evaluation

For every selector:

`Budget(K) = K * Cost_FullCF`

Compare:

- All Cheap;
- All Full-CF where feasible;
- Random selective reasoning;
- baseline selectors;
- learned selector;
- Oracle upper bound.

Primary metric:

`incremental predictive utility / measured reasoning cost`

Secondary:

- MRR;
- Recall@1/5/10;
- NDCG;
- log loss;
- calibration;
- coverage;
- latency;
- fallback/failure rate.

The most important figure is the **budget–utility curve**.

---

# 14. Required figures

Produce at least:

1. `reasoning_gain_distribution.pdf`  
   Distribution of RV, split by `new_tail`, `new_popular`, `repeat_easy`, `repeat_hard`.

2. `selector_ndcg.pdf`  
   Quality of predicting high-RV events.

3. `budget_utility_curve.pdf`  
   Utility vs expensive-reasoning budget.

4. `influence_vs_volume.pdf`  
   Dynamic influence vs volume, highlighting low-volume/high-influence wallets.

5. `temporal_generalization.pdf`  
   June/July → August → September.

6. `efficiency_frontier.pdf`  
   Utility vs measured tokens/latency.

These figures should be paper-quality and reproducible from registered experiment outputs.

---

# 15. Statistical testing

Use paired bootstrap at the correct dependency unit (wallet/event/cutoff as appropriate).

Report:

- point estimate;
- 95% CI;
- paired difference;
- relative improvement;
- p-value where appropriate.

For many selector comparisons, correct for multiplicity or clearly pre-register primary comparisons.

Do not treat correlated events from the same wallet as independent observations.

---

# 16. Cross-model robustness

The method must not be tied to one LLM.

Evaluate:

- current Full-CF model as primary;
- a second independently configured/model family as secondary.

Test:

`RV_A`, `RV_B`, and their correlation.

Also test:

- selector trained on model A → model B;
- selector trained on model B → model A.

A selector that survives model transfer is much stronger evidence for NAACL.

---

# 17. Qwen track

Use Qwen3.5-4B only if semantic state adds information beyond numerical temporal/graph features.

Preferred structured output:

```json
{
  "behavior_state": "...",
  "strategy_shift": "...",
  "counterparty_pattern": "...",
  "novelty": 0.0,
  "uncertainty": 0.0,
  "regime_change": 0.0
}
```

Do not make free-form LLM reasoning the primary selector representation.

Main question:

> Does compact semantic behavioral representation improve reasoning-worthiness beyond temporal graph statistics?

If not, remove it from the core method.

---

# 18. Do NOT do yet

Do not prioritize:

1. K-step recursive rollout.
2. Micro→meso→macro aggregation.
3. Huge prompt sweeps.
4. Larger LLMs without a hypothesis.
5. Complex routers before valid supervision.
6. September threshold tuning.
7. Causal claims from predictive spillover.
8. SOTA claims on a self-created task.
9. Cherry-picking wallet subsets.
10. Extra datasets solely to increase experiment count.

K-step is Phase II-B and starts only after this phase passes its entry criteria.

---

# 19. Phase II-B entry criteria

Proceed to K-step only if:

### Scientific
- RV is heterogeneous;
- a pre-reasoning selector beats random;
- it beats strong naive baselines;
- gains survive August;
- gains survive September;
- gains are not explained by volume.

### Methodological
- no leakage;
- exact matched budget;
- measured tokens/latency;
- reproducible selector;
- confidence intervals.

### Robustness
- cross-model evaluation;
- category-wise analysis;
- adversarial leakage audit.

### Paper
At least one defensible statement exists:

> **Selective reasoning achieves higher predictive utility per unit reasoning budget than uniform or naive allocation.**

If false, report the failure and pivot rather than forcing a positive result.

---

# 20. Experiment registry

Create:

`research/phase2/EXPERIMENT_REGISTRY.yaml`

Every experiment records:

```yaml
experiment_id:
hypothesis:
agent:
code_commit:
data_version:
feature_version:
train_period:
tune_period:
test_period:
model:
selector:
reasoning_policy:
budget:
seed:
metrics:
tokens:
latency:
result:
confidence_interval:
leakage_audit:
status:
```

No unregistered result enters final tables.

---

# 21. Required deliverables

```text
research/phase2/
├── PHASE1_RESULT_AUDIT.md
├── phase1_result_registry.csv
├── reasoning_gain_dataset.parquet
├── dynamic_influence_dataset.parquet
├── selector_benchmark.csv
├── EXPERIMENT_REGISTRY.yaml
├── selector_results/
├── figures/
│   ├── reasoning_gain_distribution.pdf
│   ├── selector_ndcg.pdf
│   ├── budget_utility_curve.pdf
│   ├── influence_vs_volume.pdf
│   ├── temporal_generalization.pdf
│   └── efficiency_frontier.pdf
├── FINAL_SYNTHESIS.md
└── PHASE2_HANDOFF.md
```

`FINAL_SYNTHESIS.md` must answer:

1. Is reasoning gain heterogeneous?
2. Can reasoning-worthiness be predicted before reasoning?
3. Which feature family matters most?
4. Does dynamic influence beat static importance?
5. Does selective reasoning beat random at equal budget?
6. Does it survive temporal holdout?
7. Does it survive cross-model testing?
8. Does it justify K-step?
9. What is the simplest publishable method?
10. What should be the primary NAACL/WWW claim?

---

# 22. Decision tree

### A — Strong selective-reasoning result

If:

`Selective > Random > Cheap`

under matched budget and temporal holdout:

Proceed to Phase II-B.

Potential core framing:

> **Reasoning-Worthiness: Learning Where Expensive LLM Reasoning Pays Off in Dynamic Ethereum Transaction Networks**

### B — Influence works, reasoning-worthiness does not

Pivot toward:

> Dynamic Predictive Influence in Ethereum Transaction Networks

More WWW-oriented.

### C — Reasoning gain works but influence does not

Pivot toward:

> Adaptive Inference-Time Reasoning for Transaction Forecasting

More NAACL-oriented.

### D — No selector generalizes

Investigate whether reasoning gain is unstable, model-specific, or the event formulation is too narrow.

### E — TGB is strong but the custom task is weak

Use TGB as validation; redesign the custom benchmark rather than claiming broad superiority.

---

# 23. Immediate execution order

Execute exactly:

```text
0. Freeze Phase-I commit
1. Audit all 11 groups
2. Diagnose/rerun June anomaly
3. Build reasoning_gain_dataset
4. Build dynamic_spillover labels
5. Run strong non-LLM selector baselines
6. Run multi-agent selector tournament
7. Freeze best selector on July
8. Evaluate August
9. Evaluate September
10. Cross-model robustness
11. Adversarial leakage/volume audit
12. Produce paper-quality figures
13. Chief Scientist synthesis
14. Decide whether Phase II-B is justified
```

**No K-step before Step 14.**

---

# 24. Chief Scientist principle

Do not maximize experiment count. Maximize the probability of discovering a robust publishable phenomenon.

When agents disagree:

1. prefer reproducible evidence;
2. prefer chronological evaluation;
3. prefer simpler explanations;
4. prefer matched-cost comparisons;
5. prefer cross-model replication;
6. prefer adversarially robust results;
7. prefer falsifiable scientific claims.

Ask after every experiment:

> **What phenomenon does this result reveal?**

---

# 25. Definition of success

The phase succeeds if the repository supports, with reproducible evidence:

> **Expensive counterfactual reasoning is not uniformly useful across Ethereum wallet-events. A pre-reasoning selector can identify events with substantially higher expected reasoning gain, allowing a fixed reasoning budget to achieve higher predictive utility than uniform, random, or static-importance allocation, with the effect surviving chronological and cross-model evaluation.**

If this statement is false, report that clearly and identify the strongest surviving hypothesis.

The project should not become “we used more agents to predict Ethereum transactions.”

The intended contribution is:

**Learning where reasoning is worth spending.**

The Ethereum graph is the environment.  
The LLM is the expensive reasoning mechanism.  
The selector is the scientific contribution.  
The fixed-budget temporal evaluation is the proof.  
Counterfactual reasoning provides the auditable mechanism for additional computation.
