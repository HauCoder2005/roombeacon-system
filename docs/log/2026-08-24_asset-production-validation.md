# RoomBeacon Asset Pipeline — Production Validation

Status: **COMPLETE**

This log records sanitized aggregate evidence from scheduled NORMAL
`08_assets_sync_minio` executions. It contains no source URLs, listing IDs,
object keys or credentials.

## Reporting invariant

```text
selected = post_upload_verified + terminal_failed + retryable_failed
```

`already_existing` counts prior SUCCESS objects verified during discovery and
skipped before selection. It is intentionally outside the selected outcome
partition. `invalid_magic` is a subset of `terminal_failed`.

## Excluded pre-fix execution

`scheduled__2026-08-24T14:15:00+00:00` ran before the MinIO policy was applied
and before the reporting schema was deployed. It is not part of the stability
sample.

## Batch 50 NORMAL executions

| Run | Limit | Selected | Verified | Existing scan | Invalid magic | Terminal total | Retryable | Pending before | Pending after | Service duration | Task duration |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scheduled__2026-08-24T14:30:00+00:00` | 50 | 50 | 37 | 39 | 12 | 13 | 0 | 15,225 | 15,175 | 19.89s | 21.52s |
| `scheduled__2026-08-24T14:45:00+00:00` | 50 | 50 | 31 | 76 | 19 | 19 | 0 | 15,175 | 15,125 | 30.67s | 31.24s |
| `scheduled__2026-08-24T15:00:00+00:00` | 50 | 50 | 50 | 107 | 0 | 0 | 0 | 17,195 | 17,145 | 17.33s | 17.96s |

Per-source verified outcomes: ChoThueNha 8/10, NhaTot 9/10, NhaTroVN
10/10, PhongTro123 10/10, TroMoi 0/10. TroMoi candidates were terminal
invalid-magic responses; security validation remains unchanged.

All three post-fix NORMAL runs satisfied the stability gate. The increase in
pending before run 15:00 came from new `post_images` persisted by its preceding
NORMAL crawl stages; within every asset execution pending decreased by exactly
the selected batch size.

Run 14:45 per-source verified outcomes: ChoThueNha 1/10, NhaTot 5/10,
NhaTroVN 10/10, PhongTro123 10/10 and TroMoi 5/10. All remaining selected
outcomes were terminal invalid-magic responses; retryable and MinIO operational
failures remained zero.

## Batch 100 decision

`DEFAULT_ASSET_BATCH_SIZE` was increased from 50 to 100 only after the three-run
gate passed. Detail/page budgets, DAG schedule, graph, parser, schema and MinIO
policy were not changed. Two NORMAL batch-100 runs are required before this log
can be marked complete; both required runs passed below.

## Batch 100 NORMAL executions

| Run | Limit | Selected | Verified | Existing scan | Invalid magic | Terminal total | Retryable | Pending before | Pending after | Service duration | Task duration |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scheduled__2026-08-24T15:15:00+00:00` | 100 | 100 | 82 | 157 | 18 | 18 | 0 | 17,145 | 17,045 | 30.81s | 31.42s |
| `scheduled__2026-08-24T15:30:00+00:00` | 100 | 100 | 65 | 239 | 35 | 35 | 0 | 17,045 | 16,945 | 29.81s | 30.39s |

Run 15:15 per-source verified outcomes: ChoThueNha 12/20, NhaTot 12/20,
NhaTroVN 20/20, PhongTro123 20/20 and TroMoi 18/20. All other selected
outcomes were terminal invalid-magic responses. Authorization and operational
failures remained zero.

Run 15:30 per-source verified outcomes: ChoThueNha 10/20, NhaTot 13/20,
NhaTroVN 20/20, PhongTro123 20/20 and TroMoi 2/20. All other selected
outcomes were terminal invalid-magic responses. Authorization and operational
failures remained zero.

## Final assessment

- Batch 50: three of three NORMAL runs passed accounting and stability gates.
- Batch 100: two of two NORMAL runs passed accounting and stability gates.
- Upload authorization and MinIO operational failures: zero across all five
  counted executions.
- Task duration at batch 100 remained 30–31 seconds, far below the 15-minute
  DAG interval.
- Pending decreased by the full selected count inside every execution. Changes
  between runs may include new image references persisted by preceding crawl
  stages.
- Batch 100 is retained. No increase to 200 is authorized by this validation.
- At 16,945 pending references and a theoretical maximum of 9,600 selections
  per day, minimum drain time is approximately 1.8 days before accounting for
  new arrivals and source responses.
