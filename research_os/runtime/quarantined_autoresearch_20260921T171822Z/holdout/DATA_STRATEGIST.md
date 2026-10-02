# HOLDOUT_FEASIBILITY_REVIEW

**Status: not assessable in this run.** The read-only runtime failed before local file access with:

`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`

Therefore, no facts from `ALLOWED_DATA_METADATA.json`, `SEPTEMBER_QUERY_METADATA.tsv`, or any SEARCH_SCOPE-like context were available for verification.

- Genuine post-August untouchedness: **Unknown**
- Same-semantic construction: **Unknown**
- Existing materialization: **Unknown**
- Upstream-source possibility: **Unknown**
- Exact reproducibility: **Unknown**
- Schema drift: **Unknown**
- Final test set: **Not constructed or frozen**

# CUTOFF_CLASSIFICATION

| Candidate cutoff | Existing materialization | Upstream-source possibility | Exact reproducibility | Native/token/internal continuity | Mapping attrition | Event identity | +7/+30 availability |
|---|---|---|---|---|---|---|---|
| 2022-09-01 | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| 2022-10-01 | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| 2022-11-01 | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |
| 2022-12-01 | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |

No cutoff can be classified as a genuinely untouched holdout from the currently accessible evidence.

# SCHEMA_CONTINUITY_RISKS

Not evaluated because the permitted metadata could not be read. The following remain unresolved for every cutoff:

- native versus token-level field continuity;
- internal identifiers and mapping-table coverage;
- endpoint/node mapping attrition;
- preservation of stable event identity and duplicate semantics;
- event ordering and temporal-boundary semantics;
- whether records required for `+7` and `+30` availability exist without post-cutoff leakage.

# DATA_EXTENSION_PLAN

1. Read only the three permitted metadata sources.
2. Inventory materialized date ranges and source-query boundaries.
3. For each candidate cutoff, compare the same inclusion, exclusion, mapping, event-identity, and availability semantics.
4. Separate:
   - already-materialized data;
   - theoretically retrievable upstream data;
   - exactly reproducible data;
   - data requiring changed schema or semantics.
5. Record attrition separately for native, token, internal, and mapping layers.
6. Do not materialize, select, or freeze a final test set during this audit.

# REQUIRED_VALIDATION_BEFORE_FREEZE

Before freezing any cutoff, verify:

- explicit evidence that all post-cutoff records were untouched by prior materialization, annotation, prediction, or submission workflows;
- identical query semantics and timestamp interpretation;
- reproducible upstream source snapshots or immutable source versions;
- stable schemas, identifiers, mappings, and event-identity rules;
- quantified attrition at native, token, internal, and mapping stages;
- confirmed event ordering and duplicate handling;
- independently verified `+7` and `+30` availability without future leakage;
- a dry-run audit manifest and hashes before any final test-set construction.