## 1. Publication gate: NAACL / WWW / neither

**Current overall decision: NEITHER.** No publishable discovery is established on the supplied evidence.

| Route | Status | Gate rationale |
|---|---|---|
| **NAACL** | **CONDITIONAL** | A realistic path exists if the contribution becomes a language-specific task involving evidence alignment, falsifiability, competing hypotheses, and selective prediction, validated by blinded annotation and a genuinely later temporal holdout. |
| **WWW** | **HOLD** | The structural/network signal failed its frozen gate; repeated wallets, one historical test cutoff, and activity/autoregressive confounds do not currently support a WWW-level graph discovery. |

## 2. Candidate claim, scope, and claim state

> For external Ethereum address proxies—not human-owner mental states—a structured language-level gate using evidence pointers, observable 7-day consequences, explicit falsifiers, and abstention may improve semantic validity and matched-coverage future-behavior prediction over recent-dynamics and confidence-only baselines on a genuinely later temporal holdout; **scope: address-level longitudinal behavior under the fixed consequence schema; state: UNTESTED**.

## 3. Actually observed evidence versus proxy or hypothesis

**Observed**

- Frozen V1 effectiveness failed: B0 macro log loss was **0.810633**, while B4 was **0.840193**; B4 also failed against B2 (**0.811696**).
- Evidence responsiveness passed on July development data for the relevant intervention groups, but did not transfer to predictive effectiveness.
- The discovery audit found near-zero association between intervention response and incremental validity: Pearson **−0.0334**, Spearman **−0.0194**, and adjusted Pearson **−0.0383**.
- Case-level gains occurred in **53.65%** of cases, but mean degradation was positive; the audit pooled development/test rows, included repeated wallets, and was not a prevalence estimate.
- OW-010B found a provisional M1-over-M0 gain but no frozen structural-support result: M2_CORE-over-M1 was below the 2% gate.
- The panel contains only **June 1, July 1, and August 1, 2022** cutoffs; August is an immutable historical test, not a newly available post-August holdout.
- The data-boundary audit passed for the frozen protocol: fixed samples, no identified future leakage, and complete response manifests.

**Proxy or hypothesis, not established**

- “Intervention responsiveness is an evidence-validity certificate” is unsupported; the narrower observed result is only that responsiveness did not guarantee future usefulness.
- The proposed claim tuple—predicate, scope/time, evidence, consequence, horizon, falsifier, and revision action—has not been validated by blinded human judgments.
- Behavioral equifinality, identifiability, sequential revision, and a language-specific selective gate remain hypotheses.
- An Ethereum address is an actor proxy; the observations do not identify owner psychology, intent, causal provenance, or social exposure.
- The proposed literature intersection is preliminary dated audit evidence, not a completed novelty or reproducibility review.

## 4. Novelty-overlap risks and the exact dated title/abstract/code/data audit still required

The **September 19, 2026** audit is explicitly preliminary. Before any novelty claim, complete a dated title/abstract/code/data audit covering:

- **Blockchain and address behavior:** `Know Your Intent`, `Intent2Tx`, Ethereum address profiling, temporal ego-network and role-inference work, and the closest temporal address-profiling paper.
- **Hypothesis and provenance methods:** `Att-NLI`, `HypER`, Counter-Hypothesis Generation, evidence-grounded reasoning, entailment, contradiction, argument mining, and Explainable AML Triage.
- **Belief and revision:** observational equivalence, equifinality, inverse planning, partial observability, defeasible reasoning, belief revision, and evidence-conditioned retraction or qualification.
- **Selective inference:** calibration, abstention, risk-coverage, conformal/selective prediction, uncertainty decomposition, and confidence-only gating.
- **Financial/agent methods:** CryptoTrade, FinMem, TradingAgents, financial Theory-of-Mind, and future-validated behavioral reasoning.

For every candidate, record the **exact title, authors, venue, publication/preprint date, abstract overlap, task definition, input granularity, hypothesis representation, evidence/provenance mechanism, intervention or null condition, labels and annotation protocol, temporal split, leakage controls, official code and commit/release, dataset and license, and minimal runnable result**. The audit must determine whether the proposed tuple, falsifier protocol, intervention controls, and matched-coverage evaluation are operationally distinct rather than renamed entailment, argument mining, belief revision, or selective prediction.

## 5. Cheapest decisive experiment

Run a staged **V2-0 falsification gate**, with no large LLM study.

