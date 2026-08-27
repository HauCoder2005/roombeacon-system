# Restart-dependent crawl stall audit

## Scope and safety

This audit observed scheduled `AUTO` runs without triggering a crawl or restarting
the stack. It did not change source budgets, schedules, crawler behavior, state, or
production data.

## Finding

The reported restart-dependent stall was not reproduced as a runtime lifecycle
failure. Source checkpoints and health state are durable under `/data/state`, and
their timestamps survived the container restart. The large post-start ingestion
batch occurred because the stack had been offline long enough for all healthy
source intervals to become due at once. Subsequent 15-minute DAG ticks correctly
ran only sources whose own 30-120 minute intervals had elapsed.

Three access-challenged sources remained in persisted cooldown before and after
the restart. They are mapped as due and then deferred by the health gate without
advancing `next_run_at` or extending `cooldown_until`. This is controlled source
policy behavior, not a crawler stall.

## State ownership

| State | Storage | Lifetime |
|---|---|---|
| Target checkpoint, frontier, `next_run_at` | `/data/state/targets/*.json` | Durable host-mounted data |
| Seen listing and detail metadata | `/data/state/seen/*.json` | Durable host-mounted data |
| Deferred detail backlog | `/data/state/deferred/*.json` | Durable host-mounted data |
| Source health and cooldown | `/data/state/health/*.json` | Durable host-mounted data |
| Airflow DAG/task lifecycle | Airflow metadata MySQL | Durable |
| HTTP/browser resources | Crawl-run scoped | Ephemeral and explicitly closed |
| MySQL transaction connection | Persistence-call scoped | Ephemeral and explicitly closed |
| DuckDB catalog | `/data/analytics/roombeacon_analytics.duckdb` | Durable; task process owns open handle |

## Production evidence

All timestamps below are UTC. No restart occurred between the listed post-start
runs.

| Scheduled run | Due | Executable | Cooldown-deferred | New listings | Bronze observations |
|---|---:|---:|---:|---:|---:|
| 2026-08-27 02:45 | 11 | 8 | 3 | 353 | 843 |
| 2026-08-27 03:00 | 3 | 0 | 3 | 0 | 0 |
| 2026-08-27 03:15 | 3 | 0 | 3 | 0 | 0 |
| 2026-08-27 03:30 | 4 | 1 | 3 | 0 | 64 |
| 2026-08-27 03:45 | 4 | 1 | 3 | 0 | 80 |
| 2026-08-27 04:00 | 4 | 1 | 3 | 17 | 45 |

The 03:30 run is the decisive recovery observation: NhaTroVN became eligible at
its persisted `next_run_at` and crawled successfully without a restart. Task 04
took about 51.5 seconds, task 05 about 0.8 seconds, and task 07 about 0.7 seconds.

The 03:45 run independently confirmed the same behavior for PhongTro123. It
became eligible at its persisted 45-minute interval, wrote 80 observations, and
completed without a restart. Its productive task 04 took about 83.6 seconds;
task 05 took about 0.8 seconds and task 07 about 0.4 seconds.

The 04:00 run then made NhaTot executable at its persisted interval and wrote 45
observations, including 17 new listings. Productive task 04 took about 42.8
seconds, task 05 about 0.7 seconds, and task 07 about 0.4 seconds. NhaTroVN was
correctly not due at planning time: its 03:30 checkpoint completed at 03:30:57,
so its next 30-minute eligibility was 04:00:57 rather than the 04:00:01 planning
instant.

Across all six consecutive post-start runs, no DAG run remained running, queued,
up-for-retry, deferred, or zombie. The three challenge cooldown records retained
their original failure counts, expiry times and update timestamps; qualification
did not extend cooldown or advance target checkpoints. Scheduler process count
remained stable, all productive task 04 processes exited, task 05 consistently
completed in under one second, and task 07 consistently released the run without
a persistent DuckDB lock.

## Resolution

No lifecycle/state bug was found, so no crawler code was changed. The apparent
stall is the expected low-activity period after a startup burst: offline time
causes multiple source intervals to expire together, while subsequent DAG ticks
honor each source's independent interval and access-policy cooldown. Restarting
is neither required for recovery nor an accepted operational remedy.

Validation gates: 44 focused scheduling, health, frontier, configuration and
architecture tests passed. All five DAG modules imported without runtime config
access.
