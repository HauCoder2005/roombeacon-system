> **ARCHIVED** — superseded by [SILVER_CONTRACT.md](../../04-processing/SILVER_CONTRACT.md).

# RoomBeacon Processing and Canonical Silver Design

## Purpose

Restructure the canonical RoomBeacon notebooks and implement one deterministic,
source-preserving Silver pipeline that transforms the latest Bronze snapshot
into the canonical DuckDB table `silver.rental_listings`. The existing
`rental_latest.parquet` remains a deprecated temporary compatibility mirror and
is exported only from the committed canonical table.

Silver creation stops after materialization. Post-Silver analytical preparation
belongs only to `03_roombeacon_processing.ipynb`; model fitting belongs only to
`04_roombeacon_modeling.ipynb` if existing model work must be promoted from its
current location. This task does not build Gold or expand model research.

## Canonical Notebook Architecture

```text
01_roombeacon_eda.ipynb
  -> 02_roombeacon_silver.ipynb
  -> DuckDB silver.rental_listings
  -> 03_roombeacon_processing.ipynb
  -> optional 04_roombeacon_modeling.ipynb
```

- `01_roombeacon_eda.ipynb` remains the accepted, read-only Bronze audit and
  processing specification.
- The current `02_roombeacon_processing.ipynb` is moved—not copied—to
  `03_roombeacon_processing.ipynb`, then stripped of Bronze-cleaning and Silver
  publication responsibilities.
- A new `02_roombeacon_silver.ipynb` becomes the only Bronze-to-Silver notebook.
- `03_roombeacon_processing.ipynb` reads only `silver.rental_listings` and
  prepares analytical/model-ready data without fitting models or recreating
  Silver.
- The current canonical Processing notebook contains no model training. The
  existing modeling work is already isolated under `notebooks/drafts/`, so this
  refactor does not create a placeholder `04_roombeacon_modeling.ipynb`.

## Scope and Constraints

- Keep `01_roombeacon_eda.ipynb` unchanged; it is the analytical specification.
- Rename the existing `02_roombeacon_processing.ipynb` to
  `03_roombeacon_processing.ipynb` using repository move semantics.
- Create exactly one `02_roombeacon_silver.ipynb` for Bronze-to-Silver work.
- Do not leave `02_roombeacon_processing.ipynb` behind after the move.
- Preserve one row per `rental_post_id` throughout processing and publication.
- Preserve all Bronze-derived columns exactly and add clean/status fields beside
  them.
- Never impute, overwrite, delete, merge, or silently accept ambiguous evidence.
- Reuse existing text, address, ward, numeric-validation, and coordinate helpers.
- Add focused deterministic helpers only where the current repository has a
  genuine gap.

## Considered Approaches

### Recommended: Python processing contract plus transactional DuckDB publisher

Build the processed DataFrame with tested Python helpers, run an explicit
Pre-Silver gate, then register the gated frame in the persistent DuckDB catalog
and transactionally replace `silver.rental_listings`. After commit and read-back
verification, export Parquet from the canonical table.

This approach reuses the repository's parser logic, makes row-level rules easy
to test, and establishes DuckDB as the single source of truth without breaking
the legacy Parquet consumer.

### Rejected: notebook-only transformation and writes

Keeping rules in notebook cells would make rebuilds depend on hidden kernel
state and make quality-gate behavior difficult to test independently.

### Rejected: SQL-only Silver transformation

SQL would simplify table replacement, but it would duplicate or bypass the
canonical Python text, address, ward, and numeric parsing helpers.

## Component Boundaries

### Processing contract module

A focused module under `notebooks/utils/` owns deterministic row annotations:

- title quality;
- address quality;
- final price and area status/value selection from existing numeric audits;
- snapshot-derived numeric outlier flags;
- coordinate quality classification;
- price-area and location consistency;
- blocked duplicate/repost candidates;
- temporal quality;
- final processing status;
- Pre-Silver invariant validation.

Functions accept DataFrames and return copies or explicit audit results. They do
not connect to databases and do not write files.

### Silver notebook

`02_roombeacon_silver.ipynb` orchestrates the canonical helpers in this order:

