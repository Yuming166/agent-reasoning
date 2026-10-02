# OW-010A BigQuery Feature Specification

This is the implementation specification for the next event-level substrate. Feature intervals are relative to cutoff `t` and are all half-open.

| family | feature examples | exact interval | status in v1 |
|---|---|---|---|
| activity | event count 1h/6h/1d/7d/30d, active days/hours | `[t-1h,t)`, `[t-6h,t)`, `[t-1d,t)`, `[t-7d,t)`, `[t-30d,t)` | materialized |
| inter-event | mean/median/std/min/max gap | `[t-30d,t)` ordered by timestamp/block/tx/event/trace | materialized; N/A for <2 events |
| flow | incoming/outgoing/self counts, native inflow/outflow/netflow, amount mean/max | `[t-30d,t)` and native family subset | materialized; native amounts N/A without native events |
| counterparty | unique, mapped/unmapped, novelty, repeat, entropy, growth | prior `[t-30d,t-7d)` vs score `[t-7d,t)` | counts and novelty/growth derivable; exact reciprocity delta pending |
| temporal structure | reciprocity, rapid forwarding, fan-in/out | `[t-30d,t)`; fan-in/out score subset `[t-7d,t)` | adjacent rapid-forward proxy and hourly fan proxies |
| composition | native/token/internal counts and ratios, token-contract diversity | `[t-30d,t)` | materialized |
| network | temporal degree and event-weighted degree | `[t-30d,t)` | derivable from counterparties/events |
| cycles/split/merge | temporal cycle and asset-aware split/merge | `[t-30d,t)` | unsupported in v1; requires explicit path/asset materialization |

Token quantities are retained as lossless strings but are not summed across token contracts or token IDs. Future outcomes are never in this discovery table.
