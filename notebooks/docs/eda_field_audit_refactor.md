# EDA field-coverage audit and refactor

The executed `01_roombeacon_eda.ipynb` is the current numerical report. Historical
counts in older methodology documents must not be reused as current findings.
This change does not modify Notebook 02, source/processing helpers, Bronze, or Silver.

## Inspection and original section/chart decisions

Cell numbers below are zero-based positions in the pre-refactor working notebook,
which already contained local changes. Both official notebooks, snapshot SQL,
`notebook_audit`, text/address/ward/coordinate/numeric helpers, relevant tests,
notebook section docs, source adapters and Bronze/Silver/Gold guidance were inspected.

| Original cells / section | Decision | Evidence and rationale |
|---|---|---|
| 0–4 introduction, imports, snapshot contract | KEEP / IMPROVE | One runtime snapshot and aligned raw evidence are sound. Retain read-only connection and identity/time/version tie-break. Add canonical combined audit frame. |
| 5–6 inventory and source proportions | IMPROVE | Inventory counted only 20 base columns; add evidence/derived counts and all-field inventory. Keep source counts/rates in a compact table. |
| 7 dtype-only chart | REMOVE | Dtype inventory table provides the same information plus coverage, examples and cardinality. |
| 8–9 location readiness | MOVE / IMPROVE | Derived location fields existed but were excluded from subsequent missingness. Parsing raw best address diverged from Notebook 02's Task 08 normalized input. Status population was labelled availability, which could imply success. |
| 10 location coverage and coordinate source heatmap | MERGE / MOVE | Replace repeated address coverage with one branching funnel; retain source trust heatmap in coordinate domain. |
| 11 coordinate reasons/providers/hotspots | KEEP / MOVE | Useful evidence of shared-point conflicts; retain after coordinate pair checks. Clarify that heuristic trust is not external verification. |
| 12 district/ward top-N and search eligibility | MOVE / MERGE | Previously appeared before structural/missingness diagnostics. Retain distributions as subset-labelled tables after domain coverage and source breakdowns; keep search eligibility as a table. |
| 13–15 structural validation | KEEP / IMPROVE | Preserve identity and timestamp checks; add nonpositive/nonfinite values, coordinate bounds/pair completeness and address provenance. PASS-count chart and timestamp chart are replaced by the full checks table. |
| 16–18 semantics | IMPROVE | Only selected text/numeric fields were profiled. Extend exclusive representation states to every runtime audit column; status distributions are separate from value coverage. |
| 19–21 missingness profiling | IMPROVE / MERGE | Base-only masks omitted derived location fields. Missing-rate and present/missing stacked charts mirrored one another. Replace with complete tables and one source × important-field heatmap backed by all-field counts/rates. |
| 22–25 missingness visualization | MERGE / IMPROVE | Four-core-field pattern charts overlap. Keep full location-aware exact-pattern table and one co-occurrence heatmap. |
| 26 address layer coverage/provenance | MERGE | Repeated address coverage folds into funnel; provenance distribution remains a table. |
| 27–29 roots and confidence | IMPROVE / MERGE | Price/area/address evidence useful, but no street/district/province causes or ward mapping losses. Add conservative textual cues, actual statuses, source-level reason counts and deterministic review samples. Merge confidence/reason charts into one evidence chart plus tables. |
| 30–31 treatment | IMPROVE | Previous three-field action totals and declared usability heatmap were not complete diagnostic findings. Replace with field/reason/confidence/action/owner table and current numeric disagreement counts; keep use-case caveats in prose. |
| 32 conservation / close | KEEP / IMPROVE | Extend assertions to every field, status distribution, funnel edge and source denominator, plus raw/evidence preservation. |

## Final notebook structure

1. Dataset Inventory & Snapshot — canonical base/evidence/derived inventory.
2. Structural Validation — identity, numeric, coordinate, provenance and time checks.
3. Field-Level Profiling — audit matrix, semantics and status distributions.
4. Missingness & Completeness — all-field, all-source, domain and stage tables.
5. Domain Quality Analysis — identity/text; price/area; branching address funnel;
   street/ward/district/province; coordinate trust; temporal and subset distributions.
6. Missing Patterns & Root Causes — missing outputs, evidence confidence, source
   attribution, deterministic samples and location-aware co-occurrence.
7. Findings & Treatment Strategy — observed issue, evidence, confidence, proposed
   action and processing owner; dynamic coverage/gaps and conservation assertions.

## Contracts and limitations

- `df_latest` remains the canonical base snapshot. `audit_frame` adds aligned raw
  evidence and calls existing Task 08–11 helpers without changing their rules.
- `missing_mask` supplies NULL/empty/whitespace semantics. Existing generic
  `data_quality` helpers use physical-null semantics only and omit missing-source
  groups, so they cannot substitute for this inventory. No new cleaning parser is
  introduced. New helpers only summarize metadata, edge intersections and review cues.
- All runtime columns are inventoried; unknown future columns stay visible as
  UNCLASSIFIED. Nullable is an observed property, not a database DDL claim.
- Empty ward candidate lists remain present evidence. Populated Boolean/status
  fields are not successes; success is measured from actual outputs or true flags.
- Street/ward/district/province are parallel branches from normalized address.
  District may come from an existing gazetteer parent; the parser does not expose
  token-level provenance. Coordinate trust has an independent dependency branch.
