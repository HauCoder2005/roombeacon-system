# Clean-clone recovery audit — 2026-09-16

## Verdict and scope

**NOT REPRODUCIBLE** under the strict `git clone + valid configuration + docker compose up` contract as currently supplied. The existing working tree can generate new committed data and complete reconciliation and Silver. That is not proof that a clean checkout reproduces the repaired runtime.

Inspected commit: `dc7d110460c3ad5d455de87fa5a5d731101863a3`, branch `main`. At audit entry there were 40 modified tracked files, plus untracked work. In particular, bounded XCom, ingestion and aggregate-idempotency repairs were working-tree modifications. No commit, push, service restart or schema change was performed. One subsequently proven reporting defect was corrected after RED evidence, as recorded below.

No clean empty-volume deployment was performed: existing evidence was preserved. Current runtime success must not be presented as an empty-machine integration test.

## What Git restores and what it does not

Tracked construction inputs include `docker-compose.yml`, `airflow/Dockerfile`, `crawler/Dockerfile`, `processing/Dockerfile`, `crawler/pyproject.toml`, Airflow DAGs, crawler configuration/source, MySQL schema/repositories, `infrastructure/minio/bootstrap.sh` and its policy, `analytics/duckdb/` bootstrap/views, Silver materializer, `.env.example`, README and infrastructure documentation. `Makefile` exists but is empty.

`data/` runtime content is ignored apart from `.gitkeep`: MySQL data, MinIO objects, Bronze artifacts, manifests, checkpoints, DuckDB catalogs and Parquet are not restored by Git. Airflow logs are also not restored. A generated authentication-password file is tracked under `airflow/config/`; its contents were deliberately not inspected.

**Proven old-machine losses: none established by this audit.** The current machine has populated databases, objects and artifacts. Their provenance does not prove which old-machine data survived. No backup was validated for historical recovery.

## Bootstrap dependency inventory

| Runtime dependency | Definition tracked? | Automatic creation | Extra requirement / limitation |
|---|---|---|---|
| Bronze database | Yes, Compose MySQL configuration | Official MySQL initialization | Valid configuration; persistent directory writable |
| Bronze business schema | Yes, `infrastructure/mysql/schema.py` | Persistence and reconciler call idempotent schema creation | Deferred until an application task runs |
| Platforms | Yes, platform repository | Created on first source persistence | Not a static seed of every adapter; 9 rows is not missing bootstrap evidence |
| Airflow metadata schema | Yes | `airflow-init`: `airflow db migrate` | Successful database health and writable Airflow bindings |
| Airflow configuration / pool | Yes | Environment wiring; init creates single-writer DuckDB pool | Supply secrets and activate DAGs; no Airflow Connection records required by these direct application clients |
| MinIO buckets / crawler identity | Yes | `minio-bootstrap`, scheduler waits for successful completion | Policy resources use canonical bucket names |
| Local Bronze / manifests / quarantine | Yes | Writer creates subdirectories on demand | Configured root must be writable; fallback can otherwise place files under container working directory |
| DuckDB extension / views | Yes | Runtime installs/loads MySQL extension and creates views | Network access for initial extension install, writable catalog/temp directory, Bronze schema available |
| Checkpoints / seen IDs | Yes | Local repository creates state directories; missing state returns None/empty | Writable persistent root; no old checkpoint required |
| Silver / Parquet | Yes | Materializer creates output directory | Writable root and operational analytical views |

The template sets `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true`: starting services alone does not start ingestion. DAG activation is an additional operator action. `AIRFLOW_UID=1000` in the template also requires matching host permissions; Compose has no init step that prepares ownership of the data/log/config bindings for a different host UID. Current paths are writable, but that existing ownership is not a portable Git property.

The infrastructure guide describes named volumes, while current Compose and runtime use bind mounts. It also describes a narrower MinIO policy than the tracked policy actually grants. Dependency ranges and `minio/mc:latest` do not produce a bit-for-bit locked build.

## Current Docker and filesystem evidence

