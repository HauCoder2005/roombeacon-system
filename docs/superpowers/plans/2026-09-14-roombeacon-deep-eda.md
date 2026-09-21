# RoomBeacon Deep EDA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `notebooks/roombeacon_eda.ipynb` into a reproducible, evidence-led analytical report that preserves RoomBeacon's current-state access boundary, annotates rather than destroys source truth, validates selective corrections, and exposes all analytical data loss.

**Architecture:** Keep the four frozen notebook cells byte-for-byte unchanged and begin analytical work only after `df = conn.sql("SELECT * FROM v_latest_posts").df()`. Put deterministic, reusable price, area, location, property-type-inference, reliability, and feature logic in one focused notebook utility module with unit tests; keep questions, diagnostics, plots, interpretations, limitations, and snapshot-specific conclusions in the notebook. Preserve one row per stable listing in the annotated current-state frame and use separate masks/subsets for each analytical question.

**Tech Stack:** Python 3.11+, DuckDB, Pandas, NumPy, Matplotlib, Seaborn, pytest/unittest-compatible tests, Jupyter nbformat/nbclient for execution validation.

**Spec:** User-approved RoomBeacon EDA requirements in `/home/codeser_server/.codex/attachments/cb2bfe7b-12c4-4bca-a679-7259bf6c2672/pasted-text.txt`, together with the original brief in `/home/codeser_server/.codex/attachments/bbb68ef2-daed-4fb5-9f79-870174142da1/pasted-text.txt`.

## Global Constraints

- Preserve notebook cell IDs `a5ea3203`, `a33445b4`, `5203bdfc`, and `91598f88` byte-for-byte, including their source arrays.
- Do not change `data/`, crawler code, Bronze persistence, database schemas, analytical SQL views, or the primary source selection `v_latest_posts`.
- Do not discard or overwrite pre-existing user changes in the dirty worktree.
- Treat `v_latest_posts` as one stable listing per row: latest direct price/area plus the latest confirmed address with `full_address_inherited` provenance.
- Treat `v_observations` only as auxiliary read-only evidence and as a separate historical frame.
- Assert row counts and uniqueness before and after every enrichment join into the current-state frame.
- Preserve original Bronze-derived columns and create new analytical columns; never overwrite `price_amount`, `area_value`, raw source text, or address provenance.
- Keep the quality-annotated snapshot row-preserving. Exclude records only through question-specific eligibility masks.
- Never explode ambiguous ward candidates or duplicate a stable listing.
- Treat inferred property type as `ANALYTICS_ONLY`, never as a source or production field.
- Defer lifecycle feature engineering because the inspected observation window is only a few hours and `active_days` is uniformly zero.
- Use robust statistics and always display `n` with location aggregates.
- Do not delete P99 observations solely because they are statistically extreme.
- Do not add a new analytics framework, database, or heavy plotting dependency.
- Do not commit automatically; leave the user's existing worktree and this task's changes reviewable.

## File Structure

- Create `notebooks/utils/eda_processing.py`: pure, copy-preserving analytical transformations and small aggregation helpers.
- Create `tests/test_eda_processing.py`: focused regression tests for deterministic corrections, contamination detection, join invariants, ambiguity preservation, and feature eligibility.
- Modify `notebooks/roombeacon_eda.ipynb`: retain the frozen access boundary, replace the incomplete post-load EDA with a complete report, and store freshly executed outputs.
- Keep `notebooks/utils/address_cleaner.py`, `notebooks/utils/location_normalizer.py`, and `notebooks/enums/ward_mapping.py` unchanged; reuse their existing behavior and expose its limitations.

---

### Task 1: Add tested analytical processing primitives

**Files:**
- Create: `tests/test_eda_processing.py`
- Create: `notebooks/utils/eda_processing.py`

**Interfaces:**
- Consumes: Pandas DataFrames; `clean_address()` and `normalize_location()` from existing notebook utilities.
- Produces: `correct_composite_vnd_price`, `annotate_price_quality`, `annotate_area_quality`, `infer_property_type_signal`, `derive_location_fields`, `safe_one_to_one_enrich`, `add_eligibility_masks`, `add_price_per_m2`, `summarize_processing_impact`, and `classify_sample_reliability`.

- [ ] **Step 1: Write correction and price-quality tests**

Add tests with the following exact expectations:

