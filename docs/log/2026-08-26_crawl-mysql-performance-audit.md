# Crawl and MySQL persistence performance audit — 2026-08-26

Status: **COMPLETE**

This audit contains aggregate operational evidence only. It did not read an
environment file or print credentials, URLs, listing identities, contacts, SQL
parameters, or payloads.

## Five-run baseline

The five scheduled NORMAL runs from 16:30 through 17:30 UTC all succeeded.
Average DAG duration was 135.44 seconds. Critical-path stage attribution was:

| Stage | Average seconds | Share |
|---|---:|---:|
| Crawl (`04`) | 60.125 | 46.3% |
| MySQL (`05`) | 0.787 | 0.6% |
| Checkpoint (`06`) | 0.672 | 0.5% |
| DuckDB (`07`) | 0.441 | 0.3% |
| MinIO (`08`) | 65.530 | 50.5% |
| Other orchestration | 1.316 | 1.0% |

The operator-visible runtime was therefore dominated by MinIO and network
acquisition, not MySQL. Productive source observations included:

| Source | Pages | Cards | Detail success | Observations | Crawl seconds | Persist seconds |
|---|---:|---:|---:|---:|---:|---:|
| cafeland | 5 | 134 | 20 | 154 | 50.433 | 1.262 |
| chothuenha | 2 | 30 | 20 | 50 | 50.429 | 1.340 |
| chothuephongtro | 5 | 100 | 20 | 120 | 55.434 | 1.366 |
| mogi | 5 | 75 | 20 | 95 | 58.808 | 1.324 |
| nhatrovn | 2 | 40 | 38 | 78 | 86.964 | 1.155 |
| tromoi | 5 | 118 | 20 | 138 | 55.637 | 1.375 |
| phongtro123 | 2 | 40 | 40 | 80 | 84.869 | 0.753 |
| nhatot | 1 | 25 | 20 | 45 | 44.661 | 0.602 |

BatDongSan, MuaBan and Guland were controlled cooldown outcomes rather than
application failures.

## Root causes and boundaries

- The required 1.5-second request pacing dominates 20/40-detail source runs.
  Detail acquisition is sequential. No concurrency was introduced because the
  existing source-policy and rate-limit evidence does not justify it.
- `HttpFetcher` created a new `httpx.AsyncClient` for every request.
- `BrowserFetcher` launched Chromium and created a context for every request.
  A NhaTot run with one listing page and 20 detail pages therefore launched 21
  browsers.
- Persistence used one pooled connection and one transaction per mapped batch;
  commit-per-row was not present. Lock counters reported zero row-lock waits.
- Persistence nevertheless contained N+1 round trips: platform lookup per
  observation, select-before-post-upsert, select-before-version-insert, and
  one execution per image/amenity.
- Bronze serialization/deserialization is an intentional Airflow artifact
  boundary. With MySQL stage time below 1% of the critical path, removing the
  artifact was not justified.

Existing unique constraints cover `(platform_id, platform_post_id)` and
`(rental_post_id, crawl_run_id)`. No index or schema change was justified.

## Minimal changes

- Reuse one HTTP client per source execution and close it at the run boundary.
- Reuse one Playwright browser/context per source execution while retaining a
  page per navigation.
- Add aggregate crawl timings and transport lifecycle counters to the existing
  manifest/XCom boundary.
- Cache platform resolution per source within a persistence batch.
- Replace post and version select-before-write patterns with atomic MySQL
  upserts using the existing unique constraints and `LAST_INSERT_ID` identity.
- Use executemany for per-observation image and amenity rows.
- Add parameter-free SQL execution/time aggregates by table to task `05`.

Transaction scope, retry behavior, detail budget, page budget, request pacing,
source health, checkpoint ordering, schedule, Bronze artifacts and DAG topology
are unchanged.

## Production validation

The first post-change NORMAL run at 17:45 UTC succeeded. NhaTot processed one
listing page, 25 cards, 20 successful details and 45 observations:

- crawl: 41.631 seconds (baseline comparable run: 44.661 seconds);
- browser lifecycle: 1 launch, 1 context, 21 pages (previously 21 launches);
- page acquisition: 1.211 seconds;
- listing parse/residual page work: 1.252 seconds;
- detail network time: 16.550 seconds;
- Bronze serialization: 0.002 seconds;
- internal MySQL persistence: 0.105 seconds;
- mapped persistence task: 0.723 seconds, including task/runtime overhead;
- SQL executions: 258, versus an estimated 743 under the old per-row path for
  the same row shape (65.3% fewer round trips).

Three post-change NORMAL runs completed without intervention:

| Run (UTC) | DAG seconds | Productive sources | Observations | Result |
|---|---:|---|---:|---|
| 17:45 | 81.011 | nhatot | 45 | success |
| 18:00 | 38.916 | controlled cooldown only | 0 | success |
| 18:15 | 143.928 | nhatrovn, phongtro123 | 158 | success |

Comparable crawler results were NhaTot 44.661 → 41.631 seconds (-6.8%),
NhaTroVN 86.964 → 82.507 (-5.1%), and PhongTro123 84.869 → 83.394
(-1.7%). The HTTP sources each created one client per run. All three productive
sources reported zero HTTP 429 and zero access challenges.

The measured SQL execution reductions were:

| Source/records | Estimated old executions | Measured new executions | Reduction |
|---|---:|---:|---:|
| nhatot / 45 | 743 | 258 | 65.3% |
| nhatrovn / 78 | 1,037 | 507 | 51.1% |
| phongtro123 / 80 | 2,810 | 468 | 83.3% |

The old counts are deterministic reconstructions from the old repository call
graph and the measured row shape, not historical SQL telemetry. The new counts
come directly from parameter-free production instrumentation.

Mapped task-level MySQL throughput was mixed because fixed Airflow startup and
the row shape dominate such short tasks: NhaTroVN improved from 67.5 to 97.7
records/second, while NhaTot measured 74.8 → 62.2 and image-heavy
PhongTro123 106.2 → 79.0. Internal persistence remained 0.105, 0.165 and
0.379 seconds respectively. Therefore task `05` was not, and is not, an
operator-visible bottleneck; the optimization primarily reduces database load.

Across the three post-change runs, average critical-stage durations were crawl
42.643 seconds, MySQL 0.753, checkpoint 0.627, DuckDB 0.431 and MinIO 35.425.
Observed fleet rates were 32 new listings/hour and 270.7 observations/hour,
versus baseline-window rates of 348.8 and 670.4. These rates are not a speed
regression: the windows had different eligibility mixes (the after window had
one all-cooldown run and only three productive sources). Source-shape timing,
not fleet yield, is the valid before/after comparison.

## Verification gates

- Focused performance/persistence/security tests: 40 passed, 11 subtests.
- Full regression: 369 passed, 34 subtests.
- DAG imports: 5/5 through the safe import regression.
- Main DAG remains 9 tasks, 8 edges, linear.
- Pre-change integrity: orphan versions 0; posts without versions 0; same-run
  duplicates 0.
- Post-change integrity: orphan versions 0; posts without versions 0; same-run
  duplicates 0. InnoDB row-lock waits and row-lock time remained zero.
