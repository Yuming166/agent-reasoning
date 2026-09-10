# AutoResearch Master Plan — Dynamic Ethereum Behavioral Influence → Adaptive High-Order Trustworthy Recursive Reasoning

> **Mission:** Run an autonomous, overnight research program that takes the current Ethereum microtransaction dataset all the way from **dynamic investor/wallet profiling and influential-node discovery** to **adaptive high-order recursive forecasting with counterfactual, step-level trustworthy verification**, producing reproducible experiments, figures, tables, ablations, and a publication-ready research narrative.
>
> **Primary target:** NAACL 2027 (or a comparably strong NLP/ML venue).
>
> **Execution model:** One orchestrating DeepSeek V4 Pro Max instance may spawn/coordinate multiple concurrent specialist roles. Treat the roles as a research team, not as independent chat personas. They share artifacts through the repository and must challenge one another's conclusions.
>
> **Local model:** Qwen3.5-4B is available locally on **4×RTX 4090**. It may be used extensively for behavioral profiling, representation extraction, candidate reasoning, and controlled inference experiments. Do not send raw/private transaction data to external APIs.
>
> **Token budget:** Up to approximately **1B tokens** for the autonomous research run. Spend compute adaptively; do not burn the budget on indiscriminate exhaustive sweeps.

---

## 0. Non-negotiable research principles

1. **Temporal integrity is absolute.**
   For every prediction timestamp `t`:
   - all features satisfy `time(feature) <= t`;
   - labels/events occur strictly after `t`;
   - no future-derived normalization, clustering, vocabulary, graph statistics, or LLM context may leak information from the evaluation horizon;
   - every experiment must record its information cutoff.

2. **Predictive influence ≠ causal influence.**
   Unless a genuine causal identification strategy is implemented, call the proposed quantity **predictive influence**, **downstream predictive spillover**, or **information contribution**, never causal influence.

3. **Do not assume high transaction volume means high influence.**
   Explicitly test:
   - high-volume/high-influence;
   - high-volume/low-influence;
   - low-volume/high-influence;
   - low-volume/low-influence wallets.

4. **Do not assume behavioral clusters are novel.**
   Wallet/user clustering already exists in blockchain/DeFi research. Novelty must come from connecting **dynamic behavioral identity → predictive influence → adaptive reasoning allocation → trustworthy recursive forecasting**.

5. **Do not claim wallet ownership or real-world identity.**
   Use terms such as wallet, address, behavioral entity, latent behavioral role, or behavioral community. Address linkage to a person/entity requires independent evidence.

6. **LLMs are experimental instruments, not unquestioned oracles.**
   Every Qwen-generated behavioral profile or reasoning step must have:
   - provenance;
   - temporal validity;
   - confidence;
   - reproducibility/stability checks;
   - evidence-removal or counterfactual tests where applicable.

7. **Do not optimize only for headline accuracy.**
   Evaluate:
   - predictive quality;
   - calibration;
   - selective risk;
   - abstention quality;
   - reasoning cost;
   - robustness;
   - temporal generalization;
   - incremental value over strong non-LLM baselines.

8. **Negative results are valuable.**
   If LLM embeddings do not beat numerical representations, report it.
   If influence does not help routing, report it.
   If recursive depth hurts calibration, report it.
   Do not tune until a preferred story appears.

9. **The system must remain reproducible.**
   Every important run gets:
   - configuration;
   - seed;
   - git commit;
   - data version;
   - model/version;
   - cutoff dates;
   - compute budget;
   - result file;
   - interpretation.

10. **Do not fabricate completion.**
    A planned experiment is not a result. A failed run is not evidence of a hypothesis. A missing metric must be marked missing.

---

# 1. Research question

The central question is:

> **If tomorrow we can spend 100× more reasoning compute on only a small subset of Ethereum wallets, what principled, temporally valid signal should determine which wallets receive that compute, and can trustworthy adaptive recursive reasoning on those wallets improve downstream multi-step behavioral forecasting?**

The research program should test the following chain:

```text
Decentralized transaction data
        ↓
Dynamic behavioral identity
        ↓
Emergent behavioral communities
        ↓
Dynamic predictive influence
        ↓
Reasoning-worthiness / reasoning ROI
        ↓
Adaptive reasoning depth
        ↓
Counterfactual step-verified recursive reasoning
        ↓
Multi-step wallet/counterparty/action forecasting
        ↓
Micro → meso → macro market rollout
```

The primary scientific contribution should be the **reasoning architecture and empirical evidence**, not a generic crypto trading bot.

---

# 2. Hypotheses

Test these independently.

### H1 — Volume is insufficient
Transaction volume, cash flow, balance, or activity alone are insufficient to identify the wallets whose observations most improve future downstream prediction.

### H2 — Behavioral structure exists
Wallets exhibit recurring behavioral patterns that can be recovered from temporal transaction trajectories.

### H3 — Behavioral identity is dynamic
A wallet's behavioral role changes across time and market/network regimes.

### H4 — Representation matters
Behavioral representations combining trajectory information outperform static handcrafted financial features for identifying useful behavioral roles.

Compare:
- numerical features;
- sequence/trajectory representations;
- Qwen semantic summaries;
- Qwen latent representations;
- combined representations.

### H5 — Predictive influence is distinct from financial size
Predictive downstream influence has only partial correlation with:
- volume;
- degree;
- balance;
- transaction count;
- centrality.

### H6 — Influence is dynamic
The same wallet can be highly influential in one regime and irrelevant in another.