- **Frozen sample:** Select **100 existing July cases** using a pre-outcome random seed, stratified only by pre-outcome activity/event bins, with at most one case per wallet where feasible. Use existing outputs; do not rewrite prose or make new calls in Stage 1.
- **Temporal split:** June remains the reference/training period, July is the development annotation period, and August remains an untouched historical test. Do not tune any rule using August. No supplied evidence establishes a later post-August block; therefore no new generalization claim may be made.
- **Source-coverage check:** Confirm that every evidence ID maps to material available before the cutoff; verify source-window coverage and missingness; exclude future-only fields such as `future7_*`, `y_*`, and `eval_complete` from prompts; do not treat missing coverage as behavioral absence.
- **Annotation rubric:** Two blinded annotators label evidence alignment, text-to-schema entailment, scope and horizon completeness, observable consequence, directional falsifiability, semantic non-redundancy, and whether competing hypotheses are genuinely distinct. Missing fields remain missing; annotators may not infer owner intent or causal meaning.
- **Controls:** Existing relevant-versus-placebo interventions; evidence-pointer shuffling; contradiction substitution where available; full claim versus consequence-only, template/text-ablated, confidence-only, and random matched-coverage gates. Any new prompt/control calls require a separately frozen V2 protocol.
- **Primary metric:** If—and only if—a genuinely later temporal block is available, use held-out paired macro-log-loss improvement over M1 at development-fixed coverage across the four consequence dimensions. Semantic validity precision and annotation agreement are prerequisite gates, not substitutes for future evaluation.
- **Statistical test:** Use a wallet-blocked paired bootstrap 95% confidence interval for per-case log-loss differences, with matched-coverage comparisons against random and probability-only gates; report Krippendorff’s alpha or equivalent predeclared inter-annotator agreement.
- **Untouched holdout:** The August cutoff remains historical and immutable. A conditional V2 pilot requires a separate later chronological block held untouched until protocol, thresholds, coverage, and analysis are frozen. If no such block exists, stop after the semantic falsification gate.

## 6. Conditional go/no-go tree toward a paper

1. **Complete dated overlap audit?**  
   - No → **HOLD**.  
   - Yes → continue.

2. **Deterministic and prompt-null checks survive activity, recency, autoregressive, wallet-blocked, and placebo controls?**  
   - No → **KILL** the evidence-validity/identifiability interpretation.  
   - Yes → continue.

3. **Semantic gate passes completeness, agreement, evidence alignment, and non-redundancy thresholds?**  
   - No → **KILL** the language-specific branch.  
   - Yes → continue.

4. **Full language adds value over consequence-only, templated, text-ablated, confidence-only, and random controls?**  
   - No → **KILL** the claim that natural language is central.  
   - Yes → continue.

5. **A genuinely later post-August holdout exists and is frozen before inspection?**  
   - No → **HOLD**; no new positive generalization claim is possible.  
   - Yes → preregister the small V2 pilot.

6. **Candidate beats M1, random gating, and probability-only gating at matched coverage on the untouched holdout without retuning?**  
   - No → **NO-GO** for a discovery paper; retain only the bounded negative result if useful.  
   - Yes → **CONDITIONAL NAACL submission path**, followed by independent replication.

A positive small pilot remains exploratory until replicated. A negative predictive result alone is not a discovery.

## 7. Venue strategy: NAACL versus WWW

**NAACL is currently the more credible route.** The paper would need to make language central: a structured hypothesis object, blinded semantic labels, evidence/falsifiability metrics, intervention/null controls, and calibrated selective prediction.

**WWW remains on HOLD.** It would require a robust network-level contribution beyond recent activity, degree, scale, and autoregressive proxies, preferably across additional temporal blocks or external labels. The failed OW-010B structural gate does not support that route now.

## 8. Reviewer risks and forbidden claims

**Primary reviewer risks**

- \(F\) measures model-response displacement, while \(\Delta\) measures downstream loss; their mismatch may reflect calibration, aggregation, prompt, formatting, or meta-head effects.
- M1 and apparent structural gains may be activity, recency, degree, scale, or autoregressive proxies.
- Repeated wallets, pooled splits, selected discordant cases, and one historical test cutoff limit generalization.
- Human annotators may inject intent, psychology, or causal meaning absent from address-level observations.
- The proposed work may collapse into existing entailment, argument mining, belief revision, explanation-faithfulness, or selective-prediction methods.
- Natural language may be cosmetic unless it beats structured consequence-only and text-ablated controls.
- No post-August holdout has been supplied; August cannot be retuned or repurposed.

**Forbidden claims**

- True wallet-owner emotion, belief, intention, or persistent latent decision state.
- Causal provenance, verified social exposure, or Theory-of-Mind/relational expectation.
- “Intervention response proves semantic validity” or “proves causal intent.”
- Confirmed language-based generalization, alpha, structural signal, or broad predictive superiority.
- “LLM behavioral reasoning is generally ineffective.”
- Demonstrated equifinality without distinct hypotheses fitting the same observations and implying different future outcomes.
- Novelty claims that the area is empty before the dated title/abstract/code/data audit is complete.
- Any claim based on inspecting, retuning, or selecting against the August historical test.