1. Runtime snapshot and contract
2. General text standardization
3. Title quality
4. Address standardization and parsing
5. Administrative mapping
6. Price validation
7. Area validation
8. Numeric outlier flags
9. Coordinate trust classification
10. Cross-field consistency
11. Duplicate/repost candidates
12. Temporal validation
13. Final processing status
14. Pre-Silver quality gate
15. Silver materialization

The Silver notebook contains no reference-location configuration, radius
summaries, local price bands, product candidate search, analytical feature
engineering, or model logic. It connects to the configured persistent DuckDB
catalog rather than `:memory:` for canonical publication.

### Post-Silver processing notebook

After the repository move, `03_roombeacon_processing.ipynb` begins with a
runtime assertion that `silver.rental_listings` exists and loads that table at
one-row-per-`rental_post_id` grain. It must not query `v_latest_posts`, raw
evidence tables, or MySQL Bronze.

Its permitted responsibilities are limited to downstream preparation:

- explicit eligibility masks based on Silver statuses;
- price-per-area and other deterministic analytical variables;
- trusted-coordinate-only location features when a real reference is supplied;
- categorical/model-ready column preparation;
- train/validation/test preparation without fitting or evaluating models.

The current radius market summaries, local price-band charts, and product-style
candidate table are removed. Generic distance helpers may remain in utilities,
but the canonical Processing notebook uses them only for an explicitly
configured trusted-coordinate feature, never as Silver cleaning or market
analysis. The notebook does not persist Gold in this task.

### Modeling notebook decision

No `model.fit`, `model.predict`, cross-validation, or evaluation code exists in
the current canonical Processing notebook. Existing modeling code is already in
`notebooks/drafts/03_experimental_price_modeling.ipynb`. Therefore this refactor
does not create `04_roombeacon_modeling.ipynb`; promoting that draft is a later,
separately reviewed task.

### Silver materializer

Refactor `SilverMaterializer` so its canonical operation accepts the gated
processed DataFrame and publishes `silver.rental_listings` transactionally.

Publication flow:

```text
processed_df
  -> Pre-Silver Quality Gate
  -> BEGIN TRANSACTION
  -> CREATE SCHEMA IF NOT EXISTS silver
  -> replace silver.rental_listings from registered gated frame
  -> validate canonical table grain, identity, rows and columns
  -> COMMIT
  -> read canonical table
  -> export rental_latest.parquet.tmp
  -> validate mirror contract against canonical table
  -> atomically replace rental_latest.parquet
  -> write compatibility metadata
```

Any failure before the DuckDB commit rolls back and leaves both the previous
canonical table and Parquet mirror unchanged. A mirror failure after canonical
commit leaves the new canonical table intact and the previous mirror intact;
the operation reports a compatibility-export failure rather than rolling back
the already-validated source of truth.

The mirror is always read from `silver.rental_listings`, never independently
from the in-memory processed DataFrame.

## Row-level Processing Contract

### Text and title

- `title_raw` remains unchanged.
- `title_normalized` uses existing conservative NFC, invisible/control,
  decorative-icon, whitespace, punctuation, and empty-to-null logic.
- `title_quality_status` is one of:
  `VALID_DESCRIPTIVE`, `MISSING`, `VERY_SHORT`, `NUMERIC_ONLY`,
  `ROOM_CODE_LIKE`, `REQUIRES_REVIEW`.
- No property-type inference is persisted.

### Address and administrative location

- Preserve `best_address_text`.
- Persist `best_address_text_normalized` and actual parser outputs:
  `street_text_extracted`, `ward_text_extracted`,
  `district_text_extracted`, `province_text_extracted`, `parse_status`.
- Persist `ward_normalized`, `ward_current`, and `ward_mapping_status` from the
  existing mapping helper.
- `AMBIGUOUS` and `UNMAPPED` must have null `ward_current`.
- `address_quality_status` uses deterministic length/content evidence:
  `ADDRESS_OK`, `ADDRESS_INSUFFICIENT`, `ADDRESS_TOO_SHORT`,
  `ADDRESS_DESCRIPTION_CONTAMINATION`, `ADDRESS_REQUIRES_REVIEW`.
  The field flags evidence and never guesses a replacement address.

### Price and area

Reuse `validate_numeric_candidates` and preserve its raw, existing, reparsed,
lineage, semantic, action, and regression evidence where required for audit.