```python
def test_correct_composite_vnd_price_only_for_supported_pattern():
    assert correct_composite_vnd_price("1 triệu 500 nghìn", 1_000_000) == (
        1_500_000.0,
        "CORRECTED_COMPOSITE_MILLION_THOUSAND",
    )
    assert correct_composite_vnd_price("2 triệu 300 nghìn", 2_000_000) == (
        2_300_000.0,
        "CORRECTED_COMPOSITE_MILLION_THOUSAND",
    )
    assert correct_composite_vnd_price("1 triệu", 1_000_000) == (
        1_000_000.0,
        "UNCHANGED",
    )
    assert correct_composite_vnd_price("500 nghìn", 500_000) == (
        500_000.0,
        "UNCHANGED",
    )
    assert correct_composite_vnd_price("1 triệu 500", 1_000_000) == (
        1_000_000.0,
        "AMBIGUOUS_UNCHANGED",
    )
```

Also verify that `annotate_price_quality()` creates, without mutating input:

```text
price_original
price_analytical
price_quality_status
price_correction_reason
price_period_status
```

Expected statuses are `MISSING`, `INVALID_NON_POSITIVE`, `VALID_ORIGINAL`, `CORRECTED_COMPOSITE`, `PERIOD_INCOMPATIBLE_DAILY`, and `REVIEW_AMBIGUOUS`.

- [ ] **Step 2: Run the price tests and verify RED**

Run:

```bash
pytest -q tests/test_eda_processing.py -k 'price or composite'
```

Expected result: collection/import failure because `notebooks.utils.eda_processing` does not exist.

- [ ] **Step 3: Implement conservative price correction and annotation**

Implement a full-string, case-insensitive pattern that corrects only strings containing both an explicit `triệu` component and an explicit `nghìn` component. Preserve already-correct values and ambiguous formats. Detect explicit daily-period text from raw price or title and mark it incompatible for monthly comparisons without rewriting the original value.

The DataFrame annotator must return a deep copy and populate correction reasons such as:

```text
NONE
RAW_COMPOSITE_MILLION_THOUSAND
NON_POSITIVE_NUMERIC_PRICE
EXPLICIT_DAILY_PERIOD
RAW_PRICE_PRESENT_BUT_NUMERIC_MISSING
```

- [ ] **Step 4: Write area-quality tests**

Cover these exact cases:

```python
def test_confirmed_phongtro123_distance_contamination():
    row = make_row(
        source_code="phongtro123",
        title_raw="Phòng gần đại học, cách trường chỉ 800m",
        area_raw="800",
        area_value=800.0,
    )
    result = annotate_area_quality(pd.DataFrame([row]))
    assert result.loc[0, "area_quality_status"] == "CONFIRMED_CONTAMINATION"
    assert result.loc[0, "area_exclusion_reason"] == "DISTANCE_TOKEN_PARSED_AS_AREA"
    assert pd.isna(result.loc[0, "area_analytical"])

def test_large_area_without_distance_evidence_is_review_not_invalid():
    row = make_row(
        source_code="mogi",
        title_raw="Cho thuê nhà kho",
        area_raw="800 m2",
        area_value=800.0,
    )
    result = annotate_area_quality(pd.DataFrame([row]))
    assert result.loc[0, "area_quality_status"] == "SUSPICIOUS_EXTREME"
    assert result.loc[0, "area_analytical"] == 800.0
```

Also test missing, zero, negative, ordinary 25 m², and a title containing `800 m²` as a genuine area token rather than a distance token.

- [ ] **Step 5: Implement evidence-specific area annotation**

Create these columns:

```text
area_original
area_analytical
area_quality_status
area_exclusion_reason
```

Classify non-positive values as invalid. Detect confirmed PhongTro123 distance contamination only when the same numeric raw token appears in an explicit distance phrase and is not followed by `m2` or `m²`. Calculate source-specific P99 boundaries from non-missing positive values and use them only to label `SUSPICIOUS_EXTREME`; do not null or delete suspicious values.

- [ ] **Step 6: Write location and inference tests**

Verify:

