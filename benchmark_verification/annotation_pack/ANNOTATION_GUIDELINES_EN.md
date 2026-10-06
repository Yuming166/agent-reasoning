# Annotation Guidelines — eth-actions-benchmark-v1.0.0-candidate

Version: 2026-10-06. These guidelines govern human blind review (pilot of 20 wallets first). **Program answers, model predictions, and future-window data are never included in the annotation package**; annotator judgment fields stay empty until filled by humans. Any output of a machine (Claude or other models) must never be recorded as human review.

## 1. Task and Materials

Each annotation unit comes from one query (wallet, UTC cutoff). You will see:
- `history_parent_refs`: references to the wallet's pre-cutoff parent actions (relative paths into `parent_actions/{split}.jsonl.gz`);
- `entity_alias_map`: entity alias map (produced from the strict history prefix only);
- for grounding tasks: the `claims` (statements) and `candidate_address`;
- for forecast tasks: the window start and end timestamps.

You will NOT see: the program-computed target, gold parent-action sets of any scope, fact labels, model predictions, or any on-chain material inside the 7-day window (window source materials are provided separately by the coordinator in a controlled step).

## 2. Key Definitions (consistent with RELEASE_PROTOCOL.md §4)

### 2.1 Qualifying outgoing external attempt (forecast task)
- `event_family == 'external_tx'` and the wallet is the true `from_address`;
- target is not null/empty/all-zero address and not self;
- **attempted semantics**: failed receipts (receipt_status=0) **count as qualifying**; zero-value calls and contract creations follow the frozen rules as well — no "successful and amount>0" filtering;
- time window: `[cutoff, cutoff+7 days)`, inclusive-exclusive;
- order: canonical `(block_number, transaction_index, event_index)`, take the first;
- no such action → inactive.

### 2.2 Three localization scopes (grounding task; annotate separately, never mix)
1. `candidate_relevant_parent_ids`: parent actions related to the candidate's appearance (program relevance);
2. `claim_required_parent_ids`: evidence actions **necessary for the statement to hold**; when this cannot be determined from credible sources, mark `not_available` — do not substitute scope-1 items;
3. `latest_relation_parent_ids`: the **most recent** observation of the exact relation key in the statement.

The same parent action may appear in several scopes; give your own judgment for each scope independently.

### 2.3 Fact labels (supported / conflicted / unknown)
- `supported`: evidence supporting the statement exists in history;
- `conflicted`: evidence conflicting with the statement exists;
- `unknown`: evidence is missing or cannot be adjudicated. **unknown is a state, not a parent-action id**; never write "UNKNOWN" into any scope's parent list.

### 2.4 unknown boundaries (do not "complete" the record)
- `raw_transaction = null` ≠ no call exists;
- an empty raw-log list ≠ no logs exist (marked separately as raw_log_source_coverage=unknown);
- a missing own-wallet role packet = unknown; **never** copy another wallet's role certificates;
- complete local observation ≠ complete EVM execution, current true allowance, or subjective intent. All of these remain unknown.

### 2.5 Amounts and coreference
- Raw amounts of different tokens are never summed or converted across assets;
- entity coreference follows `entity_alias_map` (strict history prefix) only.

## 3. Procedure
1. **Independent annotation**: two annotators work independently with no discussion of intermediate judgments; record verbatim in `annotator_1_raw_judgment` / `annotator_2_raw_judgment`;
2. **Dispute adjudication**: for disagreements, a third party (or the two annotators after negotiation) records the final judgment and rationale in `dispute_adjudication`;
3. **Agreement computation**: computed once after all annotation is complete (per-scope exact set, fact agreement, Kappa), written into `agreement_computation`;
4. Until then all annotation fields stay empty; any unfilled field is reported as pending.

## 4. Prohibitions
- Do not consult program gold files (`forecast_gold/`, `grounding_gold/`, `gold_crosswalk/`) before annotating;
- Do not enter any model output (including Claude) into human fields;
- Do not query the chain or any external data source before annotating; work from the distributed offline package only;
- Do not modify package files; judgments go only into the empty fields of the annotation sheet.

## 5. Pilot Scope
- 20 wallets (see `pilot20/wallet_list.json`, seed 20261006): 115 grounding examples, 60 forecast windows;
- pilot goals: estimate per-example time and guideline ambiguity rate; after completion, decide whether to expand per the unexecuted budget plan in `BUDGET_PLAN_200CORE_80CHALLENGE.json` (200 random core + up to 80 hard stratum; the hard stratum is defined only by history structure/missingness/binding rules).

## 6. Record Attribution
While all human fields are empty, dataset reports keep `human_status: pending`. Automatic labels (the existing grounding gold) are called **automatic labels** only, until any human verification completes.
