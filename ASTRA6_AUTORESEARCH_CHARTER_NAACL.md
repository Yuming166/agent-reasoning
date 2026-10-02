# Astra6-Only Autoresearch Charter for NAACL-Oriented On-Chain Behavioral Inference

## 0. Purpose

This document defines the operating rules for an autonomous research system whose goal is to discover, test, refine, and, when necessary, reject candidate research directions for a NAACL-level NLP paper built around on-chain behavioral traces.

The system must not optimize for experiment count, positive results, or autonomous activity itself. Its goal is to identify the strongest **novel, falsifiable, NLP-central, empirically defensible, replication-ready scientific claim** that can be supported by the available data.

The current high-level research space concerns:

- natural-language behavioral hypotheses inferred from on-chain action traces;
- evidence-grounded but potentially invalid behavioral interpretations;
- competing behavioral explanations;
- behavioral equifinality and identifiability;
- prospective falsification of natural-language hypotheses;
- hypothesis revision from new on-chain observations;
- reliability estimation and selective inference.

The system must remain willing to conclude that a proposed direction is unsupported.

---

# 1. Absolute Model Routing Rule

## 1.1 Astra6 is the only cognitive model

All research cognition must be performed through the user's private Astra6 relay.

This includes:

- literature reasoning;
- novelty analysis;
- hypothesis generation;
- task formulation;
- experiment design;
- interpretation of results;
- scientific critique;
- reviewer simulation;
- branch synthesis;
- paper-story construction;
- scientific writing and rewriting.

The system must **never** use the server-side Codex built-in LunaMax, any Codex reasoning model, or any local/fallback LLM for scientific cognition.

## 1.2 Fail-closed behavior

Use configuration equivalent to:

```bash
ASTRA_ONLY=1
ASTRA_ALLOW_FALLBACK=0
CODEX_LLM_DISABLED=1
LUNAMAX_DISABLED=1
```

If Astra6 becomes unavailable:

- pause the cognitive queue;
- preserve all current state;
- do not switch model providers;
- do not silently degrade to another model.

## 1.3 Local/server processes may only execute deterministic work

The server may perform:

- Python execution;
- SQL queries;
- shell commands;
- deterministic statistics;
- data preprocessing;
- model training/inference explicitly selected by Astra6;
- plotting;
- file operations;
- git operations;
- experiment scheduling.

The local/server executor must not substitute its own reasoning for Astra6.

## 1.4 Log every Astra6 call

Record at minimum:

- timestamp;
- agent role;
- branch ID;
- experiment ID if applicable;
- model identifier;
- prompt hash;
- response hash;
- token count if available;
- parent task ID;
- result path.

---

# 2. Research Objective

The system should optimize for:

\[
\text{Research Value}
=
f(
\text{Novelty},
\text{Empirical Strength},
\text{NLP Centrality},
\text{Falsifiability},
\text{Replication},
\text{Reviewer Robustness}
)
\]

It must not optimize for a single benchmark metric.

The main meta-question is:

> **What is the strongest empirically defensible NLP research question about inferring, contrasting, validating, and revising natural-language behavioral hypotheses from on-chain action traces?**

The system must not assume in advance that:

- behavioral equifinality exists;
- belief inference is possible;
- identifiability is the correct explanation;
- LLM-based semantic states are useful;
- selective inference will work;
- a method paper is preferable to a phenomenon/task paper.

---

# 3. Immutable Research Constitution

Create and maintain:

```text
research_os/
├── CONSTITUTION.md
├── DATA_CONTRACT.md
├── CLAIM_LEDGER.yaml
├── EXPERIMENT_REGISTRY.yaml
├── LITERATURE_LEDGER.jsonl
├── NEGATIVE_RESULTS.md
├── branches/
├── runtime/
└── synthesis/
```

## 3.1 Files

### `CONSTITUTION.md`

Contains non-negotiable scientific rules.

Only the human PI may modify it.

### `DATA_CONTRACT.md`

Defines:

- allowed data sources;
- temporal cutoffs;
- leakage rules;
- train/dev/test partitions;
- frozen holdouts;
- identity limitations;
- address-level interpretation constraints;
- future-outcome access rules.

Only the human PI may modify it.

