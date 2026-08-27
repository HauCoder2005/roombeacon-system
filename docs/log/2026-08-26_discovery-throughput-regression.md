# Discovery throughput regression after detail enrichment — 2026-08-26

Status: **COMPLETE — ORDERING FIX VERIFIED**

This report uses aggregate evidence only. It does not contain credentials,
contacts, listing identities, or source URLs.

## Last-known-good versus current flow

Git history shows that at `18bc43d` the scheduled-source default was
`crawl_details=False`, and the large-source adapters did not override it. The
effective hot path was listing page → cards → lightweight Bronze → next page.

By `0c14a6e`, the durable deferred backlog existed and was consumed before
`while current_page <= effective_end_page`. Subsequent runtime configuration
enabled details for the large sources and raised PhongTro123/NhaTroVN to a
bounded budget of 40. `DeferredBudgetScheduler` intentionally allocates 100%
of a source budget to pending first-pass backlog. The resulting flow was:

deferred details → listing page → per-card immediate detail or deferral →
frontier → artifacts → MySQL.

Runtime profiling made the regression concrete: NhaTroVN and PhongTro123 each
spent about 78–79 seconds in deferred processing before listing acquisition.
The task had no global time limit, so it usually still reached its configured
pages; however, historical frontier progress and lightweight artifact intent
were delayed behind enrichment and were lost if the task failed during that
front-loaded work.

## Request amplification baseline

| Source | Listing requests | Cards | Detail requests | Listing avg | Detail avg | Detail network total | Requests/card |
|---|---:|---:|---:|---:|---:|---:|---:|
| nhatrovn | 2 | 40 | 40 | 0.176s | 0.471s | 18.851s | 1.05 |
| phongtro123 | 2 | 40 | 40 | 0.590s | 0.497s | 19.899s | 1.05 |
| nhatot | 1 | 25 | 20 | 1.546s | 1.083s | 21.663s | 0.84 |

With detail disabled, the same page/card shapes require 0.05, 0.05 and 0.04
network requests per card respectively. Enrichment therefore amplified total
requests per discovered card by roughly 21×. The fix preserves the bounded
total requests, but the discovery phase itself again has the page-only ratio;
detail requests run only after frontier completion.

## Minimal fix

`CrawlRunner` now executes page acquisition, lightweight card processing and
frontier transitions before invoking `DeferredDetailProcessor`.

Every detail-eligible card is immediately represented by a lightweight Bronze
observation and durably enqueued with reason `DISCOVERY_FIRST_ENRICHMENT`.
After discovery completes, the existing per-source request budget consumes the
durable queue. A successful same-run enrichment replaces the matching
lightweight Bronze record by stable source identity; older backlog items not
seen in the current pages are appended. This preserves one observation per
stable listing/run while retaining full-address detail fields.

No detail concurrency, budget, schedule, parser, retry, TTL, rate-limit,
robots, source-health, checkpoint, schema, DuckDB, MinIO or DAG change was made.

The MySQL stage still starts after task `04` completes because the required DAG
remains linear. The improvement is therefore discovery/frontier priority and
failure isolation inside the application task, not parallel Airflow
persistence. Lightweight observations remain valid when detail is unavailable,
and enriched observations win when detail succeeds before artifact publication.

## Verification

- Focused discovery/frontier/backlog/address/security suite: 78 passed,
  19 subtests.
- Full regression: 372 passed, 34 subtests.
- Safe DAG imports: 5/5.
- Main DAG: 9 tasks, 8 edges, linear.

## Production validation

Three post-change NORMAL runs completed naturally:

| Run UTC | Productive source | Pages | Cards | New | Discovery | Enrichment | Detail success | Backlog before → after |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 05:30 | nhatrovn | 2 | 40 | 0 | 2.511s | 80.260s | 36 | 359 → 323 |
| 05:45 | controlled cooldown only | 0 | 0 | 0 | — | — | 0 | — |
| 06:00 | phongtro123 | 2 | 40 | 0 | 3.316s | 80.095s | 40 | 627 → 587 |

Both productive runs had zero HTTP 429 and zero access challenges. NhaTroVN
completed discovery at about 956 cards/minute and PhongTro123 at about 724
cards/minute before enrichment began. The comparable pre-fix end-to-end rates
were about 29 cards/minute because discovery and enrichment were reported as a
single blocking duration.

Pages/run did not rise in these two runs: both sources are already incremental
and correctly stopped after two entirely-known pages. New listings/run was zero
for the same reason. The fix removes enrichment as a frontier blocker but does
not override the known-page stop rule or fabricate historical work. Therefore
the claimed historical 20k/day rate cannot be reproduced from these runs, and
no numeric unique-listing/day increase is claimed without an eligible frontier
containing unseen listings.

Post-run integrity remained: orphan versions 0, posts without versions 0 and
same-run duplicates 0. NhaTroVN produced 76 versions for 76 distinct stable
posts in its validation run: 40 page observations plus 36 successful older
backlog enrichments.

An additional NORMAL run at 06:15 supplied representative unseen historical
work:

| Source | Pages | Cards | New | Discovery | New/min | Detail success | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| cafeland | 5 | 134 | 130 | 9.155s | 852 | 20 | 48.985s |
| chothuephongtro | 5 | 100 | 99 | 12.775s | 465 | 20 | 80.942s |
| mogi | 5 | 75 | 53 | 9.318s | 341 | 20 | 49.247s |
| tromoi | 5 | 120 | 120 | 8.974s | 802 | 20 | 48.664s |

Using the comparable pre-fix end-to-end runs, discovery-phase new-listing
throughput improved approximately 5.5× for CafeLand, 4.3× for
ChoThuePhongTro, 5.1× for Mogi and 6.4× for TroMoi. Pages/run remained at the
configured five-page cap, proving the fix changed ordering rather than page or
schedule policy.

Backlogs grew for sources discovering more eligible cards than their unchanged
20-request enrichment budget. This is expected conservation, not loss: for
example CafeLand `448 + 130 - 20 = 558`; ChoThuePhongTro
`318 + 99 - 20 = 397`; Mogi `110 + 60 - 20 = 150`; and TroMoi
`369 + 120 - 20 = 469`. Full-address enrichment continued in every productive
source.

The four new-listing sources produced 402 unique listings in this eligible
fleet run. A naive hourly-repeat capacity would be about 9,648/day, but that is
not a forecast because eligibility, known-page stops and source inventory vary.
The historical ~20k/day claim cannot be validated or restored by ordering
alone under current page/interval/frontier caps. A separate evidence-based
scheduling/frontier capacity audit would be required; this task intentionally
did not alter those policies.