- an unambiguous ward list becomes one `ward_analytical` value;
- two candidates produce `ward_mapping_status="AMBIGUOUS"` and `ward_analytical=None`;
- zero candidates produce `UNMAPPED`;
- no row is exploded;
- explicit province/district components are derived only when present in the address text;
- title signals return `ROOM_INFERRED`, `APARTMENT_INFERRED`, `HOUSE_INFERRED`, `DORMITORY_INFERRED`, `AMBIGUOUS`, or `UNCLASSIFIED`;
- source `property_type_raw` remains separate and unchanged.

- [ ] **Step 7: Implement location and inferred-type annotations**

Create:

```text
address_clean
province_analytical
district_analytical
ward_candidates
ward_candidate_count
ward_analytical
ward_mapping_status
property_type_source
property_type_inferred
property_type_inference_status
```

Use explicit address tokens for province/district. Reuse the existing ward mapping, but retain candidates as a list and emit a ward only when the candidate count is exactly one. For title inference, overlapping keyword families must result in `AMBIGUOUS`, not first-match wins.

- [ ] **Step 8: Write row-invariant and feature tests**

Test that `safe_one_to_one_enrich()` rejects duplicate right-side `rental_post_id`, preserves row count/order, and preserves unique listing count. Test masks:

```text
price_eligible
area_eligible
price_area_eligible
location_eligible
price_location_eligible
area_location_eligible
price_area_location_eligible
price_per_m2_eligible
```

Test that `price_per_m2` is created only for positive eligible analytical price and area, never for confirmed contamination or explicit daily price.

- [ ] **Step 9: Implement invariant, mask, feature, impact, and reliability helpers**

`safe_one_to_one_enrich()` must validate both sides and raise a descriptive `ValueError` before merging duplicates. `add_price_per_m2()` must preserve rows and create `price_per_m2` plus a reason field for ineligible rows. `summarize_processing_impact()` must report total, affected count, affected percentage, status/reason, and source. `classify_sample_reliability()` must consume empirical group counts and documented cut points supplied by the notebook; it must not embed a universal market threshold.

- [ ] **Step 10: Run the focused utility suite**

Run:

```bash
pytest -q tests/test_eda_processing.py
```

Expected result: all tests pass with no input mutation warnings or Pandas chained-assignment warnings.

---

### Task 2: Rebuild the notebook narrative after the frozen boundary

**Files:**
- Modify: `notebooks/roombeacon_eda.ipynb` after cell ID `91598f88`

**Interfaces:**
- Consumes: frozen `df` and `conn`, auxiliary `v_observations`, and Task 1 utilities.
- Produces: `before_cleaning`, `latest_attributes`, `quality_annotated_snapshot`, `after_cleaning`, `historical_observations`, all eligibility subsets, figures, summary tables, and written findings.

- [ ] **Step 1: Snapshot and verify frozen cells before editing**

Record the source-only hash for the four frozen cell IDs and save it outside the notebook editing path for comparison after execution. Confirm `df` remains the result of `SELECT * FROM v_latest_posts`.

- [ ] **Step 2: Retain and reorganize exact notebook content**

Retain unchanged:

- the existing title/import introduction until rewritten only where it does not touch frozen code;
- cell `a5ea3203` for project-root setup and imports;
- cell `a33445b4` for `create_analytics_connection()` and MySQL attachment assertion;
- cell `5203bdfc` for the successful-connection/table inventory;
- cell `91598f88` for `df = conn.sql("SELECT * FROM v_latest_posts").df()`.

Replace the incomplete post-load sequence—ad hoc renaming, duplicated location mapping, a ward-only boxplot, IQR helper, and destructive `dropna()`—with the ordered analytical report below. Do not retain stale stored conclusions or the misleading `print("Before:", len(df_work))` after dropping rows.

- [ ] **Step 3: Add report scope and current-row semantics**

Add Markdown and code that state:

```text
one row = one RoomBeacon stable listing identity in v_latest_posts
price/area = newest observation values
address = newest confirmed non-empty address across listing history
full_address_inherited = address provenance flag
latest-state view != cleaned Silver
```

Display snapshot timestamp, shape, column inventory, dtypes, five representative records, unique-listing invariant, source count/list, and first/latest observation timestamps.

- [ ] **Step 4: Create raw and auxiliary frames with strict cardinality checks**

Set:

```python
before_cleaning = df.copy(deep=True)
```

Load one deterministic latest row per `rental_post_id` from `v_observations` using `ROW_NUMBER() OVER (PARTITION BY rental_post_id ORDER BY observed_at DESC, observation_id DESC)` and select only raw evidence fields needed for processing:

```text
rental_post_id
price_raw
area_raw
property_type_raw
posted_at_raw
observation_id
observed_at
```

Validate one row per ID, then enrich with `safe_one_to_one_enrich()`. Assert before/after row counts and unique ID counts are identical. Load the full observation view separately into `historical_observations`; never join its repeated rows into the current-state frame.

- [ ] **Step 5: Add dataset and source-representation audit**

Show listing count and percentage by each represented source. Compare represented source codes with `source_registry.list_sources()` and list configured-but-absent sources. Phrase absence as a snapshot observation and cross-reference known capability/cooldown/access limitations without asserting an unverified cause.

- [ ] **Step 6: Add field coverage and missingness analysis**

For price, area, full address, inherited address, raw property type, timestamps, explicit province, explicit district, and unambiguous ward, calculate non-null, null, coverage percent, and unique count. Add:

- overall horizontal coverage bar chart;
- source-by-field coverage heatmap;
- price/area/location coverage-by-source grouped bars;
- Markdown `Observation / Interpretation / Caution` directly after each block.

- [ ] **Step 7: Add complete raw price-quality analysis**

Display count, missing, zero, negative, min, P01, P05, P25, median, mean, P75, P95, P99, max, and IQR. Add:

- raw histogram and log-x histogram;
- boxplot by represented source;
- source quantile table;
- raw examples for low/high tails;
- composite-price signature count and representative raw strings;
- explicit-period incompatibility examples.

Do not delete high prices because they exceed P99. Distinguish statistical extremes, deterministic composite corrections, and unresolved source/parser review cases.

- [ ] **Step 8: Add complete raw area-quality analysis**

Display the same robust statistics as price. Add:

- raw histogram and log-x histogram;
- boxplot by source;
- source quantile table;
- repeated-value frequency plot for large values;
- confirmed PhongTro123 distance-contamination examples showing title, raw area, parsed area, and source;
- suspicious-but-unconfirmed extreme examples.

Because trusted property type is unavailable, do not claim source differences are property-size market differences.

- [ ] **Step 9: Add geographic-level feasibility audit**

For `full_address_text`, explicit province, explicit district, ward candidates, and unambiguous ward, display:

```text
covered listings
coverage percent
unique groups
median group n
P25 group n
P75 group n
maximum group n
ambiguous count
```

Explain that province is useful for scope validation but cannot rank locations if all usable records are HCMC; full address is too granular; district and ward are sparse subsets. Select the deepest level only if the evidence table supports it. For this snapshot, label any ward view as `SECONDARY SUBSET ANALYSIS`, retain ambiguous rows, and never explode candidates.

- [ ] **Step 10: Add source-property-type distinction and inference audit**

Display source property-type coverage first and state that it is unavailable. Then report inferred signal coverage, class distribution, unclassified and ambiguous rates, distribution by source, and deterministic representative samples per class. Label all inferred output `ANALYTICS_ONLY`; do not use it to assert production taxonomy quality.

---

### Task 3: Apply row-preserving processing and show before/after evidence

**Files:**
- Modify: `notebooks/roombeacon_eda.ipynb` after the raw-quality sections

**Interfaces:**
- Consumes: `before_cleaning` enriched with auxiliary raw attributes and Task 1 utilities.
- Produces: `quality_annotated_snapshot`, `after_cleaning`, processing impact tables, and purpose-specific analytical subsets.

- [ ] **Step 1: Apply annotations without dropping rows**

Create `quality_annotated_snapshot` using price, area, location, and inferred-type annotators. Set:

```python
after_cleaning = add_eligibility_masks(
    add_price_per_m2(quality_annotated_snapshot)
)
```

Assert:

```python
len(before_cleaning) == len(quality_annotated_snapshot) == len(after_cleaning)
before_cleaning["rental_post_id"].nunique() == len(before_cleaning)
after_cleaning["rental_post_id"].nunique() == len(after_cleaning)
```

- [ ] **Step 2: Show the processing rule registry and impact**

Build a table with field, condition, evidence, action, affected rows, affected percentage, affected sources, and reason. Include at least:

- deterministic composite million/thousand price correction;
- missing/non-positive price ineligibility;
- explicit daily period ineligibility;
- confirmed distance-token area contamination;
- missing/non-positive area ineligibility;
- suspicious extreme review flag without automatic deletion;
- ambiguous/unmapped location ineligibility for grouped location analysis.

