# Literature Gap Audit: Intervention-Verified Address-Level Behavioral Hypotheses

**Audit date:** 2026-09-19
**Status:** Preliminary dated title/abstract/source audit; not yet a systematic-review or final novelty claim
**Project:** EX-Graph Ethereum temporal behavior research
**Matrix:** `claim_matrix.csv`

## Executive decision

The audit supports a narrower and more defensible research direction:

```text
as-of address behavior
  -> open natural-language behavioral hypotheses
  -> pre-registered consequence schema
  -> evidence provenance and competing explanations
  -> support-removal / placebo intervention checks
  -> frozen out-of-sample future-behavior verification
```

The following claims are **not** novel enough on their own:

- LLM + on-chain data -> transaction intent;
- LLM + market/news/on-chain data -> trading decision;
- LLM-generated explanations for AML or transaction alerts;
- generic counterfactual or evidence-grounded LLM explanations;
- Ethereum address profiling or graph-based behavior classification.

The most credible provisional gap is their intersection:

> **Generate competing, provenance-linked hypotheses about a persistent address-level behavioral regime, test whether the stated evidence controls the hypothesis through interventions, and evaluate the frozen hypotheses against future on-chain behavior.**

This is a working gap statement, not a claim that no prior work exists.

## Scope and search protocol

### Six buckets

1. blockchain transaction intent inference / DeFi intent mining;
2. wallet behavioral state, behavioral regime, and address profiling;
3. LLM latent state or intention inference from observed behavior;
4. financial Theory of Mind, recursive belief, and expectation inference;
5. future-validated hypothesis generation or behavioral hypothesis testing;
6. intervention and counterfactual verification of inferred intent or explanations.

### Inclusion policy

The audit prioritizes:

- ACL/EMNLP/NAACL/LREC and other peer-reviewed NLP venues;
- KDD/WWW/ICLR/NeurIPS/AAAI/financial-computational venues;
- primary arXiv records when the venue/code/data status is explicit;
- official author, project, or code/data pages.

For each candidate, the matrix separates:

- address-level input from agent-internal memory;
- persistent state from one-transaction intent;
- hypothesis generation from classification;
- evidence provenance from ordinary rationale text;
- intervention from ordinary ablation;
- future verification from same-task labels or trading backtests;
- relational expectation from ordinary neighbor features.

### Limitations

This pass is a bounded web and source audit completed on 2026-09-19. It has not yet performed complete backward/forward citation chaining, venue-by-venue proceedings search, or end-to-end code/data execution for every candidate. Unknown fields are deliberately marked `not verified`; they are not negative evidence.

## Main findings by bucket

### 1. Transaction intent mining is a direct neighboring line

`Know Your Intent` directly studies DeFi user transaction intent mining using a multi-perspective LLM-agent design, an intent taxonomy, multimodal on/off-chain information, and an evaluator. This removes `LLM + on-chain events -> transaction intent` as a standalone novelty claim.

`Intent2Tx` studies the reverse direction: translating natural-language intents into executable Ethereum transaction plans and validating execution. It is not a persistent address-state paper, but it confirms that intent-centered Ethereum benchmarks are becoming a distinct research line.

**Boundary for our work:** current transaction meaning is not the primary object. The primary object is a time-indexed hypothesis whose future behavioral consequences are frozen before the future window is observed.

### 2. Address profiling exists, but not as future-validated decision-state inference

Ethereum behavior work has studied address profiling, deanonymization, temporal ego networks, role inference, and account classification. These works are close in input granularity, but the outputs are typically identity, role, risk, or class labels.

The audit did not verify a paper in this family that simultaneously provides:

- open-ended competing hypotheses;
- explicit evidence provenance;
- relevant-versus-placebo intervention tests;
- held-out future behavior verification of the inferred hypothesis.

**Boundary for our work:** the unit should remain `address` or `actor proxy`, not a claimed human wallet owner. Contracts, bots, exchanges, and shared custody make psychological owner language unjustified without additional identity evidence.

### 3. Financial LLM agents model their own decisions, not an external address

CryptoTrade, FinMem, and TradingAgents use market observations, news, prices, on-chain statistics, memory, reflection, role specialization, or debate to improve an agent's trading decision. Their future evaluation is generally trading return or backtest performance.

This differs from our intended task:

```text
external address history -> state hypothesis -> future address behavior
```

An LLM agent's internal memory is not the same as an inferred persistent state of an external Ethereum address.

### 4. Hypothesis and provenance methods already exist outside blockchain behavior

Att-NLI studies latent intention inference with abductive alternatives and deductive verification in a textual interactive environment. HypER studies literature-grounded hypotheses with evidence provenance. Counter-Hypothesis Generation evaluates whether LLMs can produce alternatives under changed context. Explainable AML Triage is especially close methodologically because it combines evidence retrieval, supporting/contradicting evidence, and counterfactual checks.

These works mean that the method cannot be described simply as `LLM generates hypotheses` or `LLM uses counterfactual explanations`.

**Potential differentiation:** apply a structured hypothesis object to a longitudinal address stream and score each hypothesis against pre-registered future consequences, while testing whether the claimed evidence actually controls the model output.

### 5. Theory of Mind is motivation, not yet the primary contribution