### `CLAIM_LEDGER.yaml`

Tracks every scientific claim and its evidence status.

### `EXPERIMENT_REGISTRY.yaml`

Tracks preregistered, running, completed, frozen, failed, and superseded experiments.

### `LITERATURE_LEDGER.jsonl`

Stores prior work, exact overlap, novelty threats, and unresolved literature questions.

### `NEGATIVE_RESULTS.md`

Append-only scientific memory.

No agent may delete or rewrite prior negative findings.

---

# 4. Mandatory Prior Knowledge

Before proposing a new branch, every Astra6 research agent must read the relevant prior findings.

The following results are part of the immutable project history.

## 4.1 Established positive findings

- Recent behavioral dynamics contain predictive information beyond basic activity/scale features.
- Phase-I wallet/event selection has a limited positive result.
- Some selective reasoning allocation settings outperform random selection.
- On-chain history contains usable predictive signal.

## 4.2 Established negative or limiting findings

- Independent graph-structural signal did not pass the preregistered incremental gate.
- Decision-State V1 failed future behavioral effectiveness.
- Intervention responsiveness did not translate into predictive utility.
- Intervention-verified semantic hypotheses did not improve over the recent-dynamics baseline.
- Response-geometry features were redundant with existing features.
- Qwen ICVA did not establish a reliability improvement.
- Market-native intervention signals did not produce the desired gain.
- The prior anomaly/open-world branch was underpowered or unsupported.
- No owner-identity or true-psychology claim is justified.
- No reliable address-to-social-account exposure assumption is available.
- Frozen test data may not be retuned.
- Five-dimensional wallet importance is historical/baseline work, not presumed core novelty.

## 4.3 Interpretation rule

Agents must not reinterpret a prior NO-GO as a positive result merely by renaming the construct.

Any revival requires:

1. a genuinely new scientific question;
2. a new source of identifying information or a new evaluation target;
3. an explicit Astra6 falsifier analysis explaining why the old failure no longer addresses the new claim.

---

# 5. Research Tree

Research proceeds as a branching scientific search process.

Each branch must be represented as:

```yaml
branch_id:
question:
proposition:
novelty_gap:
nlp_centrality:
falsifier:
required_controls:
cheapest_decisive_experiment:
evidence_for:
evidence_against:
reviewer_risks:
status:
budget_tier:
parent_branch:
```

Allowed branch states:

```text
PROPOSED
LIT_AUDIT
PROBE
DISCOVERY_SUPPORTED
FROZEN
REPLICATION
SUPPORTED
MODIFY
HOLD
KILLED
```

A branch must never move directly from `PROPOSED` to `REPLICATION`.

---

# 6. Initial Competing Research Branches

Initialize the system with the following high-level branches.

## Branch A — Evidence–Validity Gap

### Question

When do evidence-responsive behavioral interpretations fail to have prospective behavioral validity?

### Core proposition

\[
\text{Evidence Sensitivity}
\not\Rightarrow
\text{Future Validity}
\]

### Immediate goal

Determine whether the aggregate Decision-State V1 failure also appears at the case level.

---

## Branch B — Behavioral Equifinality

### Question

Does the same on-chain action history systematically support multiple incompatible but evidence-grounded behavioral explanations?

### Core proposition

\[
X_{\le t}
\rightarrow
\{H_1,H_2,\dots,H_K\}
\]

where multiple hypotheses are:

- evidence-consistent;
- semantically non-redundant;
- mutually competing;
- prospectively distinguishable.

---

## Branch C — Falsifiable Behavioral Hypothesis Induction

### Question

Can on-chain action traces support natural-language behavioral hypotheses with explicit evidence, future implications, and falsifiers?

Represent each hypothesis as:

\[
h_k = (C_k,E_k,P_k,F_k)
\]

where:

- \(C_k\): claim;
- \(E_k\): supporting evidence;
- \(P_k\): future implication;
- \(F_k\): falsification condition.

---

## Branch D — Behavioral Hypothesis Revision

### Question

Can new on-chain actions induce coherent and prospectively valid updates over a natural-language hypothesis space?

Study:

\[
q_t(H)
\xrightarrow{e_{t+1}}
q_{t+1}(H)
\]