- [ ] **Step 3: Create price before/after comparisons**

Use identical bins/scales and side-by-side axes for original vs analytical price. Show a numerical comparison table with rows before, eligible rows, corrected rows, excluded rows, median, P95, and P99. Add affected-source and reason distributions.

- [ ] **Step 4: Create area before/after comparisons**

Use identical bins/scales and side-by-side axes for original vs analytical area. Show numeric impact and a second sensitivity comparison that distinguishes confirmed contamination removal from optional review of suspicious extremes.

- [ ] **Step 5: Create price-per-m² population funnel and distribution**

Show:

```text
all stable listings
price eligible
area eligible
price + area eligible
price-per-m² eligible
price-per-m² non-null
```

Plot the candidate original ratio separately from the eligible analytical ratio, using shared units and explicit sample sizes. Report median, P25, P75, P95, and P99; do not hide the candidate distribution.

---

### Task 4: Implement the core analytical questions and feasible features

**Files:**
- Modify: `notebooks/roombeacon_eda.ipynb`

**Interfaces:**
- Consumes: `after_cleaning` and its eligibility masks.
- Produces: location/source/type-signal aggregates, reliability labels, market-relative analytical features, and final feasibility evidence.

- [ ] **Step 1: Derive empirical sample reliability bands**

Display the distribution of group sizes for every candidate location level. Derive snapshot-specific cut points from the observed distribution and state their values in the notebook. Pass those explicit values to `classify_sample_reliability()` and label the scheme exploratory, not universal. Every ranked chart must filter or facet by reliability and print `n` in labels/tooltips/table columns.

- [ ] **Step 2: Add Price × Location subset analysis**

At the deepest usable level, calculate `n`, median, mean, P25, P75, IQR, min, max, source count, and reliability. Add:

- ranked median-price bars with `n` labels;
- P25–P75 interval plot;
- boxplots only for adequately sampled subset locations;
- adjacent listing-count chart;
- cross-source comparison table for the same locations.

State explicitly that low geographic coverage and source-dependent addresses prevent citywide market inference.

- [ ] **Step 3: Add Area × Location subset analysis**

Calculate `n`, median, mean, P25, P75, P95, P99, min, max, source count, and reliability. Add median/IQR intervals and listing counts. Use `area_eligible`, retain suspicious-review rows in the principal analysis, and show a sensitivity result without them.

- [ ] **Step 4: Add Price × Area and Price × Area × Location**

Use hexbin/density plotting for the full eligible sample and a sampled scatter only when points remain readable. Color/facet by source and inferred type only as experimental diagnostics. Add a location subset view only for statistically usable groups, with `n` and source count.

- [ ] **Step 5: Add cross-source validation**

Compare source-level coverage, median/IQR/P95/P99 for price and area, deterministic correction rates, contamination rates, inferred-type distribution, and location coverage. Phrase these as acquisition/parser/data-quality comparisons, never source market share.

- [ ] **Step 6: Create feasible analytical features**

Create and document:

```text
price_analytical
area_analytical
price_per_m2
province_analytical
district_analytical
ward_analytical
property_type_inferred
local_group_n
local_median_price
local_median_area
local_median_price_per_m2
price_vs_local_median_pct
area_vs_local_median_pct
price_per_m2_vs_local_median_pct
```

Compute local-relative features only for the empirically supported geographic level, inferred type signal when non-ambiguous, and groups meeting the documented reliability cut point. Keep feature values null otherwise. For each feature report definition, dependencies, non-null coverage, source distribution, and limitation.

- [ ] **Step 7: Validate feature distributions**

Check finiteness, positive denominators, extreme ratios, null coverage, and one-row-per-listing preservation. Plot price-per-m² and relative-feature distributions with raw/eligible sample sizes. Manually show representative high/low feature rows without claiming they are automatically erroneous or attractive.

---

### Task 5: Add historical-readiness and final decision sections

**Files:**
- Modify: `notebooks/roombeacon_eda.ipynb`

**Interfaces:**
- Consumes: `historical_observations`, `after_cleaning`, feature coverage, and processing impacts.
- Produces: historical-readiness decision, field-feasibility table, confirmed/needs-data/future findings, and limitations.

- [ ] **Step 1: Add Historical Analysis Readiness**