- Street extraction requires explicit prefixes. A number/name-only address is a
  candidate for manual review, not a confirmed parser failure. ADMIN_ONLY is an
  inferred lexical classification. Absence of a marker never proves absence of
  a real street. Samples cover each source/reason, not a random prevalence sample.
- Province regexes support selected HCMC/Hanoi forms, not all provinces or common
  HCMC spellings. Source adapter HCMC category URLs provide configuration context,
  not row-level province truth. No implicit context becomes a clean value.
- Mapping uses an internal reference. Ambiguous candidates remain unresolved.
  The existing parser may choose a first gazetteer match; parse_status is not proof
  of semantic correctness. These are processing review issues, not repaired here.
- Coordinate trust is the existing provider/range/shared-address heuristic. Shared
  conflicts are not independently verified centroids. Raw presence and trust are
  measured separately; no exact distances are calculated in EDA.
- Source representation is crawler coverage, not market share. Ward/district
  distributions describe only their available subset. No price-by-location market
  conclusions are introduced before resolving the known numeric disagreements.
- Source systems can change during scans. Existing price/area lineage gates block
  unsafe recovery; this notebook does not claim a globally immutable MySQL snapshot.

## Validation

See the validation report at the end of this document after fresh execution.

### Existing processing defects reproduced during validation

The untouched working-tree address parser fails four existing tests:

- `test_full_address`: “Phường 14, Quận 10” becomes “Phường Tân Bình”.
- `test_xa_huyen`: “Xã Phước Kiển, Huyện Nhà Bè” becomes “Xã Nhà Bè”.
- `test_ambiguous`: two explicit wards produce PARTIALLY_PARSED rather than AMBIGUOUS.
- `test_apply_address_parsing`: “Phường 2, Quận 3” becomes “Phường Tân Sơn Hòa”.

`FullTextGazetteer.add_keyword` stores a single value per lowercased alias; later
entries overwrite aliases shared across districts. Inspection of the built map
confirms “Phường 14” → “Phường Tân Bình” and “Phường 2” → “Phường Tân Sơn Hòa”, both
without parent context. `parse_status` is assigned solely from component count and
has no ambiguity branch. These failures are independent of the new audit helper.
Task 09 must resolve this before treating field population as reliable geography.
No parser/gazetteer code was changed by this refactor.

### Original saved-output execution issues

The pre-refactor notebook's saved outputs contain two errors: cell 20 passes
`color_discrete_map` to the reusable `bar` helper, whose signature does not accept
it; cell 28 reports `NameError: address_layer_labels is not defined`. The refactor
removes the redundant stacked chart and its invalid keyword, and defines each
remaining dependency in top-to-bottom order. The old file had 20 saved Plotly
figures; this is a count of saved figures, not proof of a successful prior Run All.

### Independent review

A reviewer inspected the rebuilt notebook, helper, tests and report. The review
identified an overclaim when normalized address input is empty despite decorative
raw content. The reason is now `NO_USABLE_NORMALIZED_ADDRESS`, verified by a new
regression test. This confirms only usable normalized input absence, not raw/source
absence. Remaining helper denominator, branch and conservation logic received no
substantive findings. Processing defects above remain open and unchanged.

## Latest validation status — 2026-09-28

**Implementation is ready; final live-data validation is blocked by database maintenance.**
The user confirmed maintenance is in progress. The fresh kernel stalled during
`create_analytics_connection`, with MySQL waiting on
`SELECT schema_name FROM information_schema.schemata`; unrelated existing queries
were also stalled. Only this task's waiting runner was cancelled. No other queries
were killed, no services restarted, and no Bronze/raw data changed.

- Valid notebook JSON/schema: checked with `nbformat.validate`.
- Isolated synthetic execution: all 18 code cells run in source order; six charts
  render; field/source/identity/edge/root conservation assertions pass. This
  exercises blank/normalized-only evidence, missing source, invalid coordinates,
  numeric validation and mapping outputs. **It is not live snapshot validation.**
- Relevant existing tests plus new tests: **108 passed, 4 failed**. All four failures
  are the unchanged address-parser tests described above. New helper tests: 5 pass.
- Independent review: no remaining substantive findings after the evidence-label
  correction. A further regression prevents “thành phố” from becoming a street cue.
- Changed-file whitespace check: clean. Repository-wide `git diff --check` still
  reports pre-existing whitespace in `analytics/duckdb/connection.py`,
  `crawler/src/roombeacon_crawler/sources/chothuenha/adapter.py`,
  `notebooks/docs/06_missing_patterns_and_root_causes.md`, and
  `notebooks/utils/address_parser.py`; those files were not edited by this task.
- The current notebook contains no stale or synthetic saved outputs. Current live
  field coverage, losses, source attribution and numeric disagreement counts must
  be generated by Run All once database maintenance finishes. Earlier-run numbers
  are deliberately not presented as the current snapshot.

### Remaining completion step

Run `notebooks/01_roombeacon_eda.ipynb` top-to-bottom in the repository's notebook
Python environment after MySQL is responsive. Confirm the final boundary assertions
and save the executed notebook. Its final `report` object and displayed tables
provide current coverage for every requested field, address/ward/coordinate losses,
source breakdowns, Task 11 disagreements/recoveries and structural warnings.

### Files changed by this task

- `notebooks/01_roombeacon_eda.ipynb`
- `notebooks/utils/eda_field_audit.py`
- `tests/test_eda_field_audit.py`
- `notebooks/docs/eda_field_audit_refactor.md`