The goal is not merely state prediction, but whether new evidence induces appropriate hypothesis revision.

---

## Branch E — Predictability × Interpretability

### Question

When is future behavior directly predictable while latent semantic interpretation remains non-identifiable?

Study the 2×2 space:

| | Low Identifiability | High Identifiability |
|---|---:|---:|
| High Predictability | predictable but uninterpretable | reliable inference |
| Low Predictability | fundamentally uncertain | interpretable now, unstable future |

---

## Branch F — Identifiability-Aware Selective Inference

### Question

Can pre-outcome signals estimate whether a behavioral interpretation will survive future falsification better than:

- LLM confidence;
- entropy;
- intervention sensitivity;
- ordinary predictive uncertainty?

This branch should only receive major compute after earlier phenomenon branches are supported.

---

# 7. Astra6 Agent Roles

Agents are separated by cognitive function rather than fictional personas.

## `LIT_SCOUT`

Responsibilities:

- retrieve nearest prior work;
- identify task overlap;
- identify method overlap;
- identify terminology overlap;
- collect exact novelty threats.

Restrictions:

- must not propose new methods;
- must not advocate for the current idea.

## `GAP_AUDITOR`

Responsibilities:

- attack novelty;
- search for prior work that collapses the claimed gap;
- determine whether the contribution is truly NLP-central.

Key question:

> If this contribution were applied to another domain or if natural language were removed, what remains?

## `PHENOMENON_SCOUT`

Responsibilities:

- inspect frozen results;
- identify reproducible empirical patterns;
- propose descriptive phenomena only after evidence exists.

Restriction:

- must not invent mechanisms before documenting the phenomenon.

## `FORMULATOR`

Responsibilities:

- convert empirical patterns into falsifiable scientific propositions;
- define null hypotheses;
- define measurable variables;
- specify what result would refute the proposition.

## `NLP_ARCHITECT`

Responsibilities:

- ensure natural language is a core research object;
- define hypothesis representation;
- define semantic incompatibility;
- define evidence-to-claim relations;
- define future implications and falsifiers;
- define revision operators.

Must reject directions where language is merely a presentation layer.

## `EXPERIMENT_DESIGNER`

Responsibilities:

- design the cheapest decisive experiment;
- define controls before results are visible;
- specify sample size and stopping rules;
- define primary outcome;
- define preregistered thresholds.

## `ADVOCATE`

Responsibilities:

- build the strongest possible argument for a branch;
- identify the strongest supporting evidence;
- propose the strongest interpretation that remains scientifically justified.

## `FALSIFIER`

Responsibilities:

- assume the branch is wrong;
- construct simpler alternative explanations;
- identify confounds;
- design experiments that can kill the branch.

The falsifier must never be asked to “improve” the branch.

## `RESULT_ANALYST`

Responsibilities:

- analyze frozen outputs;
- estimate effect sizes;
- compute uncertainty;
- characterize failures;
- compare against preregistered controls.

Restrictions:

- may not modify the protocol after seeing results;
- may not redefine the primary outcome.

## `REVIEWER_NLP`

Attacks:

- novelty;
- NLP centrality;
- task legitimacy;
- relation to NLI, abductive reasoning, belief tracking, hypothesis generation, ToM, selective prediction.

## `REVIEWER_METHOD`

Attacks:

- leakage;
- significance;
- invalid controls;
- post-hoc tuning;
- calibration;
- multiple testing;
- evaluation mismatch;
- overclaiming.

## `REVIEWER_DOMAIN`

Attacks:

- blockchain assumptions;
- wallet/address interpretation;
- automation/service-wallet confounds;
- asset/protocol semantics;
- transaction identity;
- market-structure explanations.

## `META_REVIEWER`

Receives independent reviews and outputs exactly one:

```text
KEEP
MODIFY
HOLD
KILL
```

with explicit reasons.

No numerical paper score is required.

## `RESEARCH_MANAGER`

Responsibilities:

- enforce the Constitution;
- schedule agents;
- allocate branch budgets;
- maintain branch states;
- choose the next highest-information experiment;
- synthesize the current strongest paper story;
- prevent branch resurrection;
- prevent test-set leakage;
- terminate weak directions.

---

# 8. Independence Rule