Both MySQL containers use `mysql:8.4`; MinIO uses `minio/minio:latest`; Airflow uses `roombeacon-airflow-custom:3.3.1`. All inspected running services had restart count 0. Both MySQL services, MinIO, scheduler and API server reported healthy. DAG processor and triggerer were running and their Airflow health entries were healthy. Init and MinIO-bootstrap containers exited 0.

Published loopback ports: Bronze 3307→3306; metadata 3308→3306; MinIO 9000/9001; Airflow API 8080.

Bronze, metadata and object data are **bind mounts**, not anonymous or named Docker volumes. No RoomBeacon named volume appeared in `docker volume ls`.

MySQL and Airflow bindings use `/home/codeser_server/Data/projects/roombeacon/source/roombeacon-system/...`; MinIO uses `/data/projects/roombeacon/source/roombeacon-system/data/minio`. The former repository path resolves to the latter checkout. These prefixes are not evidence of two different data roots.

Airflow mounts the data root at `/data`, DAGs at `/opt/airflow/dags`, crawler source read-only at `/opt/roombeacon/crawler/src`, and analytics read-only at `/opt/roombeacon/analytics`. Scheduler belongs to both data and orchestration networks; API, processor and triggerer use the orchestration network.

In scheduler: `/data`, `/data/bronze`, `/data/state`, `/data/silver`, `/opt/airflow/logs` and `/opt/airflow/config` existed, were writable and reported owner 1000:0. `/data/raw`, `/data/exports` and `/data/quarantine` were absent. Raw objects are mirrored to MinIO; quarantine directories are created when needed. Their absence alone is not a startup failure.

All four canonical MinIO bucket directories exist. Crawler credentials can HEAD the assets bucket. HEAD on raw/quarantine/exports returns 403; the configured policy only grants bucket listing for assets and object Get/Put for assets/raw. Those 403 responses are not evidence of nonexistent buckets. Successful Stage 05 also exercises raw mirroring.

## Runtime code identity

**Airflow executes the current host source: YES** for all seven checked files. SHA-256 hashes matched between host and scheduler for:

- Bronze reconciler DAG and crawler DAG;
- checkpoint orchestration;
- observation and rental-post repositories;
- PhongTro123 listing parser;
- asset reconciler service.

This proves host-working-tree/runtime agreement, not agreement with committed HEAD. No stale-code restart was justified.

## Airflow error classification and XCom

Supported `airflow db check` and `airflow db check-migrations --migration-wait-timeout 10` passed. API health reported healthy metadata, scheduler, triggerer and processor. Fresh task execution and XCom resolution passed.

The supplied `qRqnePms` diagnostic ID and sort-memory error were not present in the retained API-container logs searched in this audit. An exact traceback for that ID cannot be reconstructed from the available current logs.

Earlier session evidence established the now-superseded error as `MySQLdb.OperationalError (1038, 'Out of sort memory, consider increasing server sort buffer size')` in Airflow metadata, selecting XCom values through `XComModel.get_many` with an ordered `dag_run` join. This was not a Bronze transaction error. Historical payload: 270,822 bytes versus a 262,144-byte sort buffer. No memory tuning was performed.

| Run | Classification | Result |
|---|---|---|
| Pre-fix 2026-09-15 large-XCom runs | HISTORICAL / SUPERSEDED | Prior failures retained |
| `manual__xcom_bounded_20260915T1946Z` | HISTORICAL post-fix verification | SUCCESS; 671 discovered, 18 selected, 8,219-byte XCom; 18,140 observations inserted |
| `scheduled__2026-09-16T05:05:00+00:00` reconciler | CURRENT audit baseline | SUCCESS; 679 discovered, 0 selected, 244-byte XCom |
| `manual__recovery_audit_20260916T0507Z` crawler | SUPERSEDED audit probe | Shortened URL returned zero observations; persistence failed closed; no checkpoint advancement |
| `manual__recovery_canonical_20260916T0508Z` crawler | SUPERSEDED reporting regression | Commit, checkpoint, analytics and assets passed; final report failed with AttributeError |
| `manual__recovery_acceptance_20260916T0511Z` reconciler | CURRENT acceptance | SUCCESS; 681 discovered, 0 selected, backlog 0 |
| `manual__recovery_acceptance_20260916T0511Z` Silver | CURRENT acceptance | SUCCESS; 78,150 unique rows, VALID 14-column output |
| `manual__recovery_fixed_20260916T0517Z` crawler | CURRENT post-fix acceptance | SUCCESS including final report; 15 new committed versions and checkpoint advanced |
| `manual__recovery_final_20260916T0528Z` reconciler | CURRENT final acceptance | SUCCESS; 689 discovered, 0 selected, 244-byte XCom, backlog 0 |
| `manual__recovery_final_20260916T0528Z` Silver | CURRENT final acceptance | SUCCESS; 78,153 rows = 78,153 unique post IDs; VALID |

