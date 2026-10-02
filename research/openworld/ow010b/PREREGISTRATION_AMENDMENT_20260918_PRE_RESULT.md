# OW-010B Pre-result Preregistration Amendment — 2026-09-18

This amendment was made after inspecting the OW-010A schema but before any OW-010B model, target, or primary metric result was computed.

## Reason

The frozen OW-010A discovery table contains `native_event_count_7d` but does not expose independent token-transfer and internal-trace counts for the same 7-day score window. A seven-dimensional future composition target requires a matched pre-cutoff three-family reference. Using 30-day composition as a 7-day reference would be an avoidable window mismatch.

## Change

Materialize a compact, leakage-safe aggregate keyed by `(anchor_wallet, cutoff_time)` from `openworld_anchor_events_v1`:

- score-window `[t-7d,t)` counts for external/native, token-transfer, and internal-trace families;
- score-window incoming, outgoing, and self counts;
- no raw event rows are exported;
- all joins use `event_timestamp < cutoff_time`.

The new aggregate is used only to construct the already-declared target reference and M1 recent-vs-prior derived features. It does not change the population, future horizon, model classes, split, metrics, or decision rules.

The updated preregistration and manifest hashes supersede the pre-amendment hash. No test outcome was inspected before this change.