For important scientific questions, use independent Astra6 agents before synthesis.

Example:

Three Astra6 agents independently answer:

> What is the strongest explanation for Decision-State V1 failure?

They must not see one another's outputs.

Possible independent hypotheses may include:

- semantic bottleneck;
- behavioral equifinality;
- target mismatch;
- calibration degradation;
- narrative regularization;
- address-level non-identifiability.

A separate synthesis agent receives all independent reports only after completion.

Multi-agent agreement is not scientific evidence.

---

# 9. Adversarial Pairing

Every active branch must have:

\[
\text{ADVOCATE(branch)}
\quad\text{vs}\quad
\text{FALSIFIER(branch)}
\]

The system must not decide between them by textual voting.

Instead, the `RESEARCH_MANAGER` asks:

> What is the cheapest experiment that would distinguish the two explanations?

The experiment, not the rhetoric, determines branch survival.

---

# 10. Progressive Research Budget

Every branch receives progressively increasing resources.

## Tier 0 — Literature and logic only

No large experiment.

Required outputs:

- novelty audit;
- NLP-centrality audit;
- falsifier memo;
- cheapest decisive experiment.

## Tier 1 — Feasibility probe

Typical scale:

- 100–300 examples;
- small number of Astra6 calls;
- no frozen test set.

Goal:

- determine whether the object being studied even exists.

## Tier 2 — Discovery experiment

Typical scale:

- 500–1000 examples;
- full controls;
- discovery-only evaluation.

Goal:

- estimate effect magnitude;
- identify failure modes.

## Tier 3 — Freeze

Before confirmatory testing:

- freeze prompts;
- freeze sample definition;
- freeze metrics;
- freeze statistical tests;
- freeze GO/NO-GO thresholds.

## Tier 4 — Untouched replication

Run on data not used for design.

No protocol changes allowed.

## Tier 5 — Scaling and robustness

Only after replication:

- cross-model tests;
- cross-time tests;
- ablations;
- additional datasets;
- robustness;
- detailed error analysis.

A branch may not skip tiers.

---

# 11. NLP-Centrality Gate

Before a branch receives expensive compute, independently ask:

> **If all natural-language objects were replaced by arbitrary class IDs, would the scientific contribution remain essentially unchanged?**

If yes:

```text
NOT_NLP_CENTRAL
```

and the branch cannot be the primary NAACL story.

Desired NLP objects include:

- natural-language behavioral hypotheses;
- semantic incompatibility;
- entailment/contradiction among explanations;
- evidence-to-claim alignment;
- explicit future implications;
- falsification conditions;
- hypothesis revision;
- semantic multiplicity;
- language-structured uncertainty.

Natural language must be part of the research object, not merely a reporting interface.

---

# 12. Claim Ledger

Every scientific claim must exist in `CLAIM_LEDGER.yaml`.

Example:

```yaml
claim_id: C017
claim: >
  Higher interpretation multiplicity predicts lower
  prospective hypothesis validity.

status: UNTESTED

branch: B

evidence_for: []
evidence_against: []

allowed_language:
  - "we hypothesize"
  - "we test whether"

forbidden_language:
  - "we show"
  - "we demonstrate"

required_controls:
  - llm_confidence
  - intervention_sensitivity
  - predictive_uncertainty
  - wallet_activity
  - history_length

promotion_gate:
  discovery_replication: required
  untouched_holdout: required
  confidence_interval_excludes_null: required
```

Allowed claim states:

```text
UNTESTED
DISCOVERY_SUPPORTED
REPLICATION_PENDING
SUPPORTED
MIXED
REJECTED
```

Writing agents must obey the claim state.

---

# 13. Experiment Freeze Protocol

Before any confirmatory experiment, record:

```yaml
experiment_id:
branch_id:
hypothesis:
primary_outcome:
secondary_outcomes:
sample_definition:
cutoff_dates:
controls:
model_versions:
prompt_version:
statistical_test:
confidence_interval:
go_threshold:
no_go_threshold:
stop_conditions:
protocol_hash:
```

After the protocol is frozen:

- the experiment definition cannot be edited;
- changes require a new experiment ID;
- failed confirmatory runs remain permanently logged;
- failed results cannot be relabeled as exploratory success.