Display observation count, stable listing count, observation window start/end/duration, observations per listing by source, and the `active_days` distribution. State:

```text
RESULT: INSUFFICIENT TEMPORAL DEPTH
Historical feature engineering: DEFERRED_UNTIL_LONGER_HISTORY
```

Do not create listing-age, long-running-listing, time-to-rent, or lifecycle features from this snapshot. Explain that `last_observed_at` is crawler observation behavior, not a rental event.

- [ ] **Step 2: Add production-feasibility table**

For price, area, full address, district, ward, source property type, inferred property type, price-per-m², and historical features, report coverage, quality status, processing needed, cross-source consistency, feasibility (`READY`, `READY_WITH_PROCESSING`, `ANALYTICS_ONLY`, `NOT_READY`, or `DEFERRED`), feature usefulness, and major limitation. Determine final statuses from the executed evidence, not from the plan's expectations.

- [ ] **Step 3: Add analytical findings summary**

Separate:

```text
CONFIRMED BY DATA
NEEDS MORE DATA
FUTURE ENRICHMENT
```

Include snapshot-specific counts and avoid claims about market share, demand, rental completion, commuting, fees, or source quality causes that were not verified.

- [ ] **Step 4: Add reproducibility and limitations block**

Record the dataset/view names, execution timestamp, observed time range, represented sources, absent configured sources, row semantics, frozen-cell boundary, rule definitions, and the fact that a live source can change between executions. State that the report is reproducible for a database snapshot but not an immutable versioned Raw EDA publication.

---

### Task 6: Execute, verify, and review the completed work

**Files:**
- Verify: `notebooks/roombeacon_eda.ipynb`
- Verify: `notebooks/utils/eda_processing.py`
- Verify: `tests/test_eda_processing.py`
- Verify: `docs/superpowers/plans/2026-09-14-roombeacon-deep-eda.md`

**Interfaces:**
- Consumes: all implementation outputs.
- Produces: passing tests, executed notebook outputs, frozen-boundary proof, and final diff report.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest -q tests/test_eda_processing.py
```

Expected: all new tests pass.

- [ ] **Step 2: Run relevant existing regressions**

Run:

```bash
pytest -q \
  tests/test_area_normalization_and_persistence.py \
  tests/test_latest_posts_address_provenance.py \
  tests/test_runtime_persistence_and_analytics.py \
  tests/test_silver_materializer.py \
  tests/test_duckdb_paths.py
```

Expected: all selected tests pass without weakening existing assertions.

- [ ] **Step 3: Execute the notebook top-to-bottom**

Use an isolated environment outside `data/` containing the notebook's already established libraries. Execute from the repository root with a generous timeout and a kernel whose working directory preserves the frozen path-resolution behavior. Save outputs into the existing notebook only after every cell succeeds.

Verify:

- no broken cells or hidden manual-order dependency;
- all charts render;
- no secrets or connection strings appear in outputs;
- all feature columns are deterministic;
- current-state row count remains equal to the frozen `df` count;
- every location aggregation includes `n`;
- historical section reports insufficiency instead of lifecycle conclusions.

- [ ] **Step 4: Prove frozen cells are unchanged**

Recompute the source-only hash of cell IDs `a5ea3203`, `a33445b4`, `5203bdfc`, and `91598f88` and compare it with the pre-edit hash. Fail verification if any source array differs.

- [ ] **Step 5: Inspect the notebook structurally**

Use `jq`/`nbformat` to confirm cell order, unique cell IDs, absence of error outputs, non-empty Markdown interpretations after major chart blocks, and no accidental output containing passwords, DSNs, or environment values.

- [ ] **Step 6: Review git diff and working-tree isolation**

Run:

```bash
git status --short
git diff --check
git diff -- notebooks/roombeacon_eda.ipynb notebooks/utils/eda_processing.py tests/test_eda_processing.py docs/superpowers/plans/2026-09-14-roombeacon-deep-eda.md
```

Confirm no `data/`, crawler, Bronze, schema, analytical SQL, or unrelated user-modified file was changed by this task.

- [ ] **Step 7: Prepare the completion report**

Report documentation reviewed, actual executed snapshot, row meaning, frozen cells, notebook sections/charts, quality findings, before/after impacts, feature definitions/coverage/limitations, exact test commands/results, and unresolved risks.
