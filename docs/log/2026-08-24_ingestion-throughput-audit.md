# Ingestion throughput audit — 2026-08-24

Status: **COMPLETE**

This log records sanitized aggregate evidence only. No environment file,
credential, listing identity, or private payload was read or printed.

## Baseline

Before activation/pagination fixes, MySQL contained 2,123 unique listings and
5,249 persisted observations. Only five sources had ever reached MySQL. The
eight scheduled DAG runs from 14:00 through 15:45 UTC all succeeded, but seven
were almost entirely cooldown checks. The one productive fleet run at 15:00
showed the throughput shape below.

| Source | Pages | Cards | New | Known | Runner observations | Stop |
|---|---:|---:|---:|---:|---:|---|
| chothuenha | 1 | 15 | 0 | 15 | 15 | `FORWARD_SCAN_COMPLETE` |
| nhatot | 1 | 25 | 22 | 3 | 45 | `FORWARD_SCAN_COMPLETE` |
| nhatrovn | 2 | 40 | 0 | 40 | 77 | `KNOWN_REGION_REACHED` |
| phongtro123 | 2 | 40 | 0 | 40 | 80 | `KNOWN_REGION_REACHED` |
| tromoi | 1 | 24 | 0 | 24 | 28 | `FORWARD_SCAN_COMPLETE` |
| batdongsan / muaban / guland | 0 successful | 0 | 0 | 0 | 0 | controlled challenge/cooldown |

This disproved a full-pipeline stall: observations and detail/asset work were
advancing while unique listings were flat. The primary unique-ingestion
bottleneck was source coverage plus disabled/missing pagination.

## Acquisition audit and changes

- ChoThueNha page 1/2: 15 + 15 cards, zero overlap; current robots policy
  explicitly allows the query route.
- TroMoi page 1/2: 24 + 24 cards, zero overlap; current robots policy allows
  the query route.
- ChoThuePhongTro page 1/2: 20 + 20 cards, zero overlap.
- Mogi page 1/2: 15 + 15 cards, zero overlap.
- CafeLand's old `/page/2` builder returned 404. The public page linked to
  `/page-2/`; the corrected route returned 200 and 30 cards.
- Guland remained access-challenged. JS pagination was not invented or
  bypassed.

Batch 2 and Batch 3 were activated. Each newly paginated source starts with a
source-scoped five-page bootstrap budget. Detail budgets, asset budget, Airflow
schedule, robots/retry policy, and schema were unchanged.

`interval_minutes` was also restored as an explicit `CrawlPlan` field. Before
this fix, checkpoint scheduling silently fell back to 60 minutes for every
source. The fix preserves each adapter's declared interval; it does not change
the Airflow 15-minute DAG schedule.

ChoThueNha and TroMoi had legacy forward-only checkpoints. Their first
pagination-enabled run correctly discovered deeper records, but exposed a
planner migration edge: the old state was classified as incremental. The
planner invariant now treats incomplete historical state as bootstrap. Both
frontiers were moved forward (not reset) to continuation page 6.

## Three normal scheduled runs after the fix

| DAG run (UTC) | Duration | Productive sources | Pages | New unique | MySQL observations |
|---|---:|---|---:|---:|---:|
| 16:00 | 98.16s | cafeland, chothuephongtro, mogi | 15/15 | 309 | 309 |
| 16:15 | 140.60s | chothuenha, nhatot, nhatrovn, phongtro123, tromoi | 15/15 | 177 | 396 |
| 16:30 | 44.19s | none due; controlled cooldown only | 0 | 0 | 0 |

All three DAG runs succeeded. The 16:15 runner produced 397 observations; MySQL
inserted 396 because one NhaTot observation was an idempotent technical
duplicate. There were no page failures among productive sources.

Historical frontier after validation:

- cafeland, chothuephongtro, mogi: continuation page 6;
- chothuenha, tromoi: corrected continuation page 6;
- nhatrovn, phongtro123: historical bootstrap already complete; normal runs
  stop after two fully-known pages;
- nhatot: intentional forward-only acquisition;
- guland and phongtrotoanquoc: no unverified historical frontier.

## Final MySQL snapshot

| Source | Unique | Observations | Addresses | Images |
|---|---:|---:|---:|---:|
| cafeland | 134 | 134 | 20 | 502 |
| chothuenha | 75 | 105 | 35 | 2,776 |
| chothuephongtro | 100 | 100 | 100 | 432 |
| mogi | 75 | 75 | 75 | 379 |
| nhatot | 246 | 399 | 312 | 3,294 |
| nhatrovn | 855 | 2,319 | 2,319 | 3,444 |
| phongtro123 | 1,005 | 2,655 | 2,165 | 19,615 |
| tromoi | 119 | 167 | 167 | 2,421 |
| **Total** | **2,609** | **5,954** | **5,193** | **32,863** |

Net validation delta: **+486 unique listings** and **+705 persisted
observations**. Post-fix DAG average duration was 94.32 seconds, far below the
15-minute schedule interval. The slowest mapped crawl was 86.83 seconds and the
asset stage averaged 37.70 seconds.

## Gates

- Focused planner/frontier/pagination/source tests: 63 passed.
- Full regression: 364 passed, 34 subtests passed.
- DAG imports: 5/5 passed.
- Main DAG: 9 tasks, 8 edges, linear, `max_active_runs=1`.
- Reset / FORCE_FULL / schedule change / detail-budget change / asset-budget
  change: none.