---

# 14. Initial Priority Experiment

Do not begin by training a new model.

Use existing frozen Decision-State V1 material as a **discovery-only phenomenon audit**.

For each case \(i\), compute:

\[
F_i
=
\text{predefined intervention/evidence sensitivity}
\]

and

\[
\Delta_i
=
\ell(B4_i,Y_i)
-
\ell(B0_i,Y_i)
\]

where:

- \(B0\) is the recent-dynamics baseline;
- \(B4\) is the intervention-verified semantic interpretation model.

Analyze:

1. \(F_i\) vs \(-\Delta_i\);
2. future validity by \(F_i\) quintile;
3. high-faithfulness failure cases;
4. low-faithfulness success cases;
5. calibration;
6. relationship after controlling for:
   - history length;
   - wallet activity;
   - event family;
   - repeat/unseen wallet;
   - confidence;
   - abstention;
   - hypothesis entropy.

## Decision

If no meaningful case-level Evidence–Validity Gap exists:

- downgrade Branch A;
- do not force an identifiability story;
- revisit the paper question.

If a gap exists:

launch targeted probes of competing mechanisms:

- behavioral equifinality;
- semantic bottleneck;
- future-target mismatch;
- ordinary predictive uncertainty;
- automation/service-like behavior;
- insufficient historical evidence.

This first analysis is discovery only and cannot be used as final confirmatory evidence.

---

# 15. Behavioral Equifinality Probe

If Branch B survives literature and logic audit, test whether the same observation supports multiple genuinely competing hypotheses.

For each on-chain episode \(X_i\):

generate:

\[
\mathcal H_i
=
\{h_{i1},\dots,h_{iK}\}
\]

Each hypothesis must satisfy:

## Evidence compatibility

\[
E(X_i,h_{ik})>\tau_E
\]

## Semantic non-redundancy

Hypotheses cannot be paraphrases.

Use independent semantic/NLI checks.

## Mutual competition

At least two hypotheses must make different future commitments.

For example:

\[
H_1:
\text{persistent de-risking}
\]

predicts sustained reduction in risky exposure.

\[
H_2:
\text{temporary liquidity preparation}
\]

predicts subsequent redeployment into risky assets.

The branch only survives if competing hypotheses are common enough to constitute a systematic phenomenon.

---

# 16. Falsifiable Behavioral Hypothesis Representation

If Branch C is active, represent each natural-language behavioral hypothesis as:

```yaml
claim:
supporting_evidence:
alternative_explanations:
future_implications:
falsification_conditions:
confidence:
```

The system should not output unsupported psychological statements such as:

```text
"The wallet owner believes ETH will fall."
```

Prefer operational formulations such as:

```text
"The observed behavior is consistent with persistent reduction
of risky-asset exposure."
```

or:

```text
"The behavior is consistent with temporary liquidity preparation
followed by renewed risky-asset acquisition."
```

The task is about **behaviorally implied hypotheses**, not hidden human psychology.

---

# 17. Prospective Resolution

Future behavior is used as a validation signal, not as input.

At cutoff \(t\):

\[
X_{\le t}
\rightarrow
\mathcal H_t
\]

Freeze the hypothesis set.

Only afterward reveal:

\[
X_{t:t+\Delta}
\]

Resolve each hypothesis as:

```text
SUPPORTED
UNRESOLVED
FALSIFIED
```

The exact rule must be specified before future data is accessed.

The main scientific question becomes:

> Can a natural-language behavioral interpretation formed from current action traces survive prospective behavioral falsification?

---

# 18. Identifiability and Reliability

Only after Branches A–C show support should the system invest heavily in identifiability-aware prediction.

Candidate signals may include:

- number of competing hypotheses;
- semantic distance between hypotheses;
- hypothesis entropy;
- intervention stability;
- evidence overlap;
- evidence exclusivity;
- disagreement over future implications;
- temporal consistency;
- observable predictive uncertainty.

Compare against:

- LLM confidence;
- raw entropy;
- intervention sensitivity;
- non-semantic predictive uncertainty;
- random abstention.

Evaluate:

- AUROC;
- AUPRC;
- calibration;
- risk–coverage;
- selective validity.

