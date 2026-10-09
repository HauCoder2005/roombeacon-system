> **ARCHIVED** — superseded by [PRICE_MODEL.md](../../05-analytics-ml/PRICE_MODEL.md).

# RoomBeacon Data Correctness and Modeling Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate numeric lineage from semantic/model suitability, harden area parsing, audit administrative consistency, regenerate Silver, and rerun the unchanged modeling benchmark.

**Architecture:** Preserve every Bronze row and every raw value in Silver. Append parser provenance, semantic suitability, administrative consistency, and model-eligibility fields; the modeling notebook consumes those fields through an explicit funnel and compares permissive versus strict development populations without reusing the historical sealed test for champion selection.

**Tech Stack:** Python 3.12, pandas, DuckDB, pytest, Jupyter notebooks, scikit-learn/LightGBM/CatBoost/XGBoost.

**Spec:** `/home/codeser/.codex/attachments/e2b14dde-7f7d-4b8b-9775-aa97139162d8/Pasted text.txt`

## Global Constraints

- Preserve all canonical Silver rows and raw lineage.
- Do not use global magnitude or IQR thresholds as business-validity rules.
- Do not reduce model families, folds, transforms, feature sets, or benchmark scope.
- Do not use the historical sealed test to re-select a champion.
- Modify notebook helpers/builders and regenerate generated notebooks.
- Preserve unrelated working-tree changes.

## Review Focus

- Single linear measurements must never become area while explicit and two-dimensional evidence must remain supported.
- Lineage-trusted prices with insufficient ordinary-room rent evidence must remain in Silver but not become model targets.
- Legitimate high monthly rent must remain supported when cadence and scope evidence are strong.
- Administrative consistency must distinguish mismatch from ambiguous/unverifiable evidence without rewriting fields.
- Eligibility and sensitivity comparisons must use group-aware chronological development folds without test leakage.

---

### Task 1: Reproduce and capture current-data failures

**Files:**
- Create: `data/modeling/roombeacon_correctness_audit/` artifacts

**Interfaces:**
- Consumes: current Silver and Bronze snapshot parquet files.
- Produces: reproducible area, price, UNKNOWN, and admin audit tables used by later verification.

- [ ] Query real anomaly families and identify parser/root-cause functions.
- [ ] Persist concise audit CSV/JSON artifacts without modifying canonical data.
- [ ] Verify counts against current Silver.

### Task 2: Harden area evidence and Silver suitability contracts

**Files:**
- Modify: `notebooks/utils/price_area_validation.py`
- Modify: `notebooks/utils/silver_processing.py`
- Modify: `tests/test_price_area.py`
- Modify: `tests/test_silver_processing.py`

**Interfaces:**
- Produces: area parser evidence classification and `area_semantic_status` / `area_model_suitability` Silver fields.

- [ ] Add failing tests for height, single width/length, dimensions, and explicit area.
- [ ] Verify RED.
- [ ] Implement minimal evidence-aware parser and Silver status fields.
- [ ] Verify GREEN and existing regression coverage.

### Task 3: Separate price lineage from model suitability

**Files:**
- Modify: `notebooks/utils/price_area_validation.py`
- Modify: `notebooks/utils/silver_processing.py`
- Modify: `tests/test_price_target_trust.py`
- Modify: `tests/test_listing_semantics.py`

**Interfaces:**
- Produces: `price_semantic_status`, `price_model_suitability`, and suitability-gated `price_model_value` while retaining lineage status/evidence.

- [ ] Add failing tests for unsupported extreme ordinary-room price and supported legitimate high rent.
- [ ] Verify RED.
- [ ] Implement evidence-based semantic suitability independent of magnitude-only rules.
- [ ] Verify GREEN and existing cadence/role regressions.

### Task 4: Add ward/district consistency audit

**Files:**
- Modify: `notebooks/utils/ward_normalization.py`
- Modify: `notebooks/utils/silver_processing.py`
- Modify: `tests/test_ward_normalization.py`

**Interfaces:**
- Produces: deterministic `admin_consistency_status`, reason, and candidates without rewriting location truth.

- [ ] Add failing tests for consistent, inconsistent, ambiguous, and unverifiable pairs.
- [ ] Verify RED.
- [ ] Implement mapping-backed audit fields.
- [ ] Verify GREEN.

### Task 5: Rebuild modeling eligibility and UNKNOWN sensitivity

**Files:**
- Modify: `notebooks/utils/modeling_benchmark.py`
- Modify: `notebooks/utils/build_modeling_notebook.py`
- Modify: `tests/test_modeling_benchmark.py`

**Interfaces:**
- Consumes: Silver semantic/suitability fields.
- Produces: explicit eligibility funnel plus permissive/strict development comparison under unchanged splitting and metrics.

- [ ] Add failing model-contract tests.
- [ ] Verify RED.
- [ ] Implement eligibility masks, funnel, and sensitivity artifacts.
- [ ] Verify GREEN.

### Task 6: Regenerate data and notebooks, execute full benchmark

**Files:**
- Regenerate: `notebooks/02_roombeacon_silver.ipynb`
- Regenerate: `notebooks/03_roombeacon_processing.ipynb`
- Regenerate: `notebooks/04_roombeacon_modeling.ipynb`
- Regenerate: `data/silver/rental_listings.parquet`
- Regenerate: modeling benchmark artifacts

**Interfaces:**
- Consumes: all hardened helpers/builders.
- Produces: clean sequential notebook execution and refreshed auditable evidence.

- [ ] Identify and run canonical notebook builders.
- [ ] Execute notebooks 02 → 03 → 04 at full scope.
- [ ] Verify no saved traceback/error outputs.
- [ ] Run relevant tests and full pytest suite.
- [ ] Produce final before/after audit report.