### H7 — Influence is role-conditional
The value of observing a wallet depends on its behavioral role.

### H8 — Community context matters
Wallet behavior is better predicted when temporal community/network context is modeled explicitly.

### H9 — Influence can guide expensive reasoning
An influence-aware router can achieve a better quality/cost trade-off than uniform shallow or uniform deep reasoning.

### H10 — Counterfactual verification improves reliability
Removing, replacing, or perturbing evidence can identify fragile reasoning steps and reduce unsupported recursive forecasts.

### H11 — Recursive reasoning provides incremental value
High-order recursive forecasting:

```text
A_t → B_{t+1} → C_{t+2} → D_{t+3}
```

provides information not recoverable from independent one-step predictions, after controlling for model capacity and compute.

### H12 — Adaptive recursion is better than uniform recursion
Given the same reasoning budget, allocating additional depth selectively according to:

```text
Influence
+ uncertainty
+ counterfactual sensitivity
+ community importance
+ expected reasoning ROI
```

outperforms assigning the same depth to every case.

---

# 3. Current data/resources

First audit the actual repository rather than trusting this document.

Expected resources include:

- >20,000 Ethereum addresses; current project metadata may contain ~27,613 EX-Graph-mapped addresses.
- Full transaction histories for the selected addresses.
- Google Blockchain Analytics materializations.
- Native transactions.
- ERC-20/token transfers.
- Internal traces.
- Directional target/counterparty sequences.
- Static structural features.
- Minute-level ETH price.
- 52 blockchain/crypto social-media influencers' tweets.
- External crypto influencer tweet dataset.

Important distinction:

> The 52 influencer tweets are **external social context**, not wallet-owner tweets. There is no assumed reliable author-wallet crosswalk.

The current repository may contain artifacts and scripts related to:

```text
artifacts/
data/
metadata/
notes/
src/
DATA_ACCESS.md
README.md
run_llm_v2_floatfix.sh
```

Do not assume paths are unchanged. Discover the repository structure first.

---

# 4. Multi-agent research organization

DeepSeek should NOT behave as one monolithic coding agent.

Create a lightweight research council with concurrent specialist roles.

## Role A — Principal Investigator / Theory Lead

Responsibilities:
- formulate/refine hypotheses;
- identify the strongest scientific story;
- decide which experiments distinguish competing explanations;
- challenge weak novelty claims;
- prevent the project from becoming "just clustering + LLM + trading";
- maintain `research/PI_DECISIONS.md`.

Every major result must answer:

1. What hypothesis does this test?
2. What alternative explanation exists?
3. What experiment distinguishes them?
4. What would falsify our interpretation?

---

## Role B — Data & Temporal Integrity Auditor

Responsibilities:
- inspect schemas;
- trace every feature to source timestamp;
- detect future leakage;
- validate train/validation/test boundaries;
- inspect normalization and clustering leakage;
- check social-data timestamps;
- validate holdout construction;
- maintain `research/audit/`.

Mandatory deliverables:

```text
research/audit/DATA_AUDIT.md
research/audit/LEAKAGE_AUDIT.md
research/audit/TEMPORAL_SPLITS.md
research/audit/FEATURE_LINEAGE.csv
```

Any experiment with unresolved leakage concerns is **provisional**, not a paper result.

---

## Role C — Quantitative Influence Scientist

Responsibilities:
- construct competing definitions of influence;
- quantify predictive spillover;
- compare influence with volume/centrality;
- analyze stability and regime dependence;
- search specifically for low-volume/high-influence cases.

Maintain:

```text
research/influence/
```

---

## Role D — Behavioral Representation Scientist

Responsibilities:
- construct temporal wallet states;
- clustering;
- trajectory representations;
- dynamic personas;
- community transitions;
- Qwen representation experiments.

Must compare numerical and LLM-derived representations fairly.

---

## Role E — Qwen Behavioral Model Scientist

Use local Qwen3.5-4B.

Responsibilities:
- structured behavioral profiling;
- trajectory summarization;
- semantic embeddings;
- latent representation extraction if technically available;
- uncertainty/stability analysis;
- counterfactual behavioral-profile experiments.

Do NOT immediately run Qwen over every transaction.

Use staged sampling.

---

## Role F — Recursive Reasoning Architect

Responsibilities:
- implement one-step → two-step → high-order recursion;
- define shared state;
- maintain evidence provenance;
- design stopping criteria;
- design adaptive depth;
- compare independent agents vs shared-state rollout.

The recursion should model behavioral dynamics, not merely textual "A believes B believes C".

---

## Role G — Trustworthy Reasoning Auditor

Responsibilities:
- verify every recursive step;
- check evidence IDs;
- test counterfactual evidence removal;
- identify unsupported inference;
- calibrate confidence;
- implement abstention/fallback;
- compare verified vs unverified reasoning.

---

## Role H — Evaluation & Statistics Lead

Responsibilities:
- design metrics;
- bootstrap confidence intervals;
- significance tests where appropriate;
- paired evaluation;
- temporal generalization;
- calibration;
- selective prediction;
- cost-normalized evaluation.

---

## Role I — Baseline & Prior-Art Lead

Responsibilities:
- implement strong non-LLM baselines;
- compare against existing temporal/network forecasting approaches;
- search current literature when needed;
- maintain novelty map.

Do not make novelty claims without evidence.

---

## Role J — Market Rollout Scientist

Secondary role.

