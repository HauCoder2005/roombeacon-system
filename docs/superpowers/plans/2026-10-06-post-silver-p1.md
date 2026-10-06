# Post-Silver Platform P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing 132,436-row Silver notebook pipeline into an installable, snapshot-only production package and an Asset-driven Airflow DAG without changing its ordered 80-column output.

**Architecture:** `roombeacon_processing` owns deterministic Bronze-snapshot-to-Silver transformations. Notebook modules become compatibility re-export shims. A pure application service loads only validated Parquet snapshots and atomically publishes Silver; Airflow supplies orchestration and Assets but no transformation logic.

**Tech Stack:** Python 3.11+, pandas, NumPy, DuckDB, PyArrow/Parquet, Airflow 3 Assets, pytest.

**Spec:** `AGENTS.md`, `architecture/overall-architecture.pdf`, and the user-approved P0 design in this task.

## Global Constraints

- Do not modify frozen crawler paths or storage-plane modules.
- Do not read MySQL except in the dedicated future Bronze snapshot DAG; P1 Silver reads Parquet only.
- Preserve notebooks 01-07 through re-export shims.
- Preserve exactly 132,436 rows, 80 ordered columns, values, dtypes, and deterministic row hashes for the current fixture.
- Keep the LightGBM/RAW/F4 champion unchanged.
- Do not run production containers or databases; use local fixtures.
- Stage only P1 files and commit each task separately; never push.

## Review Focus

- Missing/corrupt snapshot metadata must fail closed before publication.
- A failed build must leave the previous canonical Silver and metadata intact.
- Notebook imports and public function/class identities must remain compatible.
- Nullable/string/decimal/timestamp values must hash deterministically across Parquet roundtrips.
- Airflow import must not connect to MySQL, load Parquet, or perform other runtime work.

---

### Task 1: Installable processing package and notebook compatibility

**Files:**
- Create: `processing/pyproject.toml`
- Create: `processing/src/roombeacon_processing/{__init__,text_standardization,address_parser,ward_normalization,price_area_validation,listing_semantics,location_analysis,numeric_validation,silver}.py`
- Modify: corresponding `notebooks/utils/*.py` files into re-export shims
- Test: `tests/processing/test_package_compatibility.py`

**Interfaces:**
- Produces: `roombeacon_processing.silver.build_silver_dataset` and `evaluate_pre_silver_quality_gate`; existing `notebooks.utils.*` imports resolve to the same objects.

- [ ] Write compatibility/import tests and verify RED because the package does not exist.
- [ ] Move the current implementations into focused package modules; keep notebook shims.
- [ ] Install editable package locally and run compatibility plus existing Silver utility tests GREEN.
- [ ] Commit package and shims.

### Task 2: Golden Silver contract and deterministic hashing

**Files:**
- Create: `processing/src/roombeacon_processing/contracts.py`
- Create: `processing/src/roombeacon_processing/golden.py`
- Create: `tests/processing/test_silver_golden.py`
- Create: `tests/fixtures/silver_golden_manifest.json`

**Interfaces:**
- Produces: `SilverContract`, `hash_silver_rows(frame) -> list[str]`, and a manifest recording fixture input hashes, 132,436 rows, and the ordered 80-column schema.

- [ ] Write contract/hash tests and verify RED.
- [ ] Implement stable null/type canonicalization and SHA-256 row hashing.
- [ ] Build from `data/bronze/snapshot`, compare with legacy `data/silver/rental_listings.parquet`, and stop if any unexplained mismatch exists.
- [ ] Persist only the compact golden manifest, run tests GREEN, and commit.

### Task 3: Snapshot-only Silver application service and atomic publication

**Files:**
- Create: `processing/src/roombeacon_processing/build.py`
- Modify: `analytics/silver/materializer.py`
- Test: `tests/processing/test_silver_build.py`
- Test: `tests/test_silver_materializer.py`

**Interfaces:**
- Produces: `build_silver(snapshot_dir: Path, output_dir: Path) -> SilverBuildResult` with source snapshot ID/hashes, runtime, row/column counts, output SHA-256, schema and processing versions.

- [ ] Write tests proving no MySQL connector is used, metadata/hash validation is mandatory, and failed publication preserves prior files; verify RED.
- [ ] Implement snapshot load, transform, gate and two-file rollback-safe publication with ZSTD and explicit row-group size.
- [ ] Run focused tests GREEN and commit.

### Task 4: Diagnose and replace the failing DAG

**Files:**
- Create: `airflow/dags/analytics/roombeacon_silver_build.py`
- Remove: `airflow/dags/analytics/roombeacon_silver_materializer.py`
- Create: `tests/test_silver_build_dag.py`

**Interfaces:**
- Consumes: Airflow Asset `bronze_snapshot` and `build_silver(...)`.
- Produces: Asset `silver_rental_listings`; DAG ID `roombeacon_silver_build`.

- [ ] Capture the local-log root cause in the test/module documentation: repeated SIGKILL/OOM after direct MySQL ATTACH/materialization.
- [ ] Write static/import-safe DAG contract tests and verify RED.
- [ ] Implement Asset schedule/outlet, `catchup=False`, `max_active_runs=1`, timeouts, retry backoff, and `duckdb_analytics_pool`; no MySQL imports or connection calls.
- [ ] Run DAG contract tests GREEN and commit.

### Task 5: Benchmark and optimize verified hotspots

**Files:**
- Create: `benchmarks/benchmark_silver_build.py`
- Modify: processing modules only where profiling proves a hotspot
- Create/modify: focused performance-equivalence tests under `tests/processing/`

**Interfaces:**
- Produces: machine-readable baseline/optimized runtime and peak RSS; output still passes Task 2 hashes.

- [ ] Benchmark current package once on the fixed snapshot, recording runtime/RSS without writing production output.
- [ ] Profile and select the largest proven hotspot (expected address/ward row-wise application).
- [ ] Write an equivalence test, verify RED for the new vectorized/batched interface, implement one optimization, and re-run golden tests.
- [ ] If needed, try one second evidence-backed optimization; stop and ask if the performance goal remains unmet.
- [ ] Record before/after benchmark JSON and commit.

### Task 6: P1 verification and handoff

**Files:**
- Modify only P1 tests/plan ledger if verification reveals a defect.

**Interfaces:**
- Produces: a verified P1 branch state ready for P2.

- [ ] Run all processing/Silver/DAG tests, then bare `pytest`; report pre-existing failures separately.
- [ ] Verify notebook imports, 132,436 × 80 golden output, metadata/hash integrity, and frozen-area diff.
- [ ] Review the complete P1 diff for security, performance, compatibility, and secret leakage.
- [ ] Commit only necessary fixes and report commits, benchmarks, and open risks.
