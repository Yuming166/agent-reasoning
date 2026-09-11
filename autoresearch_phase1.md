# autoresearch.md — Phase I: Dynamic Wallet Identity & Influential Wallet Discovery

## 0. Mission

You are the autonomous research team for Phase I of the Ethereum microtransaction reasoning project.

The ultimate project goal is:

> decentralized transaction data → dynamic behavioral identity → emergent communities → dynamic predictive influence → adaptive reasoning allocation → trustworthy high-order recursive reasoning → micro→meso→macro market rollout

**Phase I stops BEFORE high-order recursive trustworthy reasoning.**

The Phase-I question is:

> **Which Ethereum wallets are worth paying attention to, at what time, and why?**

The output must be a scientifically defensible, temporally valid, dynamically updated set/ranking/vector of important wallets that can later be handed to Phase II.

Do not prematurely implement high-order recursive reasoning.

---

## 1. Core Research Question

For wallet i at cutoff t, define:

S_i(t) = all information about wallet i observable at or before t.

The central object is a time-dependent importance/influence representation:

I_i(t)

A useful hypothesis is:

I_i(t) = Δ Predictability(Y_future | C_t, X_i(t))

or:

IG_i(t) = H(Y_future | C_t) - H(Y_future | C_t, X_i(t))

These are hypotheses, not assumptions that must be accepted.

The team must investigate multiple competing definitions of wallet importance.

---

## 2. Non-Negotiable Scientific Principles

### No future leakage

At cutoff t, every feature used to define identity, community, influence, or importance must be computable using information available at or before t.

Never use future transactions, future wallet labels, future network statistics, future prices, future social information, or future model performance to construct the selection set being evaluated.

### No circularity

Correct:

historical data ≤ t → estimate importance → freeze top-K → observe future → evaluate

Incorrect:

historical + future → find influential wallets → evaluate on the same future

### Influence is not transaction volume

Volume is a baseline, not a definition of influence.

Explicitly test:

- low-volume / high-influence wallets
- high-volume / low-influence wallets

### Predictive influence is not causal influence

Unless a valid causal identification strategy is implemented, never call the result causal.

Use terms such as predictive influence, information contribution, lead-lag influence, or downstream predictive utility.

### Importance may be multidimensional

Do not force all useful notions into one scalar prematurely.

A possible final representation is:

I_i(t) = [I_behavior, I_network, I_predictive, I_information, I_temporal]

---

## 3. Current Data Contract

Primary working data is the existing EX-Graph-derived Ethereum microtransaction dataset.

Known scope:

- approximately 27,613 EX-Graph-mapped Ethereum addresses
- Google Blockchain Analytics materializations
- approximately 2022-03-01 to 2022-09-01 for historical development
- approximately 2022-09 to 2022-10 for holdout/future evaluation
- approximately 11.63M source rows
  - native transactions
  - token transfers
  - internal traces
- directional source/counterparty sequences
- static structural features
- minute-level ETH price
- 52 blockchain/crypto social-media influencers' tweets

Social data is external context. It is NOT a reliable set of wallet-owner tweets.

Do not invent an author→wallet identity mapping.

---

## 4. Phase-I Scope

Include:

1. data and leakage audit
2. temporal state construction
3. behavioral representation
4. dynamic behavioral identity/persona
5. dynamic communities
6. competing wallet-importance definitions
7. predictive influence experiments
8. information-gain/counterfactual experiments where feasible
9. benchmark discovery and benchmark alignment
10. standard Ethereum benchmark evaluation
11. dynamic influential-wallet benchmark design
12. budgeted wallet-selection evaluation
13. cross-method robustness
14. final important-wallet selection/ranking
15. Phase-II handoff

Explicitly exclude:

- high-order recursive reasoning
- recursive debate
- recursive evidence graphs
- advanced trustworthy reasoning
- multi-step LLM reasoning rollout
- final market trading agent
- unsupported causal claims
- expensive LLM reasoning over all wallets

---

# 5. Research Tournament Architecture

Use multiple concurrent research groups.

The Chief Scientist must NOT impose one preferred definition of importance at the beginning.

## Group 0 — Data & Leakage Audit

Establish a trusted temporal protocol.

Check:

- timestamps and cutoff semantics
- train/validation/test boundaries
- duplicate or future-derived features
- social-data timing
- per-cutoff graph statistics
- label leakage
- reproducible temporal snapshots

Outputs:

- `research/audit/DATA_AUDIT.md`
- `research/audit/temporal_protocol.yaml`

No final result is valid until this protocol passes audit.

## Group A — Behavior-First

Hypothesis:

> A wallet's behavioral identity is a strong determinant of future predictive usefulness.

Construct:

S_i(t) → Z_i(t) → P_i(t)

where P_i(t) is a dynamic persona.

Compare:

- handcrafted numerical features
- trajectory representations
- sequence embeddings
- K-means
- GMM
- HDBSCAN
- hierarchical clustering where useful

Candidate features:

Activity:
- transaction count
- active days
- inter-arrival statistics
- burstiness
- dormancy/reactivation
- activity acceleration

Capital:
- inflow/outflow/netflow
- volume
- volume change
- token diversity
- concentration

Counterparties:
- unique counterparties
- new/repeat ratio
- concentration
- turnover
- first-time interaction rate

Network:
- degree
- weighted degree
- PageRank
- k-core
- local clustering
- bridge/brokerage measures

Trajectory:
- action sequence
- counterparty sequence
- token sequence
- amount buckets
- time-gap sequence

Evaluate:

- silhouette
- cluster stability
- bootstrap consistency
- temporal persistence
- transition structure
- downstream predictive utility

Do not assume K-means is correct.

## Group B — Predictive-Influence-First

Hypothesis:

> The best definition of an important wallet is the wallet whose historical state improves prediction of future ecosystem behavior.

Possible targets:

- next counterparty
- next interaction
- future wallet activity
- future edge formation
- future community evolution
- aggregate ecosystem activity
- future transaction direction
- future flow category

Metrics may include:

- NLL
- AUC / PR-AUC
- MRR
- Recall@K
- Brier score
- calibration
- time-to-event metrics

Test whether importance is persistent, regime-specific, community-specific, event-specific, or short-lived.

Use strict out-of-sample evaluation.

## Group C — Temporal-Graph-First

Hypothesis:

> Important wallets are structurally important in the evolving transaction network.

Investigate:

- degree
- weighted degree
- PageRank
- k-core
- betweenness/brokerage
- temporal centrality
- temporal motif participation
- community bridge score
- dynamic node influence
- network propagation proxies

Compare static vs rolling-window vs temporal graph importance.

Test whether graph importance predicts future network behavior.

Do not equate centrality with predictive influence.

## Group D — Information-Gain / Counterfactual-First

Hypothesis:

> An important wallet is one whose historical presence or information substantially reduces uncertainty about the future.

Use:

IG_i(t) = H(Y_future | C_t) - H(Y_future | C_t, X_i(t))

Where feasible, use counterfactual masking:

full context → predict future → mask wallet i → predict again → measure performance difference

Possible variants:

- wallet masking
- feature masking
- community masking
- trajectory masking
- influence residualization

Start with representative subsets. Do not run expensive experiments over all 27k wallets without evidence that they are needed.

## Group E — Qwen Behavioral Representation

Hypothesis:

> A local Qwen model can discover semantic behavioral identities that complement numerical graph features.

Use Qwen to obtain:

- behavioral summaries
- recurring interaction patterns
- strategy-like behavior
- state transitions
- anomalies
- uncertainty
- regime changes

Never accept “Qwen says this wallet is important” as ground truth.

Compare:

1. numerical representation
2. trajectory representation
3. Qwen semantic representation
4. Qwen latent representation, if technically available
5. combined representation

Every Qwen representation must be validated by an independent downstream metric.

## Group F — Benchmark / SOTA Track

Explicitly answer:

> Where can this research make a credible state-of-the-art claim?

Search for:

- Ethereum link prediction
- Ethereum account classification
- phishing detection
- wash-trading detection
- wallet/entity classification
- behavioral clustering
- transaction prediction
- temporal graph prediction
- blockchain address prediction
- wallet influence / importance
- information-based graph node selection
- budgeted node selection
- active learning / graph subset selection

For each candidate benchmark record:

```text
benchmark_name
paper
year
venue
dataset
task
official_split
metrics
current_SOTA
public_code
public_leaderboard
data_access
compatibility_with_our_data
leakage_risk
reproduction_cost
novelty_potential
NAACL_fit
```

Distinguish a true public benchmark from a paper-specific evaluation or informal leaderboard.

---

# 6. Standard Benchmark Track

The first standard benchmark target should be EX-Graph Ethereum Link Prediction.

EX-Graph officially provides:

- Ethereum link prediction
- wash-trading address detection
- X/Ethereum matching link prediction

It also provides implementations and a public leaderboard.

Treat this as external validation, not as the definition of wallet importance.

Where feasible reproduce official baselines:

- DeepWalk
- Node2Vec
- GCN
- GAT
- GraphSAGE
- GATv2
- APPNP
- TAGCN
- ClusterGCN
- GGNN
- DAGNN

Use the official protocol rather than silently changing the task.

At experiment time, query the current official leaderboard instead of hard-coding an old SOTA number.

---

# 7. Ethereum Account-Classification Validation

Investigate established Ethereum account-classification datasets/tasks.

Candidate labels include:

- exchange
- mining
- ICO
- phishing
- gambling
- other known entity/service classes

Use these to validate whether learned behavioral representations capture real wallet roles.

Do not redefine unsupervised personas to directly match labels.

Correct sequence:

unsupervised behavioral representation → dynamic clusters/personas → external label validation

Also investigate newer labeled Ethereum datasets with thousands of labeled addresses and known entities.

---

# 8. New Benchmark Track: Dynamic Influential Wallet Discovery

If no sufficiently standard benchmark exists, formalize a new task.

At cutoff t, given:

G_≤t

select:

I_t^K = {i_1, ..., i_K}

The future period G_(t:t+Δ) remains hidden during selection.

Evaluate future predictive utility.

Potential metrics:

- future prediction gain
- NDCG
- Recall@K
- MRR
- rank correlation with future realized utility
- future link prediction
- future activity prediction
- future edge formation
- future community evolution
- temporal persistence
- selection overlap
- utility per selected wallet

The selector must be compared against strong simple baselines.

---

# 9. New Benchmark Track: Budgeted Wallet Selection

This is high priority because it directly precedes Phase-II reasoning allocation.

With N ≈ 27,613 and budget:

K ∈ {10, 25, 50, 100, 250, 500, 1000}

select K wallets to maximize future downstream predictive utility.

Baselines:

- random
- transaction volume
- activity
- degree
- weighted degree
- PageRank
- k-core
- behavioral score
- predictive influence
- information gain
- hybrid methods

Report:

U(K)

and:

U(K)/K

Study the full budget-quality frontier.

---

# 10. Influence Residual Analysis

Investigate:

InfluenceResidual_i = I_i - E[I | Volume_i]

Question:

> Which wallets are more influential than their financial size would suggest?

Explicitly test:

- low-volume / high-influence
- high-volume / low-influence
- high-centrality / low-predictive-influence
- low-centrality / high-predictive-influence

Do not assume these groups exist.

---

# 11. Persona × Influence

Estimate dynamic persona P_i(t) and influence I_i(t) jointly.

Questions:

1. Which personas are most predictive?
2. Does influence vary strongly within a persona?
3. Do persona transitions precede influence changes?
4. Does a wallet become influential after switching persona?
5. Are high-influence wallets concentrated in certain communities?
6. Are low-volume/high-influence wallets behaviorally distinctive?
7. Is influence stable within a persona?

Produce, where possible:

```text
persona
mean influence
median influence
tail influence
influence stability
future utility
community concentration
regime dependence
```

---

# 12. Dynamic Communities

Investigate whether important wallets are:

- hubs within communities
- bridges between communities
- representatives of emerging communities
- connectors between behavioral personas
- transient boundary wallets

Compare:

1. transaction communities
2. behavioral communities
3. hybrid communities

All community construction must respect the relevant temporal cutoff.

---

# 13. Wallet-Importance Evaluation Protocol

For every cutoff:

Past
→ wallet state
→ behavioral identity
→ communities
→ influence estimation
→ top-K selection
→ FREEZE
→ future observation
→ evaluation

Preferred structure:

development period
→ method selection
→ frozen evaluation protocol
→ multiple walk-forward windows
→ final untouched holdout

Do not report only one convenient split.

---

# 14. Baseline Hierarchy

Every new wallet-selection method must compare against:

### Random
- random K

### Size
- transaction volume K
- ETH flow K
- activity K

### Structural
- degree K
- weighted degree K
- PageRank K
- k-core K

### Behavioral
- cluster-based K
- behavioral anomaly K

### Temporal
- recent activity K
- acceleration K
- persistence K

### Predictive
- predictive influence K

### Information
- information gain K

Never compare only against weak baselines.

---

# 15. Required Ablations

At minimum:

1. no behavioral features
2. no network features
3. no temporal features
4. no market context
5. no trajectory features
6. static vs dynamic importance
7. volume-only
8. network-only
9. behavior-only
10. predictive-only
11. information-only
12. combined model

For Qwen:

- no Qwen
- semantic summary only
- latent representation only
- numerical + Qwen
- trajectory + Qwen

---

# 16. K Sensitivity

Always evaluate:

K ∈ {10,25,50,100,250,500,1000}

Do not optimize K on the final test period.

Plot:

- future utility vs K
- utility per wallet vs K
- overlap across methods vs K
- stability vs K

The goal is to understand the budget-quality frontier, not merely find one perfect K.

---

# 17. Important-Wallet Convergence Analysis

Different methods may select different wallets.

Compute:

- Jaccard overlap
- rank correlation
- top-K overlap
- consensus frequency
- method-specific uniqueness
- future utility of consensus wallets

If independent methods repeatedly identify the same wallets, this is evidence of robust importance.

If rankings diverge strongly, investigate whether importance is multidimensional.

Consensus is not proof of correctness.

---

# 18. Open Research Track

Each group may propose at least one non-predefined definition.

Examples:

- influence concentration
- influence novelty
- behavioral surprise
- propagation importance
- bridge importance
- reasoning-worthiness

Any novel definition must pass the same temporal evaluation.

---

# 19. Research Tournament Rules

Groups initially work independently.

Before seeing other groups' results, each group submits:

```text
research question
hypothesis
importance definition
representation
algorithm
evaluation protocol
baselines
expected failure modes
compute cost
novelty
```

Then the Chief Scientist compares them.

Maintain:

| Method | Definition | Future Utility | Stability | Cost | Novelty | Leakage Risk | Benchmark Fit |
|---|---|---:|---:|---:|---:|---|---|

After Round 1:

- allow cross-team critique
- reproduce promising results
- challenge assumptions
- run head-to-head comparisons

Any post-result hypothesis change must be documented.

---

# 20. Compute Strategy

Use a staged funnel.

Suggested:

27k+
→ cheap activity/temporal filter
→ 5k–10k
→ behavioral representation
→ 1k–3k candidates / representative states
→ network + temporal influence
→ 500–1k
→ predictive / information-based evaluation
→ top 50–500

For Qwen, initially sample:

- cluster medoids
- high-influence wallets
- low-influence wallets
- low-volume/high-influence
- high-volume/low-influence
- persistent wallets
- episodically influential wallets
- regime-transition wallets
- random controls

Scale only after evidence of utility.

---

# 21. Experiment Registry

Every experiment must record:

```yaml
experiment_id:
timestamp:
git_commit:
data_version:
cutoff_windows:
model:
features:
representation:
selection_method:
K:
seed:
compute:
runtime:
gpu_hours:
metrics:
result:
status:
artifact_paths:
notes:
```

No result is valid unless reproducible.

---

# 22. Repository Structure

Maintain:

```text
research/
├── audit/
│   ├── DATA_AUDIT.md
│   └── temporal_protocol.yaml
├── benchmarks/
│   ├── BENCHMARK_SURVEY.md
│   ├── benchmark_registry.yaml
│   └── reproduction/
├── behavior/
│   ├── hypotheses.md
│   ├── representations/
│   ├── clustering/
│   └── persona_results/
├── influence/
│   ├── hypotheses.md
│   ├── predictive/
│   ├── network/
│   ├── information_gain/
│   └── residual_analysis/
├── qwen/
│   ├── prompts/
│   ├── representations/
│   └── behavioral_analysis/
├── tournament/
│   ├── group_A/
│   ├── group_B/
│   ├── group_C/
│   ├── group_D/
│   ├── group_E/
│   ├── group_F/
│   └── OPEN_TRACK/
├── experiments/
│   └── EXPERIMENT_REGISTRY.yaml
└── final/
    ├── FINAL_SYNTHESIS.md
    ├── important_wallets.parquet
    ├── wallet_importance_scores.parquet
    ├── wallet_behavior_profiles.parquet
    ├── wallet_communities.parquet
    ├── selection_policy.yaml
    └── phase2_handoff.md
```

---

# 23. Final Phase-I Deliverables

## A. Dynamic wallet state

For every evaluated wallet and cutoff:

S_i(t)

with reproducible features.

## B. Behavioral identity

P_i(t), or an equivalent dynamic behavioral representation.

## C. Communities