Responsibilities:
- propagate wallet-level forecasts to community/network-level outcomes;
- then to aggregate market signals;
- test whether micro forecasts improve market-level prediction/trading;
- keep this as a downstream validation, not the primary contribution.

---

## Role K — Skeptical Reviewer

Act as an adversarial reviewer.

At every milestone ask:

- Is this just clustering?
- Is this just graph prediction?
- Is this just prompt engineering?
- Is this just agentic trading?
- Is influence defined circularly?
- Is the LLM seeing future information?
- Is recursive reasoning actually doing anything?
- Could a simpler model achieve the same result?
- Is the market result just a backtest artifact?
- Is there survivorship bias?
- Is the target trivial?

Maintain:

```text
research/reviewer/REVIEW_LOG.md
```

---

## Role L — Integration Engineer

Responsibilities:
- merge branches/artifacts;
- resolve conflicts;
- maintain reproducible pipeline;
- run end-to-end smoke tests;
- maintain `README.md`;
- maintain experiment registry.

---

# 5. Coordination protocol

Do not allow 10 agents to independently duplicate the same experiment.

Use this cycle:

```text
Hypothesis
   ↓
Experiment proposal
   ↓
PI approval / rejection
   ↓
Implementation
   ↓
Audit
   ↓
Execution
   ↓
Independent interpretation
   ↓
Skeptical review
   ↓
Replication / follow-up
   ↓
Decision
```

For major findings, require **two independent roles** to interpret the result before treating it as a stable conclusion.

Use files as the shared memory.

Recommended:

```text
research/
├── README.md
├── PI_DECISIONS.md
├── HYPOTHESES.md
├── EXPERIMENT_REGISTRY.md
├── audit/
├── influence/
├── behavior/
├── qwen/
├── recursion/
├── trust/
├── evaluation/
├── baselines/
├── market/
├── reviewer/
└── figures/
```

---

# 6. Phase I — Repository and data audit

Before research, inspect:

- repository tree;
- README;
- existing scripts;
- existing artifacts;
- metadata;
- data schemas;
- prior experiment logs;
- current one-step counterfactual reasoning implementation.

Do not rewrite working code unnecessarily.

Create a machine-readable manifest:

```yaml
data_version:
address_count:
transaction_count:
native_tx_count:
token_transfer_count:
internal_trace_count:
time_min:
time_max:
holdout_start:
holdout_end:
social_data_time_range:
price_data_time_range:
known_mapping_limitations:
```

Also create feature lineage:

```text
feature
source_table
source_timestamp
aggregation_window
available_at_prediction_time
future_safe
```

---

# 7. Phase II — Temporal wallet state

Represent each wallet at multiple cutoffs:

```text
S_i(t)
```

Possible feature groups:

### Activity
- tx count;
- inter-arrival statistics;
- active days;
- burstiness;
- dormancy;
- reactivation.

### Capital flow
- inflow;
- outflow;
- net flow;
- token diversity;
- concentration;
- value-weighted activity.

### Counterparty
- unique counterparties;
- repeat counterparties;
- new-counterparty ratio;
- counterparty concentration;
- inbound/outbound asymmetry.

### Temporal behavior
- holding duration;
- transaction spacing;
- activity regime;
- periodicity;
- response latency.

### Network structure
- degree;
- weighted degree;
- PageRank;
- temporal centrality;
- k-core;
- local clustering;
- community membership.

### Market relation
Only use market information available by `t`:
- ETH return;
- realized volatility;
- local volume;
- market regime.

### Trajectory features
Encode sequences such as:

```text
wallet → counterparty → token/action → amount bucket → time gap
```

Do not include future counterparties or future transaction labels.

---

# 8. Phase III — Behavioral identity / persona discovery

Do not start with fixed labels such as whale, trader, bot.

First discover latent behavior.

Run:

- KMeans;
- GMM;
- HDBSCAN;
- hierarchical clustering where useful.

Evaluate:

- silhouette;
- stability;
- temporal persistence;
- bootstrap consistency;
- cluster transition structure;
- downstream predictive utility.

Then interpret clusters.

Potential emergent roles may include:

- accumulator;
- momentum follower;
- contrarian;
- profit taker;
- arbitrage-like;
- liquidity-oriented;
- routing/hub-like;
- bot-like;
- dormant/reactivated;
- follower-like.

These names are interpretations, not ground truth.

Represent:

```text
Persona_i(t)
```

rather than assigning one permanent persona per wallet.

---

# 9. Phase IV — Qwen-assisted behavioral representation

Use local Qwen3.5-4B.

## Route A — Numerical representation

```text
transaction state
→ handcrafted temporal features
→ embedding/clustering
```

## Route B — Semantic behavioral representation

Compress a wallet's trajectory into a structured state summary:

```text
cutoff time
recent actions
rolling statistics
counterparty patterns
temporal patterns
market context
network context
```

Prompt Qwen to output structured JSON:

```json
{
  "dominant_behavior": "...",
  "activity_regime": "...",
  "holding_horizon": "...",
  "reaction_style": "...",
  "counterparty_style": "...",
  "market_response": "...",
  "behavioral_uncertainty": 0.0,
  "evidence": ["event_id_1", "event_id_2"]
}
```

Never feed millions of raw transactions.

## Route C — Latent representation

If Qwen's local stack allows hidden-state extraction:

```text
trajectory summary
→ Qwen hidden representation
→ dimensionality reduction
→ clustering
```

Compare:

```text
Numerical
Semantic
Latent
Numerical + Semantic
Numerical + Latent
```

A particularly interesting outcome is:

> Qwen latent representations improve predictive utility while semantic labels add little.

