# OW-010A Final Report

**Status:** `SUBSTRATE_READY_FOR_OW010B`  
**Label access:** none; EX-Graph wash/illicit labels were not inspected, joined, counted, or used.  
**Scope:** event-level as-of substrate reconstruction and diagnosis only.

## 1. Why did ~27,613 mapped addresses become only ~370/282/359 strict candidates?

Because OW-009 did not operate on all event-level mapped anchors. Its executable input was a day-level local extract that had already applied `sequence_role=primary`, `counterparty_present`, `NOT self_transaction`, and both-endpoints-EX-Graph-mapped filters. The script then retained only outgoing-source wallets, required at least three active history days and at least ten history events, and only then ranked. The resulting strict candidate counts were 370 / 282 / 359 for 2022-06-01 / 2022-07-01 / 2022-08-01.

## 2. Which single filter caused the largest attrition?

At the observed stage level, the local source-artifact observability filter removed 16,243 / 15,518 / 15,002 wallets. Among explicit OW-009 code predicates, `hist_active_days >= 3` removed 3,344 / 2,663 / 2,454; this is the largest explicit predicate attrition.

## 3. Which filters are scientifically necessary?

The as-of cutoff, half-open time intervals, family-specific event identity, exact duplicate policy, and declared history window are necessary for a valid temporal observational unit. Preserving event family, direction, self events and unmapped counterpartes is necessary for the intended open-world behavioral population. Future windows and Top-5%/matching rules are valid only as separately declared evaluation design, not discovery eligibility.

## 4. Which filters are implementation artifacts or unnecessarily restrictive?

The local primary-only, both-endpoints-mapped, non-self, outgoing-only, day-aggregated representation is an inherited implementation projection, not a general wallet discovery requirement. Universal `active_days >= 3` and `events >= 10` are potentially overrestrictive population choices. The original global `fillna(0.0)` is a missingness/zero conflation risk. Token `(transaction_hash,event_index)` identity is a fixed identity bug risk.

## 5. Is there any future-conditioned eligibility or leakage risk?

No future activity is required in the repaired discovery table: the full grid is retained and discovery features are joined only on `event_timestamp < cutoff_time`. The future table is physically separate, carries `evaluation_only=TRUE`, and leakage QA reports zero role/boundary violations. OW-009 materialized future outcomes for candidate rows after discovery but did not use them for ranking or matching; this audit keeps that distinction explicit.

## 6. How large is the true discovery cohort before future evaluation and matching?

Per cutoff, the full anchor×cutoff grid is 27,613. The pre-cutoff observed population is 20,461 / 20,818 / 21,123. The event-history `>=1` discovery cohort is 17,156 / 15,736 / 14,683. With a pre-cutoff score-window activity requirement `>=1`, it is 12,525 / 9,934 / 9,562. The latter is a diagnostic sensitivity condition, not the default discovery rule.

## 7. Why did matching fail to achieve |SMD| <= 0.10?

The frozen matcher assigned five controls to every treated wallet, so there was no assignment failure. The failure is balance: treated Top-5% wallets lie in activity tails and nearest Euclidean controls remain different. The strict maximum after-SMD is 0.6575 / 0.8699 / 0.4706. Every matching covariate fails the 0.10 criterion in at least two of the three cutoffs. The code has no caliper or balance-rejection rule; its fallback reuses controls from a fixed k-neighbor list.

## 8. Which information is missing from the current local representation?

The local OW-009 CSV lacks sub-day timestamps, transaction/event identities, event-family labels, native/token/internal distinction, native values, token contract/id/quantity, internal trace path, full incoming role coverage, self events, unmapped counterparties, and exact event-level temporal ordering. Consequently, rapid forwarding, precise novelty/growth, exact reciprocity change and asset-aware flow structure cannot be claimed from that local projection.

## 9. What exactly should be materialized from BigQuery?

Materialize a leakage-safe `wallet_id × cutoff_time` feature table from the event-level anchor table using history `[t-30d,t)`, prior `[t-30d,t-7d)`, and score `[t-7d,t)`: activity counts, inter-event gaps, native/token/internal composition, native flow, counterparty sets and entropy, novelty/repeat/growth, reciprocity, rapid forwarding, fan-in/fan-out and temporal degree. Keep token quantities lossless and asset-specific. Store `[t,t+7d)` and `[t,t+30d)` outcomes in a separate `evaluation_only` table.

## 10. Can we plausibly obtain >=2,000 leakage-safe candidates per cutoff?

Yes, plausibly. Even the conservative event-level `history>=1` cohort is 14,683--17,156 per cutoff, and `history>=10` is 10,294--13,130. A pre-cutoff score activity requirement `>=10` still leaves 4,913--6,981. The old 370/282/359 result is therefore not a substrate-wide coverage bound; it is a bound on the restrictive local projection.

## 11. Should the >=2,000 requirement remain unchanged?

Keep it unchanged for the next preregistered gate. It is a conservative heuristic coverage/precision guard, not a completed power calculation. The repaired substrate makes it plausible without threshold tuning. Any change should be a dated preregistration amendment after the discovery population and final estimand are frozen.

## 12. Is OW-009 currently:

`DESIGN_REVISION_NEEDED` with the current local representation `SUBSTRATE_UNDERPOWERED`. It is not `METHOD_NO_GO` solely from the negative pilot, not a single-code `IMPLEMENTATION_BUG`, and not `READY_FOR_RERUN`. For the OW-010A substrate track, the artifact is `SUBSTRATE_READY_FOR_OW010B`: event-level tables and leakage QA are complete. OW-010B remains explicitly unstarted; exact reciprocity feature parity is a next-stage freeze item.