- `price_amount_clean` and `area_value_clean` come only from the existing
  `clean_candidate` contract.
- `price_validation_status` and `area_validation_status` distinguish validated
  existing values, accepted deterministic reparses, missing/semantic nulls,
  invalid values, lineage failures, and parser disagreements.
- Negotiable price remains null with semantic status.
- Parser disagreement never overwrites an existing value.

### Statistical outliers

Outlier thresholds are deterministically derived from positive clean candidates
in the current snapshot and recorded in the run summary. Each field uses
P01/P99.9 and the upper 1.5-IQR fence with precedence:

1. `MISSING_OR_UNUSABLE`
2. `SUSPICIOUS_LOW`
3. `EXTREME_HIGH`
4. `HIGH_IQR_OUTLIER`
5. `NORMAL`

Outliers remain in Silver; flags never null or delete them.

### Coordinate quality

Reuse `audit_coordinate_trust` for pair validity, provider evidence, shared-point
counts, conflicting addresses, and search eligibility. Extend the deterministic
annotation to include distinct current wards and sources for each rounded pair.

`coordinate_quality_status` uses:
`NO_COORDINATE`, `INVALID_RANGE`, `UNIQUE_COORDINATE`,
`SHARED_SAME_LOCATION`, `SHARED_MULTIPLE_ADDRESSES`,
`SHARED_MULTIPLE_WARDS`, `HEAVILY_SHARED_COORDINATE`, `REQUIRES_REVIEW`.

`coordinate_search_usable` is true only when the existing helper marks the pair
trusted. No user distance or radius is calculated.

### Cross-field consistency

`price_area_status` uses clean candidates and snapshot thresholds:
`CONSISTENT`, `MISSING_PRICE`, `MISSING_AREA`,
`MISSING_PRICE_AND_AREA`, `EXTREME_PRICE_PER_AREA`,
`LOW_PRICE_LARGE_AREA_REVIEW`, `HIGH_PRICE_SMALL_AREA_REVIEW`,
`REQUIRES_REVIEW`.

`location_consistency_status` uses only parser, ward mapping, and coordinate
evidence:
`RESOLVED`, `ADDRESS_PRESENT_WARD_UNRESOLVED`,
`WARD_RESOLVED_COORDINATE_MISSING`, `COORDINATE_SHARED_REVIEW`,
`COORDINATE_ADMIN_CONFLICT`, `INSUFFICIENT_LOCATION`.

No expected-rent model or fabricated administrative relationship is introduced.

### Duplicate/repost candidates

Candidate blocking never compares missing values and never uses shared
coordinates alone. Two conservative rules are supported:

1. normalized address + clean price + clean area;
2. normalized title + clean price + current ward.

Only blocks containing at least two listings are candidates. Metadata includes
`duplicate_status`, deterministic `duplicate_group_id`,
`duplicate_group_size`, `duplicate_scope` (`SAME_SOURCE` or `CROSS_SOURCE`),
and `duplicate_match_reason`. Rows are not merged or deleted. When a row belongs
to multiple candidate blocks, the stronger address-price-area rule takes
precedence; other evidence is retained in the match reason.

### Temporal semantics

The crawler currently overwrites `last_observed_at` on duplicate-key updates,
so out-of-order observations can make it earlier than `first_observed_at`.
Processing preserves all timestamps and uses:

- `CONSISTENT` when chronological invariants hold;
- `REQUIRES_REVIEW` when first/last/latest relationships conflict;
- `MISSING_TEMPORAL_EVIDENCE` when required timestamps are absent.

It does not claim verified backfill semantics and does not reorder timestamps.

### Final processing status

No numeric quality score is created.

- `INSUFFICIENT_CRITICAL_DATA`: missing/invalid source identity or no usable
  title plus no usable location evidence.
- `REQUIRES_REVIEW`: ambiguous/unmapped location truth, parser disagreement,
  invalid numeric evidence, temporal conflict, coordinate/admin conflict, or
  other deterministic hard-review state.
- `READY_WITH_FLAGS`: usable record with non-blocking missing fields, outliers,
  shared-coordinate review, or duplicate candidate metadata.
- `READY`: critical identity and processing contracts pass without flags.

## Silver Contract