That would suggest latent behavioral structure is useful even when human-readable labels are insufficient.

---

# 10. Qwen sampling strategy

Do not process all 27k wallets immediately.

First select representative states using cheap numerical profiling:

- cluster medoids;
- cluster boundaries;
- high-influence candidates;
- low-volume/high-influence candidates;
- high-volume/low-influence candidates;
- persistent influencers;
- episodic influencers;
- regime-transition wallets;
- random controls.

Start with roughly 100–500 representative wallet states.

Measure:

- inference cost;
- representation quality;
- stability;
- incremental predictive value.

Expand only when the evidence justifies it.

Use the 4×4090 cluster efficiently with batched local inference.

---

# 11. Phase V — Dynamic influence

Construct multiple influence definitions.

## I1 — Capital influence

Examples:
- flow;
- volume;
- net flow;
- value-weighted activity.

## I2 — Activity influence

Examples:
- future activity explained by wallet activity.

## I3 — Network influence

Examples:
- temporal PageRank;
- weighted centrality;
- k-core;
- community bridge score.

## I4 — Temporal lead-lag influence

Measure whether wallet `i` systematically precedes downstream events.

## I5 — Predictive spillover

Let:

```text
Y_future = downstream future behavior
X_i(t) = wallet i state
C_t = context
```

Compare:

```text
P(Y_future | C_t)
```

against

```text
P(Y_future | C_t, X_i(t))
```

Define an incremental predictive score.

## I6 — Information-gain influence

Conceptually:

```text
IG_i(t)
=
H(Y_future | C_t)
-
H(Y_future | C_t, X_i(t))
```

Use only quantities estimated from training/validation data without test leakage.

## I7 — Counterfactual influence

Perturb/remove wallet evidence and measure the change in downstream forecast.

Do not call this causal unless identification assumptions are defensible.

---

# 12. The critical influence experiment

Explicitly construct a 2D analysis:

```text
             High predictive influence
                     ↑
                     |
       low-volume    |    high-volume
       influencers   |    obvious whales
                     |
---------------------+--------------------→ financial size
                     |
       irrelevant    |    high-volume
       small wallets |    noisy actors
                     |
                     ↓
```

Search for:

> **low-capital / low-volume wallets with unusually high predictive downstream spillover.**

These examples can become central motivating case studies.

Also search for:

> **high-volume wallets with surprisingly low predictive spillover.**

These negative examples prevent the paper from becoming a generic "find whales" paper.

---

# 13. Persona × Influence

Build a matrix:

```text
Behavioral Persona × Predictive Influence
```

For each role estimate:

- mean influence;
- median influence;
- tail influence;
- influence stability;
- regime dependence;
- downstream reach;
- reasoning ROI.

Questions:

1. Which behavioral roles are disproportionately influential?
2. Are some roles influential only during high volatility?
3. Are some roles persistent while others are episodic?
4. Does behavioral transition predict future influence?
5. Does community membership alter influence?
6. Can persona + network position predict future influence?

This is potentially much more interesting than a static wallet leaderboard.

---

# 14. Phase VI — Temporal communities

Construct temporal interaction graphs.

At minimum:

```text
wallet ↔ wallet
```

If feasible:

```text
wallet ↔ token
wallet ↔ contract
wallet ↔ protocol
wallet ↔ community
```

Discover communities using appropriate graph methods.

Compare:

1. transaction communities;
2. behavioral communities;
3. hybrid communities.

Track:

```text
Community_k(t)
```

and transitions.

Test whether:

```text
community context
+
wallet state
```

improves future action prediction.

---

# 15. Phase VII — Reasoning-worthiness / ROI

The router should decide:

> Which wallet deserves expensive reasoning?

Define an approximate reasoning ROI:

```text
RROI_i(t)
=
expected prediction improvement
/
additional reasoning cost
```

A practical router can use:

```text
Depth_i(t)
=
π(
  influence_i(t),
  uncertainty_i(t),
  counterfactual_sensitivity_i(t),
  community_importance_i(t),
  budget
)
```

Compare:

### Baseline A
Uniform depth 1.

### Baseline B
Uniform depth 2.

### Baseline C
Uniform maximum depth.

### Baseline D
Random selective reasoning.

### Baseline E
Volume-based routing.

### Baseline F
Centrality-based routing.

### Proposed
Influence + uncertainty + sensitivity + behavioral role routing.

Always compare under **equal or carefully normalized compute budgets**.

---

# 16. Phase VIII — Next-event prediction target

Do not predict only:

```text
next counterparty
```

Use a richer marked temporal event:

```text
P(
  counterparty,
  action,
  token/type,
  Δt
  |
  S_t
)
```

At minimum predict:

1. next counterparty/category;
2. next action type;
3. time-to-next-event.

Possible extension:

```text
P(
  event_{t+1},
  event_{t+2},
  ...,
  event_{t+k}
)
```

This turns the task into a temporal event/trajectory forecasting problem.

---

# 17. Phase IX — Recursive behavioral forecasting

The recursion should be explicit.

Example:

```text
At time t:
Wallet A state
    ↓
predict A's next action
    ↓
infer affected counterparty B
    ↓
construct B's updated state
    ↓
predict B's next response
    ↓
construct C's state
    ↓
...
```

Conceptually:

```text
A_t
→ B_{t+1}
→ C_{t+2}
→ D_{t+3}
→ ...
```

Do NOT merely ask Qwen to produce a long paragraph.

Represent the rollout as structured states.

