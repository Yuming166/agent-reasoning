# OW-010A Event Identity Policy

## Canonical identities

- `external_tx`: `(event_family, transaction_hash)`
- `token_transfer`: `(event_family, transaction_hash, event_index, token_contract_address, token_id, from_address, to_address)`
- `internal_trace`: `(event_family, transaction_hash, trace_address)`

All address components are lower-cased. Exact duplicate removal is only applied when both the semantic identity and a full-row signature agree. If one semantic identity has multiple full-row variants, every variant is retained and `identity_collision_flag=TRUE`.

## Audit findings

- External: 2,877,009 rows, zero duplicate identity groups, zero collision groups.
- Internal: 4,478,515 rows, zero duplicate identity groups, zero collision groups; transaction hash alone would be insufficient because there are 3,382,252 distinct transaction hashes but 4,478,515 trace identities.
- Token: 4,275,544 source rows; 136 exact duplicate extra rows under the extended identity and 12 collision groups containing 24 rows. `(transaction_hash,event_index)` alone is inadequate: 3,097 transaction/event-index groups contain multiple extended items, with a maximum of 99 items.

The initial token identity diagnostic that used only `event_index` is treated as superseded and is not used for the materialized table.