A strong result would be:

\[
\text{Identifiability Signal}
>
\text{Confidence / Faithfulness / Ordinary Uncertainty}
\]

on untouched replication data.

---

# 19. Branch Kill Conditions

KILL or HOLD a branch when any of the following occurs:

- novelty collapses to applying an existing method to Ethereum;
- NLP is cosmetic;
- the core phenomenon fails on discovery data;
- the result exists only after post-hoc subgroup search;
- the claim requires owner identity;
- the claim requires unobserved psychological truth;
- the claim requires assuming a wallet saw external text;
- graph effects collapse into activity/volume proxies;
- frozen test data would need to be retuned;
- three preregistered decisive probes fail;
- future behavior cannot operationally falsify the hypothesis;
- a simpler explanation cannot be distinguished using available data;
- the branch requires redefining the target after seeing results.

Negative findings must be appended to `NEGATIVE_RESULTS.md`.

---

# 20. Literature Workflow

Literature review is continuous.

The `LIT_SCOUT` and `GAP_AUDITOR` maintain a novelty matrix.

Example:

| Dimension | Existing Work | Candidate Contribution |
|---|---|---|
| Input | text / transaction / graph | real longitudinal on-chain action traces |
| Target | intent/class label | competing NL behavioral hypotheses |
| Ground truth | annotation/synthetic label | prospective behavioral falsification |
| Uncertainty | confidence | semantic multiplicity / identifiability |
| Intervention | limited | controlled evidence intervention |
| Revision | often static | temporal hypothesis revision |
| Output | single answer | competing falsifiable hypothesis set |

A branch is weakened if its novelty reduces to:

> “We apply an existing method to Ethereum.”

---

# 21. Nightly Decision Memo

At the end of each major autonomous cycle, output:

```text
NIGHTLY RESEARCH DECISION — YYYY-MM-DD

ACTIVE BRANCHES

[Branch ID]
Status:
Strongest supporting evidence:
Strongest contradicting evidence:
Main uncertainty:
Next decisive experiment:

KILLED / HELD BRANCHES

[Branch ID]
Reason:

CURRENT BEST PAPER STORY

Research question:
Observed phenomenon:
Mechanism hypothesis:
NLP contribution:
Method contribution, if any:

MAIN REVIEWER THREATS

1.
2.
3.

CLAIMS PROMOTED

CLAIMS DEMOTED

NEXT HIGHEST-INFORMATION EXPERIMENT
```

Do not report progress primarily as:

- number of experiments;
- number of Astra calls;
- number of files changed.

The main output is always a scientific decision.

---

# 22. Review Tournament

At major milestones, invoke three independent Astra6 reviewers.

## Reviewer A — NLP

Must answer:

1. What is the strongest reason to reject?
2. Is NLP central or cosmetic?
3. What prior work most threatens novelty?
4. Is the task definition legitimate?
5. Could the language layer be replaced by class IDs?

## Reviewer B — Methodology

Must answer:

1. What is the strongest reason to reject?
2. Is there leakage?
3. Are controls sufficient?
4. Are claims stronger than the statistics?
5. What experiment would collapse the story if negative?

## Reviewer C — Domain

Must answer:

1. What is the strongest blockchain-specific confound?
2. Are wallet-level semantic claims justified?
3. Could automation/service behavior explain the result?
4. Are transaction semantics represented correctly?
5. Is a supposedly semantic effect actually activity/volume?

A separate Astra6 meta-reviewer outputs:

```text
KEEP
MODIFY
HOLD
KILL
```

with justification.

---

# 23. Concurrency Policy

Recommended initial configuration:

```yaml
astra_workers: 6

allocation:
  literature: 1
  hypothesis_or_phenomenon: 2
  skeptic_or_falsifier: 1
  experiment_design: 1
  reviewer_synthesis: 1

max_live_branches: 4
max_branch_depth: 5
max_failed_decisive_probes_per_branch: 3
max_automatic_debug_attempts: 2
```

The goal of concurrency is epistemic diversity.

Do not increase the number of agents merely to produce more text.

---

# 24. Background Runtime

Implement a persistent orchestrator:

```text
researchd
├── scheduler
├── queue
├── astra_workers
├── experiment_workers
├── gpu_allocator
├── sql_worker
├── result_collector
└── watchdog
```

Requirements:

- all state persisted to disk;
- resumable after process failure;
- branch-level locking;
- deterministic experiment manifests;
- explicit GPU allocation;
- no repeated Astra call after restart unless previous call was incomplete;
- git commit or snapshot for every frozen experiment.

Suitable runtime options include:

- `systemd`;
- Docker supervisor;
- `tmux` for early development only.

---

# 25. Scientific Memory

The system must prevent repeated rediscovery of failed ideas.

Before proposing any experiment, an agent must query:

1. `NEGATIVE_RESULTS.md`
2. `CLAIM_LEDGER.yaml`
3. `EXPERIMENT_REGISTRY.yaml`
4. relevant branch verdicts
5. literature novelty threats

If a proposal substantially matches an old failed experiment, the system must return:

```text
DUPLICATE_OR_PREVIOUSLY_REJECTED
```

unless the proposing agent provides a specific scientifically meaningful difference.

---

# 26. Preferred Research Trajectory

If supported by evidence, the ideal progression is:

\[
\text{Evidence–Validity Gap}
\]

\[
\downarrow
\]

\[
\text{Competing / Equifinal Behavioral Interpretations}
\]

\[
\downarrow
\]

\[
\text{Natural-Language Falsifiable Hypothesis Representation}
\]

\[
\downarrow
\]

\[
\text{Prospective Hypothesis Resolution}
\]

\[
\downarrow
\]

\[
\text{Identifiability / Reliability Forecasting}
\]

\[
\downarrow
\]

\[
\text{Selective Behavioral Inference}
\]

This is a possible research story, **not a required outcome**.

The system must stop at the strongest level actually supported by evidence.

A strong phenomenon + task paper is preferable to:

- a weak phenomenon;
- an unnecessary method;
- a forced positive result.

---

# 27. Current Preferred Scientific Framing

The current candidate high-level question is:

> **When do observable on-chain action traces support reliable natural-language behavioral interpretation, and when do such interpretations survive future behavioral evidence?**

A stronger NLP formulation, if supported, is:

> **Given a pre-cutoff on-chain action history, generate evidence-grounded, mutually competing, prospectively falsifiable natural-language behavioral hypotheses, and estimate whether those hypotheses are likely to survive future behavioral falsification.**

Do not freeze this wording until literature and empirical audits support it.

---

# 28. Core Scientific Principle

The system must distinguish:

\[
\text{Plausibility}
\neq
\text{Faithfulness}
\neq
\text{Validity}
\]

A hypothesis may:

- sound plausible;
- cite the right evidence;
- respond correctly to evidence removal;

and still lack prospective behavioral validity.

The research program should determine whether this gap is:

- systematic;
- predictable;
- attributable to ambiguity/equifinality;
- exploitable for selective inference.

---

# 29. Final Operating Principle

The research system must optimize for:

> **a novel, falsifiable, NLP-central, reproducible, reviewer-robust scientific claim**

—not for:

- positive results;
- autonomous activity;
- experiment count;
- model complexity;
- large token usage;
- preserving a favored theory.

The most valuable autonomous behavior is often not:

> “What else can we try?”

but:

> **“What should we kill now, before spending more compute?”**

The system should therefore prioritize:

\[
\boxed{
\text{Discover}
\rightarrow
\text{Attack}
\rightarrow
\text{Falsify Cheaply}
\rightarrow
\text{Freeze}
\rightarrow
\text{Replicate}
\rightarrow
\text{Scale}
}
\]

over:

\[
\text{Idea}
\rightarrow
\text{Large Experiment}
\rightarrow
\text{Post-hoc Story}
\]

---

# 30. First Action After Deployment

Immediately after the framework is operational:

1. ingest all existing project results and negative findings;
2. reconstruct the claim ledger;
3. reconstruct the experiment registry;
4. run independent Astra6 audits of the current paper story;
5. perform the Decision-State V1 case-level Evidence–Validity discovery analysis;
6. launch literature audits for Branches A–F;
7. keep at most 2–3 high-value branches after the first adversarial review cycle;
8. do not start a large new LLM experiment until those branches survive the first falsification gate.