Current discovery XCom keys: `audit_meta`, `batch_limit`, `mysql_before`, `selected_runs`. No complete discovery manifest crosses XCom. Final reconciliation rescans globally and reports 146,963 MySQL observations = 146,963 DuckDB observations.

## Bronze identity and measured counts

Bronze identity: database `roombeacon_bronze`, hostname `898f79c19d04`, internal port 3306, UUID `5ecd1652-afea-11f1-a6a8-5e034349feb3`.

Metadata identity: database `airflow`, hostname `3bb448020234`, internal port 3306, UUID `5eb7695d-afea-11f1-9c9c-72d2d4cf468c`. These are different databases/servers.

Baseline measured around 05:04 UTC on 2026-09-16:

| Table | Count | Latest created_at |
|---|---:|---|
| platforms | 9 | 2026-09-15 02:22:54 |
| rental_posts | 78,138 | 2026-09-15 20:03:04 |
| rental_post_versions | 146,922 | 2026-09-16 05:03:52 |
| post_prices | 161,273 | 2026-09-16 05:03:52 |
| post_addresses | 14,543 | 2026-09-16 05:03:50 |
| post_details | 182,999 | 2026-09-16 05:03:52 |
| post_images | 614,655 | 2026-09-16 05:03:52 |

Latest version observed_at at baseline: `2026-09-16 05:03:42`; greatest run identifier: `run_20260916_045350`. Counts changed while scheduled jobs continued: fresh reconciler later measured 78,150 posts / 146,963 versions. Global changes cannot all be attributed to the acceptance run.

Second read at 05:14 UTC: platforms 9; posts 78,150; versions 146,963; prices 161,314; addresses 14,563; details 183,040; images 615,006. The fresh acceptance reconciler's discovery XCom was **244 bytes**, 681 discovered, zero selected, and contained only the four documented top-level keys.

## Fresh source-to-Silver trace

Canonical source: `https://chothuenha.com.vn/cho-thue-phong-tro-nha-tro-ho-chi-minh`.

Airflow run: `manual__recovery_canonical_20260916T0508Z`; crawl identity: `run_20260916_051039`. Requested one page, ten records, no detail crawling. The page produced 15 records: the page-level processing exceeded the requested record cap, although the run remained bounded to one page.

- Source eligibility succeeded; crawl status SUCCESS.
- Local `listings.json`: 15 records, 11,694 bytes; `metadata.json`: one page entry.
- Bronze observations: 15.
- Stage 05: SUCCESS; posts created 0, existing 15, versions inserted 15, technical duplicates 0.
- An independent database connection read 15 versions for 15 distinct post identities, all created at `2026-09-16 05:10:43`. This verifies durability after commit.
- Child rows for that run: prices 15, details 15, images 15; addresses, amenities, fees, contacts and attributes 0.
- Stage 06: `success_checkpoint_advanced=true`.
- Stage 07: SUCCESS.
- Fresh reconciler: SUCCESS, XCom resolved, zero backlog.
- DuckDB/Silver verification: total latest rows 78,150 = distinct post IDs 78,150.
- Fresh Silver: SUCCESS, 78,150 rows, VALID; `/data/silver/rental_latest.parquet` and metadata generated at approximately 05:11:37 UTC.

No prior-machine checkpoint was required by the planner contract: existing first-crawl regression verifies missing state selects BOOTSTRAP_FULL. Current checkpoints are JSON under `/data/state/targets` and `/data/state/seen`, not Airflow XCom or business MySQL.

## Tests, changes and remaining limits