Financial ToM work studies how people reason about other participants' beliefs and expectations in experimental markets. It provides a theoretical motivation for a second-order relational hypothesis, but it does not establish a wallet-level LLM benchmark.

Therefore Level 2 should remain a gated extension:

```text
Level 1: address behavior -> operational hypothesis -> future behavior
Level 2: address + neighbors + context -> relational expectation hypothesis -> future group behavior
```

The paper should not claim that it identifies an address's true belief or mental state.

## Claim matrix interpretation

The detailed matrix is in `claim_matrix.csv`. The following summary is the current boundary map:

| Candidate family | Address-level | Persistent inferred state | LLM | Competing hypotheses | Provenance | Intervention | Future behavior verification | Current overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Know Your Intent | partial | no verified longitudinal state | yes | partial | partial | no verified | no verified | direct transaction-intent neighbor |
| Intent2Tx | no | no | yes | no | execution-aware | no | no | adjacent intent benchmark |
| CryptoTrade / FinMem / TradingAgents | no external address | agent memory only | yes | partial | partial | no | trading returns/backtest | adjacent financial-agent family |
| Ethereum profiling / ego networks / role inference | yes | no | no | no | no | no | generally no | adjacent address-behavior family |
| Att-NLI | no blockchain address | yes, task-specific | yes | yes | partial | verification, not causal intervention | no future address behavior | methodological neighbor |
| HypER / Counter-Hypothesis Generation | no | hypothesis object, not address state | yes | yes/partial | yes/partial | context changes or evaluation | no wallet future | methodological neighbor |
| Explainable AML Triage | alert/subgraph level | no verified persistent state | yes | partial | yes | yes counterfactual checks | no held-out future wallet behavior | closest intervention/provenance neighbor |
| Financial ToM experiments | participant/market experiment | participant belief construct | no LLM | recursive beliefs | no | experimental manipulation | experiment outcome, not wallet future | theoretical motivation |
| **Proposed work** | **yes** | **yes** | **yes** | **yes** | **yes** | **yes** | **yes** | **intersection candidate** |

## Proposed operational object

Do not freeze a seven-class state taxonomy in the first experiment. Use an open hypothesis with a closed measurement schema:

```text
Z_i^t = (
  hypothesis_text,
  probability_or_rank,
  consequence_vector,
  evidence_ids,
  alternative_hypotheses,
  horizon,
  abstention
)
```

The hypothesis text remains open-ended. The consequence vector is constrained to observable fields available in the EX-Graph time window, such as:

- net flow direction by asset family;
- stablecoin exposure;
- risky-token inflow/outflow;
- new versus repeat counterparty rate;
- asset or protocol concentration;
- interaction-family transition;
- future active days;
- future counterparty set or next-counterparty rank.

This is **open at the semantic layer and closed at the measurement layer**.

## Proposed baseline ladder

The audit recommends freezing the following ladder before any large Astra6 run:

```text
B0 = M1 recent-dynamics baseline
B1 = M1 + deterministic consequence/state proxies
B2 = M1 + single LLM hypothesis
B3 = M1 + multiple competing LLM hypotheses
B4 = M1 + hypotheses + evidence-intervention gate
```

The ladder is not assumed to be monotonically improving. The important tests are:

- `B4 > B2`: intervention verification adds value beyond multi-hypothesis generation;
- `B4 > B0`: the hypothesis layer has incremental predictive value beyond recent dynamics;
- `B4` improves calibration or abstention even if raw prediction gain is small;
- claimed evidence importance aligns with directional intervention response;
- irrelevant placebo does not produce the same response as relevant evidence removal.

Future outcomes must be used only after the hypothesis is frozen. They may score the hypotheses, but may not select or rewrite the test-time hypothesis.

## Recommended novelty wording

### Safe working claim

> Existing work has studied blockchain transaction intent mining, financial-agent reflection, address profiling, and evidence-grounded or counterfactual LLM reasoning separately. We study whether an LLM can generate competing, provenance-linked behavioral hypotheses for an external Ethereum address, and whether those hypotheses remain useful after evidence interventions and out-of-sample future-behavior verification.

### Claims to avoid

- “We infer the true intent of a wallet owner.”
- “We identify investor emotions from transaction histories.”
- “No prior work studies blockchain intent with LLMs.”
- “Counterfactual sensitivity proves causal belief or intention.”
- “Theory of Mind is demonstrated by a next-counterparty prediction.”
- “A successful narrative explanation is a discovered latent state.”

## Decision

```text
LITERATURE_GATE = PRELIMINARY_PASS_WITH_NARROW_NOVELTY
LEVEL_1 = eligible for protocol design
LEVEL_2_RELATIONAL_EXPECTATION = DEFER_UNTIL_LEVEL_1_PASS
LARGE_ASTRA6_RUN = HOLD_UNTIL_PROTOCOL_FREEZE
STRUCTURAL_ANOMALY_RESUSCITATION = NO
```

The audit supports writing a first-level protocol around:

```text
Infer -> Intervene -> Verify
```

It does not yet support a broad claim of an empty literature area. The next audit increment should be citation chaining plus full-text/code/data verification for the closest five papers: `Know Your Intent`, `Att-NLI`, `HypER`, `Explainable AML Triage`, and the closest address-profiling temporal paper.
