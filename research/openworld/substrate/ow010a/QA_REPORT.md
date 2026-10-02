# OW-010A QA Report

## Source and identity

- Source window: `[2022-03-01,2022-09-01)` UTC.
- Source rows: external 2,877,009; token 4,275,544; internal 4,478,515.
- Materialized anchor rows: 11,835,499.
- Observed mapped anchors: 21,469; the remaining mapped addresses remain in the wallet×cutoff feature grid with true-zero/unobserved statuses.
- Unmapped counterparty rows are retained: 11,394,460 rows with a non-null unmapped counterparty address, plus 3,284 rows without a counterparty address.
- Anchor direction rows: incoming 5,153,224; outgoing 6,654,776; self 27,499.
- Token identity audit: 3,097 `(transaction_hash,event_index)` groups have multiple extended token items; maximum 99.

## Discovery coverage

The discovery feature table has exactly 82,839 rows = 27,613 anchors × 3 cutoffs. There are 35,264 true-zero history rows and 47,575 rows with history activity across all cutoffs.

## Direction and counterparty coverage

For history>=1, both-direction wallets are 14,833 / 13,460 / 12,314 at June/July/August; incoming-only are 1,657 / 1,542 / 1,490; outgoing-only are 665 / 732 / 878. Counterparty coverage shows unmapped counterparties for 17,028 / 15,595 / 14,540 history-active wallets, so a mapped-only filter would materially alter the open-world population.

## Temporal leakage

The compact leakage audit reports zero violations for: history start/end bounds, score start bound, discovery role, full source coverage, future outcome role, and future-named columns in the discovery table. The feature query references only event timestamps strictly before cutoff.

## Matching diagnostic

The frozen OW-009 matcher enters 19 / 15 / 18 strict Top-5% treated wallets, matches all of them to five control assignments, and has zero unmatched treated rows. However, the balance criterion fails: strict `max after SMD` is 0.6575 / 0.8699 / 0.4706, far above 0.10. Reuse rates are 0.2421 / 0.2933 / 0.2667. The assignment fallback reuses controls from only the fixed nearest-neighbor list; this is an implementation behavior, not evidence of sufficient balance.

The current negative result is not reinterpreted as a detector result. No label table was read.