Command: `ROOMBEACON_ENV=test PYTHONPATH=crawler/src:. .venv/bin/pytest -q tests/test_crawl_planner.py tests/test_bronze_reconciliation.py -k 'not duckdb_analytics_pool_assigned'` → **18 passed, 1 deselected**. Initial broader selection had the same 18 passes and one import failure because the host virtualenv lacks `airflow.exceptions`; actual Airflow runtime diagnostics and fresh DAG execution passed.

A fresh single-target runtime failure proved a reporting boundary defect: installed Airflow 3.3.1 `RuntimeTaskInstance.xcom_pull` returns a scalar dict when one string task ID produces exactly one value. `reporting.py:34` iterated dict keys as records and raised AttributeError. This occurs after commit and is neither a MySQL failure nor an API-server 500. Four mapped pulls in the crawler DAG now pass a list of task IDs, preserving list shape for one and multiple mapped results. Plans and scalar analytics pulls remain unchanged.

New regression `tests/test_reporting_xcom_cardinality.py`: RED **1 failed, 1 passed**, with the single-result case receiving a dict instead of a list. GREEN combined command adds this file to the planner/reconciliation selection above: **20 passed, 1 deselected**. The test compiles the actual DAG reporting function without requiring a host Airflow installation and reproduces the installed SDK return-shape contract. A new bounded run `manual__recovery_fixed_20260916T0517Z` was triggered for runtime verification; no failed task was cleared.

Additional runtime boundary verification executed the corrected wrapper with the real installed `RuntimeTaskInstance.xcom_pull`, using read-only saved XCom values in place of API retrieval, and the real application report function. It passed: one target, 15 observations inserted, 15 existing posts, one checkpoint advanced. No task state or XCom was changed by this check.

**Final live acceptance, approximately 05:28 UTC:** crawler `manual__recovery_fixed_20260916T0517Z` completed SUCCESS. Its source run `run_20260916_052634` wrote 15 observations; Stage 05 reported 0 new posts, 15 existing posts, 15 inserted versions, 0 technical duplicates; checkpoint advanced. An independent connection confirmed 15 versions for 15 distinct posts, created at 05:26:39. Fresh reconciler and Silver runs `manual__recovery_final_20260916T0528Z` both completed SUCCESS. The reconciler audited 689 artifacts, emitted 244 bytes, selected zero pending items, and verified 148,861 MySQL observations = 148,861 DuckDB observations. Latest-post/Silver totals were 78,153 = 78,153 distinct post IDs. This closes the reporting regression and proves new data generation by the patched runtime, while leaving the strict clean-clone gaps below unresolved.

Files changed in this audit: `airflow/dags/crawler/roombeacon_crawler.py`, `tests/test_reporting_xcom_cardinality.py`, and this report. Prior bounded-XCom RED/GREEN evidence belongs to the previous task. Full-worktree `git diff --check` reports pre-existing trailing whitespace in `crawler_settings.py` and `config/env/minio.py`; those unrelated edits were preserved.

Additional proven pending issue from source inspection: checkpoint authorization still accepts `UNKNOWN` persistence status. The scheduled acceptance path supplied explicit SUCCESS, but this does not establish fail-closed behavior for legacy/manual payloads. The previously approved correction had not been implemented when this audit superseded isolated-task work.

Before claiming clean-clone recovery, a reviewable recovery commit must include the intended repairs, directory preparation/UID requirements and DAG activation must be made explicit, and an isolated empty-state deployment must exercise the resulting committed revision. Current live data must not be removed to conduct that test. No claim is made that old historical data is recoverable.

## Safety

`.env` was not read; secret values and connection strings were not printed. No database reset, DROP, TRUNCATE, mass DELETE, volume deletion, schedule modification or container restart was performed. Existing contaminated child rows and historical failed runs were retained. Unit tests used temporary fixtures, not production tables. Only fresh bounded acceptance jobs wrote normal pipeline data.

**NOT HEALTHY — FRESH CLONE STILL HAS BLOCKERS**

This strict fresh-clone verdict is distinct from the demonstrated ability of the current patched runtime to commit new observations and materialize Silver.