Each node should include:

```json
{
  "entity": "...",
  "timestamp": "...",
  "predicted_event": "...",
  "candidate_counterparties": [],
  "confidence": 0.0,
  "evidence_ids": [],
  "assumptions": [],
  "uncertainty": 0.0,
  "verification_status": "...",
  "stop_reason": null
}
```

---

# 18. Independent-agent vs shared-state recursion

Run a major ablation.

### Condition A — Independent agents

Each step receives only its own local evidence.

### Condition B — Shared-state agents

Every subsequent agent receives the structured state produced by previous steps.

### Condition C — Shared-state + verified evidence

Subsequent steps receive only verified state transitions.

Compare:

- accuracy;
- calibration;
- error propagation;
- diversity;
- compute;
- hallucination/unsupported reasoning;
- recursive depth.

This is important because "multi-agent" alone is not necessarily useful.

---

# 19. High-order recursion

Do not assume depth 3 is enough.

Evaluate:

```text
depth 1
depth 2
depth 3
depth 4
depth 5
...
```

until:

- performance saturates;
- uncertainty explodes;
- error propagation dominates;
- budget limit reached.

Plot:

```text
performance vs depth
cost vs depth
calibration vs depth
error propagation vs depth
```

The desired scientific result is not necessarily "deeper is always better".

A stronger result could be:

> Optimal depth is conditional on influence, uncertainty, and counterfactual sensitivity.

---

# 20. Step-level trustworthy reasoning

Every recursive step must produce a structured verification record.

Required fields:

```json
{
  "step_id": "...",
  "input_state": "...",
  "evidence_ids": [],
  "evidence_time_valid": true,
  "candidate_prediction": "...",
  "confidence": 0.0,
  "assumptions": [],
  "counterfactual_test": {},
  "verification_score": 0.0,
  "supported": true,
  "abstain": false
}
```

Verification should ask:

1. Is every cited event real?
2. Was it available at prediction time?
3. Does the conclusion actually depend on it?
4. What happens if the evidence is removed?
5. What happens if a conflicting event is inserted?
6. Is the prediction robust to small trajectory perturbations?
7. Is the confidence calibrated?

---

# 21. Counterfactual reasoning

Implement at least:

### Evidence removal

```text
E = {e1,e2,...,en}

predict(Y | E)

remove e_j

predict(Y | E \ e_j)
```

Measure the change.

### Evidence replacement

Replace an important event with a matched alternative.

### Temporal truncation

Remove the latest portion of the context.

### Contradictory intervention

Insert a plausible conflicting observation.

### Counterfactual persona

Remove/alter events and ask whether the inferred behavioral role changes.

The key quantity is sensitivity:

```text
Sensitivity(E_j)
=
D(
 P(Y | E),
 P(Y | E without/altered E_j)
)
```

where `D` may be an appropriate divergence or prediction-change metric.

---

# 22. Evidence provenance

Every reasoning step must point to actual evidence IDs.

Do not allow free-form invented citations.

Build a provenance graph:

```text
evidence
   ↓
reasoning step
   ↓
prediction
   ↓
next state
   ↓
next reasoning step
```

This graph should be exportable.

Potential final figure:

```text
Transaction Evidence
        │
        ▼
 Behavioral State
        │
        ▼
 Prediction ──────┐
        │         │
        ▼         │
 Counterfactual  Verification
        │         │
        └────┬────┘
             ▼
       Updated State
             │
             ▼
        Recursive Step
```

---

# 23. Abstention and stopping

A trustworthy recursive system should be allowed to say:

```text
STOP
```

when:

- uncertainty is too high;
- evidence is insufficient;
- counterfactual sensitivity is extreme;
- candidate branches disagree;
- the predicted entity is too weakly supported;
- the reasoning budget is exhausted.

Compare:

```text
forced prediction
vs
selective prediction + abstention
```

Evaluate risk at coverage:

```text
Risk@50
Risk@70
Risk@80
Risk@90
```

and selective calibration.

---

# 24. Multi-agent branch search

Use multiple DeepSeek/Qwen reasoning roles as a **controlled search procedure**, not as uncontrolled brainstorming.

For a difficult prediction:

```text
               State S_t
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   Predictor A  Predictor B  Predictor C
       │           │           │
       ▼           ▼           ▼
 candidate 1   candidate 2   candidate 3
       └───────────┼───────────┘
                   ▼
             Evidence Auditor
                   │
          ┌────────┴────────┐
          ▼                 ▼
    Counterfactual       Conflict Test
          │                 │
          └────────┬────────┘
                   ▼
              Aggregator
                   │
                   ▼
          accept / abstain
```

Suggested roles inside a hard case:

- trajectory forecaster;
- network forecaster;
- behavioral forecaster;
- market-context forecaster;
- skeptic;
- evidence auditor;
- counterfactual analyst.

Do not count agreement among agents as truth.

**Consensus is a candidate signal, not proof.**

---

# 25. Recursive branch pruning

For each candidate branch estimate:

```text
Expected utility
=
predicted quality gain
-
reasoning cost
-
error propagation risk
```

Continue exploring a branch only if:

```text
expected value of additional reasoning > cost
```

Otherwise stop.

This creates an explicit bridge between:

```text
influence
→ reasoning allocation
→ recursive search
```

---

# 26. Strong baselines

At minimum implement/compare:

### Non-LLM

- majority/most-frequent;
- Markov baseline;
- time-aware frequency model;
- logistic regression;
- gradient boosting;
- random forest where appropriate;
- sequence model;
- temporal graph model if feasible.