C_i(t), where applicable.

## D. Multiple importance scores

Where computationally feasible:

I_behavior(t)
I_network(t)
I_predictive(t)
I_information(t)

## E. Final ranking representation

Prefer a vector/table rather than prematurely collapsing everything:

```text
wallet
timestamp
behavior_score
network_score
predictive_score
information_score
stability_score
community
persona
volume
influence_residual
```

## F. Selection policy

A machine-readable policy for selecting:

- top 10
- top 25
- top 50
- top 100
- top 250
- top 500
- top 1000

## G. Benchmark report

Separate:

1. standard benchmark results
2. new-task results
3. exploratory findings

Never present a self-created task as an established benchmark.

## H. Phase-II handoff

Create:

`research/final/phase2_handoff.md`

It must answer:

> Given a fixed computational budget, which wallets should Phase II spend expensive trustworthy reasoning on?

---

# 24. Criteria for Choosing the Final Method

Do not choose solely by:

- training loss
- in-sample score
- complexity
- novelty
- LLM-generated explanation
- theoretical elegance

Use a multi-objective decision based on:

- future utility
- stability
- generalization
- efficiency
- interpretability
- novelty
- benchmark performance

A slightly weaker peak model may be preferable if it is substantially more stable, reproducible, or efficient.

The Chief Scientist must document this tradeoff.

---

# 25. Stop Conditions

Phase I is complete when:

1. temporal protocol is audited;
2. leakage audit passes;
3. multiple definitions of wallet importance have been tested;
4. strong baselines have been evaluated;
5. at least one strict out-of-sample evaluation is complete;
6. benchmark compatibility has been assessed;
7. dynamic behavior/persona analysis is sufficiently complete for interpretation;
8. important-wallet rankings are reproducible;
9. K-budget curves are available;
10. final selection policy is frozen;
11. Phase-II handoff is complete.

Do not automatically continue into high-order recursive reasoning.

Stop and summarize the evidence.

---

# 26. What Counts as a Strong Phase-I Result?

Weak:

> “Our model produces interesting wallet clusters.”

Strong:

> “Using only information available before each cutoff, our method identifies a small subset of wallets that consistently provides substantially more future predictive utility than random, volume, activity, and graph-centrality selection across multiple walk-forward periods.”

Stronger:

> “The wallet selector improves established Ethereum prediction benchmarks and establishes a reproducible dynamic influential-wallet benchmark in which the proposed selector achieves superior future utility under a fixed wallet/reasoning budget.”

Potentially strongest:

> “Behavioral identity, network structure, predictive influence, and information contribution capture partially distinct dimensions of wallet importance, and their combination yields a robust budget-quality frontier.”

---

# 27. Scientific Writing Target

Do not frame the project merely as:

> “We used LLMs to analyze Ethereum transactions.”

Prefer a scientific framing such as:

> **Dynamic Influential Wallet Discovery for Predictive Ethereum Ecosystem Modeling**

or, if supported by results:

> **Who Is Worth Reasoning About? Dynamic Wallet Importance and Budgeted Reasoning Allocation in Ethereum**

The primary contribution should be the formalization and empirical evaluation of dynamic wallet importance. LLMs are one representation/component, not automatically the entire novelty claim.

---

# 28. Chief Scientist Final Decision

At the end of Phase I, produce:

`research/final/FINAL_SYNTHESIS.md`

with exactly:

1. Executive conclusion
2. What “important wallet” means empirically
3. Best-performing definition
4. Best behavioral representation
5. Best community representation
6. Best predictive influence method
7. Best information-based method
8. Benchmark results
9. New benchmark proposal
10. Budgeted-selection results
11. Robustness and failure cases
12. Low-volume/high-influence findings
13. High-volume/low-influence findings
14. Convergence/divergence between methods
15. What remains uncertain
16. Recommended Phase-II design
17. Exact frozen wallet-selection interface
18. Reproducibility checklist

Clearly distinguish:

- established evidence
- exploratory evidence
- hypotheses
- unresolved questions

---

# 29. Final Principle

Do not optimize for making the original idea look correct.

Optimize for discovering:

> **What definition of wallet importance survives strict temporal evaluation, strong baselines, independent reproduction, and a fixed downstream budget?**

If the answer differs from the initial hypothesis, that is a successful research result.

**Phase I ends with a validated dynamic wallet-selection layer. Only after that should Phase II investigate high-order recursive trustworthy reasoning.**
