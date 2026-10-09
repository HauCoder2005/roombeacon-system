# RoomBeacon Repository Rules

## Scope and architecture
- Treat `architecture/overall-architecture.pdf` as the target architecture.
- Build post-Silver work on branch `feat/post-silver-platform`; do not push.
- Preserve notebooks 01-07. When moving notebook utilities into packages, keep re-export shims.
- Do not invent coordinates, infer distance from ward/district centroids, or reselect the locked LightGBM/RAW/F4 champion.

## Frozen and protected areas
- Never modify `crawler/src/roombeacon_crawler/{sources,fetchers,policies,pipeline,application/crawl}/**`.
- Never modify `crawler/src/roombeacon_crawler/services/fetch_coordinator.py`.
- Never modify `crawler/src/roombeacon_crawler/mappers/bronze_mapper.py`.
- Never modify `airflow/dags/crawler/roombeacon_crawler.py`.
- Do not modify storage modules from `feat/storage-plane-alignment`; consume public interfaces only.
- If protected code must change, stop and ask the user first.

## Data access and production safety
- Analytics must not read MySQL Bronze directly.
- Only the bounded DuckDB extract/snapshot job may read Bronze, with watermark and timeouts.
- Every downstream processing, warehouse, ML, search, and API job reads Parquet or its derived stores.
- Do not write production databases or run commands in live containers.
- Give real-data or infrastructure commands to the user as:
  `⚠ PRODUCTION: <command> | <reason> | rollback: <rollback>`
- Use local DuckDB/Parquet fixtures for tests when Docker or network access is unavailable.

## Security
- Never print secrets or read `.env`; only report variable names as set/unset.
- Keep `.env` ignored and use least-privilege, non-root service accounts.
- Bind published ports to `127.0.0.1`.
- Add ClickHouse, MySQL App, and API only behind disabled-by-default profiles: `warehouse`, `app`, `api`.
- API responses must exclude seller/contact PII; mask it only when explicitly required.
- Use parameterized queries, bounded inputs/timeouts, structured redacted logs, and pinned dependencies.

## Git and verification
- Preserve unrelated user changes; stage only files changed for the current phase.
- Use small commits per phase and never push.
- Develop features and fixes test-first; run focused tests before the broader suite.
- Golden Silver output is 132,436 rows and exactly 80 ordered columns for the current fixture, with row hashes matching the legacy output.
- Before completion, verify the frozen-area diff is empty and report pre-existing failures separately.
