## 1. FINAL_GATE_DECISION: MODIFY_BEFORE_ANNOTATION

The package is correctly marked `PREPARED_NO_ANNOTATIONS`; no semantic or reliability result exists yet. However, deterministic validation and reliability-scoring defects must be corrected before human annotation.

## 2. BLINDING_AND_LEAKAGE

- The supplied Pass A columns are text-only plus blank annotation fields. Pass B contains the intended recorded consequence, horizon, and evidence fields. Current audits show unique row handles, no wallet-like values, and no listed F/Delta/future-outcome, probability, rank, or model-metadata columns.
- The temporal Pass A/Pass B lock is not actually enforced. `audit_blinding()` hard-codes `pass_a_hidden_until_locked` from the pass name, and `blinding_ok` ignores that field. Both files are generated together, and the manifest hashes the blank template rather than a submitted-and-locked Pass A.
- The validator permits extra columns and relies on an incomplete blacklist. Generic `rank`, exact `F`, arbitrary score/provider metadata, or other leakage-bearing fields could pass. Wallet-like values are checked only in `row_handle` and `hypothesis_text`, not notes or extra columns.
- The opaque permutation and current generated-column contents are acceptable, but the audit is not fail-closed.

## 3. SCHEMA_AND_STATISTICS

- The declared label sets are implemented correctly for the listed fields. For the four known evidence groups, the `not_applicable` logic is correct; `unclear` is retained as a real reliability category.
- Exact-span validation is incomplete: the validators only require a non-empty span and never verify that it is an exact substring of `hypothesis_text`. Pass A also gates the check only on `pass_a_commitment`, not independently on non-`unclear` `pass_a_operationality`.
- Evidence labels have no allowlist validation. An unknown evidence ID is silently treated as absent, allowing the known groups to be marked `not_applicable`.
- The reliability script does not apply the declared missingness, agreement, or kappa thresholds. Once any valid pair exists, it reports `COMPUTED` even if missingness exceeds 5% or reliability fails. The blank smoke’s `exact_agreement_all_rows=1.0` with zero valid pairs is not a usable reliability estimate, although its `RELIABILITY_NOT_YET_ASSESSABLE` status is appropriate.
- The fixed 20-case double-code roster is never read. The scorer uses every row/case present in the coder files and the full `row_to_case` map. The supplied smoke output reports `bootstrap_cases=100`, not the required 20; therefore its whole-case bootstrap universe is wrong.
- Cohen’s kappa is nominally computed over complete pairs and treats `unclear` as a category. The AC1 implementation is wrong for the multi-category fields: it omits the nominal `1/(q-1)` factor in the chance-agreement term and does not use an explicit declared category count. ([mdpi.com](https://www.mdpi.com/2076-3417/16/17/8808?utm_source=openai))
- The reported `categories` diagnostic also counts rows where either coder used a category, rather than pooled rater assignments; this misreports category totals even when the agreement coefficients are otherwise computed.

## 4. CLAIM_BOUNDARY

This is an off-charter exploratory fallback preparation, not an Astra6 result, official claim, preregistration, or final scientific conclusion. The current package contains no human annotation or semantic-gate outcome.

Even a later passing annotation/reliability gate could support only descriptive human agreement and alignment of model-produced structured consequence labels. It would not establish forecasting effectiveness, future ground truth, causal intent, true owner belief, psychology, emotion, or social exposure. Address-level behavior remains only an actor proxy. The August frozen test is immutable, and the official Astra6 cycle, claim ledger, and experiment registry remain untouched.

## 5. NEXT_ACTION

Apply one deterministic fail-closed pre-annotation patch to the existing validator/reliability scorer: enforce the exact schema and substring spans, load and assert the fixed 20-case roster, correct multi-category AC1 and threshold handling, then rerun only the blank smoke expecting `bootstrap_cases=20` and `RELIABILITY_NOT_YET_ASSESSABLE`.

`large_llm_experiment_allowed=false`  
`promotion_to_official_ledger=false`