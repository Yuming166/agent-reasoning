# OW-010B Target Specification

This target is frozen in `preregistration/OW010B_PREREGISTRATION.md` before primary result inspection.

## Primary target

The primary target is a signed seven-dimensional change vector from the pre-cutoff score window `[t-7d,t)` to the future window `[t,t+7d)`:

- log1p event-count change;
- log1p unique-counterparty change;
- active-day change;
- incoming-share change;
- outgoing-share change;
- external/native-family-share change;
- token-family-share change.

Direction and event-family shares use three-category additive smoothing with alpha `0.5`; self/internal are reference categories. Target standardization is fit on the fitting cutoffs only. The target has no external-label component.

## Why this is not future activity alone

The vector has three scale/persistence coordinates and four composition coordinates. Its composition coordinates distinguish incoming from outgoing behavior and external/native, token, and internal event-family mix. A wallet can have the same future event count while changing direction or event-family composition, and such a row has nonzero target components. The primary M0 explicitly controls historical scale, recent level, volume, counterparty count, and degree; M1/M2 are tested only for incremental loss reduction.

## Scalar summary

`S7 = sqrt(mean(z_j^2))` where `z_j` are training-standardized signed target dimensions. This is a magnitude-of-change summary only; it discards direction and is secondary.

## Secondary 30-day target

The future table exposes only 30-day count, unique-counterparty, and active-day aggregates. The secondary 30-day target therefore has exactly those three signed changes relative to the 30-day history window. It cannot be used to claim 30-day composition or reciprocity prediction.

## Missingness and zero rules

- future zero counts are valid true zeros;
- score-window zero counts are valid reference values;
- smoothed shares remain defined for zero-event windows;
- incomplete future coverage is excluded from the relevant evaluation only and is not converted to zero;
- no future value is imputed;
- no target dimension is selected after viewing test outcomes.