### Influence routing

- random;
- volume;
- activity;
- centrality;
- predictive influence;
- proposed adaptive router.

### Reasoning

- no reasoning;
- one-step LLM;
- fixed-depth recursive LLM;
- adaptive recursion;
- adaptive + verification;
- adaptive + counterfactual verification.

### Representation

- handcrafted;
- trajectory;
- Qwen semantic;
- Qwen latent;
- combined.

---

# 27. Evaluation metrics

## Event prediction

- top-1;
- top-k;
- MRR;
- NLL;
- cross-entropy;
- Brier score where applicable.

## Time-to-event

- MAE;
- median absolute error;
- log-time error;
- survival-style metrics if implemented.

## Calibration

- ECE;
- reliability diagrams;
- Brier;
- selective risk.

## Recursive forecasting

- accuracy by depth;
- cumulative error;
- error propagation;
- calibration by depth.

## Trustworthiness

- evidence validity;
- evidence sufficiency;
- counterfactual sensitivity;
- unsupported-step rate;
- abstention quality.

## Efficiency

- tokens;
- inference time;
- GPU time;
- calls;
- energy proxy if available;
- quality per unit compute.

## Influence

- out-of-sample incremental predictive value;
- stability;
- regime dependence;
- downstream reach;
- ranking quality.

---

# 28. Statistical methodology

For every major comparison:

- use walk-forward evaluation;
- use multiple temporal test windows where possible;
- report confidence intervals;
- use paired comparisons on the same prediction cases;
- bootstrap at the appropriate unit;
- avoid treating individual transactions as independent if serial dependence exists;
- distinguish statistical significance from practical significance.

Never select a test period after inspecting its results.

---

# 29. Market-level rollout

Only after wallet-level forecasting is credible.

Pipeline:

```text
wallet forecasts
→ community aggregation
→ predicted transaction flow
→ network-level flow
→ market-level features
→ ETH/crypto market forecast
→ optional strategy simulation
```

Compare:

1. market-only baseline;
2. transaction-only features;
3. wallet prediction features;
4. influence-weighted wallet predictions;
5. verified recursive predictions.

For trading:

- strict chronological backtest;
- transaction costs;
- slippage assumptions;
- no future leakage;
- no look-ahead portfolio construction;
- realistic execution delay.

Trading PnL is a **secondary validation**, not the central research claim.

---

# 30. Social-media context

Use the 52 influencer tweet dataset as external context.

Never imply:

```text
tweet author = wallet owner
```

unless independently verified.

Possible intervention design:

```text
No social context
vs
social context
vs
stale social context
vs
removed relevant tweet
vs
contradictory social context
```

Ask:

> Does external social information improve prediction of behavioral-community responses, and can counterfactual removal identify whether the improvement genuinely depends on the relevant evidence?

This can become a secondary extension.

---

# 31. Literature/prior-art check

Whenever the research story changes materially, update:

```text
research/PRIOR_ART.md
```

Search for work on:

- Ethereum user behavior clustering;
- DeFi behavioral clustering;
- temporal Ethereum graphs;
- wallet/address clustering;
- behavioral communities;
- influence estimation;
- temporal point processes;
- marked event prediction;
- graph forecasting;
- recursive LLM reasoning;
- multi-agent reasoning;
- adaptive reasoning;
- selective prediction;
- evidence verification;
- counterfactual reasoning;
- LLM agents in finance;
- crypto transaction prediction.

The goal is not to claim that nobody has ever done any individual component.

The goal is to identify the **specific composition and scientific gap**.

---

# 32. Experiment registry

Every experiment must create a record like:

```yaml
experiment_id:
date:
git_commit:
hypothesis:
data_version:
train_window:
validation_window:
test_window:
prediction_horizon:
model:
prompt_version:
seed:
compute_budget:
features:
routing_policy:
reasoning_depth:
verification:
counterfactual:
metrics:
result_path:
status:
interpretation:
limitations:
next_action:
```

Status must be one of:

```text
PLANNED
RUNNING
COMPLETED
FAILED
PROVISIONAL
REPLICATED
REJECTED
```

---

# 33. Autonomous decision policy

DeepSeek may autonomously choose the next experiment when:

1. the current result is statistically/empirically clear;
2. the next experiment can distinguish competing hypotheses;
3. compute cost is reasonable;
4. no unresolved leakage issue exists.

Prioritize experiments by:

```text
Priority
=
Expected scientific information gain
×
Probability of changing the paper
/
Compute cost
```

Do not spend the entire night optimizing a model that is already clearly inferior.

---

# 34. What should run overnight

Use the following priority order.

## Tier 0 — Must finish

1. repository/data audit;
2. temporal leakage audit;
3. temporal wallet states;
4. strong simple influence baselines;
5. volume vs predictive influence comparison;
6. low-volume/high-influence discovery;
7. baseline event forecasting.

## Tier 1 — High scientific value

8. dynamic behavioral clustering;
9. persona transitions;
10. temporal communities;
11. Qwen behavioral representation;
12. persona × influence;
13. influence-aware reasoning routing.

## Tier 2 — Core reasoning contribution

14. one-step Qwen prediction;
15. two-step recursion;
16. 3–5 step recursion;
17. shared-state recursion;
18. evidence provenance;
19. counterfactual verification;
20. abstention;
21. adaptive depth.

## Tier 3 — High-risk/high-reward

22. multi-agent branch search;
23. recursive branch pruning;
24. community-aware recursion;
25. social-context interventions;
26. micro→meso→macro rollout.