The table grain is exactly one current analytical representation per
`rental_post_id`. It preserves raw identity/source fields and includes the
canonical clean/status fields required by the task, but excludes transient
chart, sample, and helper columns.

Core groups are:

- identity/source: `rental_post_id`, `source_code`, `source_listing_id`, `url`;
- title: raw, normalized, quality status;
- price and area: source values/evidence when available, clean values,
  validation and outlier statuses;
- address/admin: raw best address, normalized address, parser fields, ward
  lineage, mapping status, address quality status;
- coordinates: source coordinates/provider, quality status, search usability;
- cross-field, duplicate, and temporal statuses;
- lineage: `processing_status`, `processing_run_id`, `processing_version`,
  `processed_at`.

The exact column list is a versioned constant tested by the quality gate and
materializer. Temporary baselines, visualization labels, and intermediate masks
are excluded.

## Pre-Silver Quality Gate

The gate raises a dedicated exception and blocks all publication unless every
invariant passes:

1. non-empty output;
2. row count equals source snapshot row count;
3. `rental_post_id` is non-null and unique;
4. `source_code` and `source_listing_id` are non-null and unchanged;
5. all declared raw/source columns equal the frozen input snapshot;
6. no row multiplication or deletion;
7. text normalization is idempotent;
8. non-null clean numeric values are positive and have accepted validation
   statuses;
9. ambiguous/unmapped wards do not produce `ward_current`;
10. invalid coordinate pairs are never search usable;
11. duplicate-candidate rows remain present and at listing grain;
12. statistical outliers remain present and flagged;
13. no unsupported imputation appears;
14. every status value belongs to its documented enum;
15. output columns exactly match the versioned Silver contract.

The gate returns an auditable PASS table for notebook display and tests.

## Materialization and Compatibility Guarantees

`silver.rental_listings` is the canonical Silver dataset.

`rental_latest.parquet` is a deprecated temporary compatibility mirror.

Canonical read-back validation checks table existence, exact columns, row count,
distinct/non-null `rental_post_id`, and source identity. Mirror validation checks
the same row count, unique/distinct IDs, and exact canonical columns. Values are
read from the canonical table to create the mirror.

The materializer never calls Parquet a source of truth and never refreshes it
when canonical DuckDB publication fails.

## Testing Strategy

Use the existing pytest/unittest style and add focused tests for:

- title and address quality states;
- price/area finalization and disagreement fail-closed behavior;
- outlier precedence without row removal;
- coordinate quality and search usability;
- cross-field statuses;
- deterministic duplicate blocks and scope;
- temporal conflicts;
- final processing status;
- raw immutability, row conservation, status enums, and full Pre-Silver gate;
- transactional canonical-table publication and rollback;
- mirror ordering after canonical commit;
- canonical/mirror row, grain, and column equality;
- notebook structure proving wrong-layer analytics and feature engineering were
  removed from Silver;
- notebook architecture proving the old `02_roombeacon_processing.ipynb` no
  longer exists, `02_roombeacon_silver.ipynb` owns Bronze cleaning, and
  `03_roombeacon_processing.ipynb` reads only canonical Silver;
- repository references updated for the new canonical notebook names without
  rewriting intentional historical references.

Existing text, address, ward, numeric, location, and Silver tests remain part of
regression verification. Known unrelated crawler import failures are reported
separately rather than classified as Processing regressions.

## Failure Behavior

- Processing-rule or quality-gate failure: no DuckDB or Parquet mutation.
- DuckDB transaction failure: rollback; previous table and mirror remain.
- Canonical read-back failure: rollback before commit where possible; otherwise
  report a materialization failure and do not export mirror.
- Parquet export/read-back failure after canonical commit: canonical table stays
  valid, previous mirror remains, and the compatibility failure is explicit.
- Notebook runtime failure: stop before materialization and surface the failing
  stage.

## Completion Boundary

Success is a fully executed `02_roombeacon_silver.ipynb`, a passing Pre-Silver
gate, a validated persistent `silver.rental_listings`, a matching compatibility
Parquet mirror, and a fully executed `03_roombeacon_processing.ipynb` whose only
input is canonical Silver. The old `02_roombeacon_processing.ipynb` is absent.
No canonical `04` is created because model code is not mixed into the current
Processing notebook. The task stops after reporting those artifacts and tests.