## Tier 4 — Secondary

27. trading backtest;
28. broader hyperparameter sweeps;
29. large-scale Qwen expansion.

If the run is time-limited, stop after Tier 2 rather than producing shallow Tier 4 results.

---

# 35. Compute allocation

Available:

```text
4 × RTX 4090
Qwen3.5-4B local
DeepSeek V4 Pro Max orchestrator
~1B token total budget
```

Suggested initial allocation:

```text
10% data/audit
15% cheap behavioral/influence experiments
15% Qwen representation
25% recursive reasoning
15% verification/counterfactual
10% ablations
5% market/social extensions
5% reserve
```

These percentages are guidelines, not hard quotas.

If an early result invalidates the main hypothesis, redirect compute immediately.

---

# 36. Parallelism policy

Run independent workloads concurrently.

Examples:

### Parallel group 1

```text
Influence scientist
Behavior scientist
Baseline scientist
Literature scientist
```

### Parallel group 2

After shared state artifacts exist:

```text
Qwen semantic representation
Qwen latent representation
Numerical representation
Community detection
```

### Parallel group 3

After a stable one-step predictor exists:

```text
Recursive architect
Trust auditor
Counterfactual scientist
Multi-agent branch scientist
```

### Parallel group 4

After core results:

```text
Evaluation/statistics
Skeptical reviewer
Market rollout
Figure generation
```

Do not parallelize dependent experiments prematurely.

---

# 37. Reproducibility rules for local Qwen

Record:

- exact model checkpoint;
- quantization;
- context length;
- decoding parameters;
- temperature;
- top-p;
- seed if supported;
- GPU allocation;
- batch size;
- prompt version;
- input state hash.

For stochastic outputs, run repeated samples on a representative subset.

Measure behavioral-profile stability.

---

# 38. LLM reliability tests

For a representative sample:

### Prompt stability

Use several semantically equivalent prompts.

### Sampling stability

Run multiple stochastic samples.

### Evidence perturbation

Remove selected events.

### Temporal truncation

Remove the latest context.

### Contradiction

Insert a conflicting event.

### Representation stability

Compare embeddings across nearby cutoffs.

A useful result is not simply "Qwen works".

A stronger result is:

> Qwen-derived representations are useful when stable under temporal and evidence perturbations.

---

# 39. Important anti-circularity checks

Be especially careful with influence.

Do NOT define influence as:

```text
wallet is important because the router chose it
```

and then claim:

```text
router improves because it chose influential wallets.
```

Influence must be computed independently or through a properly nested training procedure.

Likewise, do not use test-set future outcomes to define the influential-wallet list before testing the reasoning model.

If selecting top-K influential wallets:

```text
train influence on past
→ select candidates
→ freeze selection
→ evaluate future
```

For rolling deployment:

```text
past window
→ estimate influence
→ route next window
→ update
→ repeat
```

---

# 40. Nested temporal evaluation for the full system

The strongest evaluation should simulate deployment.

At each time `t`:

```text
Historical data ≤ t
       ↓
Estimate personas
       ↓
Estimate communities
       ↓
Estimate influence
       ↓
Select wallets
       ↓
Allocate reasoning budget
       ↓
Predict future
       ↓
Verify / abstain
       ↓
Observe actual future
       ↓
Update
```

Never let future test information enter earlier stages.

This is the gold-standard evaluation.

---

# 41. Final paper-level figures to produce

At minimum:

### Figure 1 — System overview

```text
Blockchain events
→ behavioral identity
→ influence
→ adaptive reasoning
→ verified recursive rollout
→ market/community outcomes
```

### Figure 2 — Influence landscape

Volume vs predictive influence, highlighting unusual quadrants.

### Figure 3 — Dynamic persona map

Wallet behavioral roles over time.

### Figure 4 — Persona × influence

Heatmap or distribution.

### Figure 5 — Reasoning-depth curve

Performance vs depth and compute.

### Figure 6 — Adaptive routing

Quality-cost frontier.

### Figure 7 — Recursive provenance

Evidence → step → counterfactual → updated state.

### Figure 8 — Counterfactual reliability

Performance/unsupported reasoning before and after verification.

### Figure 9 — Micro→meso→macro rollout

Wallet → community → aggregate market.

---

# 42. Final tables

### Table 1
Dataset and temporal split.

### Table 2
Wallet behavioral representation comparison.

### Table 3
Influence definition comparison.

### Table 4
Wallet-selection/routing baselines.

### Table 5
Recursive depth comparison.

### Table 6
Trustworthy verification ablations.

### Table 7
Equal-budget comparison.

### Table 8
Market-level downstream validation.

---

# 43. Stop conditions

Stop an experiment branch when:

- leakage cannot be resolved;
- a method is clearly dominated after replication;
- additional tuning changes no conclusion;
- compute cost is disproportionate;
- the experiment no longer distinguishes a meaningful hypothesis.

Do NOT stop because a result is inconvenient.

---

# 44. What counts as a strong result

A particularly strong final story would look like:

1. Static financial size poorly identifies predictive influence.
2. Dynamic behavioral identity explains meaningful heterogeneity.
3. Predictive influence is regime- and role-dependent.
4. Influence-aware selection finds a small subset of wallets worth expensive reasoning.
5. Qwen representations add useful behavioral information beyond simple numerical features.
6. Recursive forecasting improves multi-step event prediction.
7. Uncontrolled recursion suffers from error propagation.
8. Counterfactual step-level verification reduces unsupported recursive steps.
9. Adaptive depth achieves a better quality/compute frontier.
10. Community-aware rollout improves meso-level prediction.
11. Optional market-level signals provide independent downstream validation.

But **do not force this story**. The actual evidence determines the final narrative.

---

# 45. If the strongest hypothesis fails

Examples:

### If Qwen adds no value
Position the contribution around dynamic influence + adaptive trustworthy reasoning.

### If influence does not help routing
Investigate whether uncertainty alone or counterfactual sensitivity is better.

### If recursive reasoning does not beat a strong sequence model
Do not hide it. Investigate whether recursion is redundant and pivot toward trustworthy selective reasoning.

### If deeper reasoning hurts
That itself can motivate adaptive stopping.

### If behavioral personas are unstable
Study instability as a signal of regime change rather than pretending personas are permanent.

### If social data adds little
Keep it as an intervention/negative-control analysis.

---

# 46. Overnight execution loop

Run continuously until budget/time exhaustion:

```text
1. Inspect current state.
2. Identify highest-value unresolved question.
3. Propose experiment.
4. Audit temporal validity.
5. Implement minimal reproducible version.
6. Run.
7. Save raw results.
8. Analyze.
9. Have skeptical role review.
10. Replicate important findings.
11. Update hypotheses.
12. Choose next experiment.
```

At every major stage, write a short decision memo:

```text
What we believed
What we tested
What happened
What changed
What remains uncertain
What to do next
```

---

# 47. Final deliverables

By the end of the autonomous run, produce as much of the following as the evidence supports:

```text
research/
├── README.md
├── HYPOTHESES.md
├── PI_DECISIONS.md
├── PRIOR_ART.md
├── EXPERIMENT_REGISTRY.md
├── audit/
│   ├── DATA_AUDIT.md
│   ├── LEAKAGE_AUDIT.md
│   ├── TEMPORAL_SPLITS.md
│   └── FEATURE_LINEAGE.csv
├── influence/
│   ├── influence_definitions.md
│   ├── influence_results.csv
│   ├── influence_stability.csv
│   └── persona_influence_analysis.md
├── behavior/
│   ├── persona_results.csv
│   ├── persona_transitions.csv
│   └── community_results.csv
├── qwen/
│   ├── prompts/
│   ├── profiles/
│   ├── embeddings/
│   └── reliability.md
├── recursion/
│   ├── rollout_schema.json
│   ├── recursive_results.csv
│   └── depth_analysis.csv
├── trust/
│   ├── provenance_schema.json
│   ├── counterfactual_results.csv
│   ├── verification_results.csv
│   └── abstention_results.csv
├── evaluation/
│   ├── main_results.csv
│   ├── confidence_intervals.csv
│   └── statistical_tests.md
├── baselines/
├── market/
└── figures/
```

Also update the root README with:

- research question;
- data limitations;
- reproducibility instructions;
- strongest validated findings;
- known negative results;
- next steps.

---

# 48. Final synthesis memo

At the end, produce:

```text
research/FINAL_SYNTHESIS.md
```

It must contain:

## A. Executive conclusion

What is actually supported?

## B. Strongest novelty claim

One precise sentence.

## C. Main evidence

Only replicated results.

## D. Key negative results

What did not work?

## E. Best model/system

Exact configuration.

## F. Compute-quality frontier

How much extra compute buys how much improvement?

## G. Most convincing case studies

Especially low-volume/high-influence and recursive cases.

## H. Ablation conclusions

Which components actually matter?

## I. Threats to validity

Be brutally honest.

## J. NAACL-level paper outline

Suggested structure:

1. Introduction
2. Problem formulation
3. Dynamic behavioral identity
4. Predictive influence
5. Adaptive recursive reasoning
6. Step-level trustworthy verification
7. Experimental setup
8. Results
9. Ablations and analysis
10. Limitations
11. Related work
12. Conclusion

## K. Next experiments

Rank by expected scientific value.

---

# 49. Final instruction to the autonomous DeepSeek research team

You are not being asked to "write a lot of code."

You are being asked to **conduct an autonomous scientific investigation**.

Behave simultaneously as:

- a principal investigator;
- a quantitative researcher;
- a machine-learning engineer;
- an NLP/LLM researcher;
- a graph-learning researcher;
- a statistical auditor;
- an adversarial peer reviewer.

Use parallel specialist roles whenever they reduce duplicated work.

Challenge your own assumptions.

Prefer experiments that can falsify the central hypothesis.

Do not confuse a visually compelling figure with evidence.

Do not confuse agent consensus with correctness.

Do not confuse predictive influence with causality.

Do not confuse behavioral clustering with identity.

Do not confuse a profitable backtest with a scientific contribution.

The highest-priority objective is to discover whether the following claim survives rigorous temporal evaluation:

> **In a decentralized transaction network, dynamic behavioral identity and predictive downstream influence can identify where expensive reasoning is worth spending, and adaptive counterfactual step-verified recursive reasoning can improve multi-step behavioral forecasting under a fixed reasoning budget.**

If it survives, build the strongest evidence chain possible.

If it fails, find out **why**, preserve the negative result, and pivot to the strongest scientifically defensible hypothesis.

**Do not wait for human approval between ordinary experiments.**
Only stop for genuinely destructive actions, irreversible data operations, missing credentials, or decisions that would materially change the project's scope.

The goal by morning is not "more code."

The goal is a **reproducible, audited, evidence-backed research result with a credible path to a top NLP/ML conference submission.**
