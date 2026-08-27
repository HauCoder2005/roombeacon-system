# Full-address coverage verification

Status: CODE FIXED — TARGETED RECOVERY IN PROGRESS

## Baseline

The baseline was captured from MySQL in one read-only statement at
2026-08-26 18:13 Asia/Ho_Chi_Minh. It ranks one stable listing and resolves its
latest confirmed address. The same rule is used for the final snapshot; an
inherited value is explicitly identified rather than copied into a raw version.

| Source | Total | Latest address | Missing | Coverage |
|---|---:|---:|---:|---:|
| cafeland | 1,178 | 910 | 268 | 77.25% |
| chothuenha | 76 | 76 | 0 | 100.00%* |
| chothuephongtro | 897 | 897 | 0 | 100.00% |
| mogi | 380 | 380 | 0 | 100.00% |
| nhatot | 445 | 406 | 39 | 91.24% |
| nhatrovn | 861 | 861 | 0 | 100.00% |
| phongtro123 | 1,049 | 1,049 | 0 | 100.00% |
| tromoi | 1,015 | 1,015 | 0 | 100.00% |
| **Fleet** | **5,901** | **5,594** | **307** | **94.80%** |

`*` ChoThueNha's apparent coverage is not trustworthy in the baseline. Six
artifact runs contained 106/106 detail rows with the same known company-office
address. Those historical observations are preserved, but the parser no longer
accepts organization/agent JSON-LD as a listing address.

## Verified causes and fixes

- Raw persistence previously copied a prior address into a new lightweight
  version. This made inherited state look directly observed. Raw versions now
  persist only `address_raw` from that version.
- `v_latest_posts` now exposes `full_address_text` and
  `full_address_inherited`. Its current-state address is the latest confirmed
  address for the stable rental post; raw historical rows remain untouched.
- CafeLand now extracts scoped `reales-location` and semantic `Vị trí:` values,
  rejects navigation garbage, and rejects `/moi-gioi/` profiles as rental
  details. Recent artifacts improved from one 16/20 run to repeated 20/20 runs,
  while 268 older latest rows still needed normal deferred recovery.
- Generic JSON-LD address extraction now uses a real-estate entity whitelist.
  ChoThueNha no longer relies on hard-coded office-address strings.
- A parsed HTTP detail response without an expected address is recorded as a
  fetch success and an address-extraction failure. The queue item receives
  normal retry/backoff instead of being removed as enriched.

## Targeted recovery

The recovery command only queues existing stable identities; it does not fetch
or write MySQL itself. At apply time, 288 of 307 missing rows were already in
the deferred queue. Eleven valid NhaTot rows were added. Eight CafeLand rows
were rejected as non-listing/profile URLs, and valid CafeLand missing rows were
already pending. Recovery continues after page discovery within the unchanged
per-source detail budget and source-access policy.

No database reset, historical rewrite, page-budget, detail-budget, schedule,
schema, robots, retry, or Airflow graph change was made.

## First normal-run validation

Scheduled run `2026-08-26T11:30:00Z` completed all nine tasks successfully.
NhaTot discovered its listing page first in 3.09 seconds (one successful page,
zero failed), then attempted 20 deferred details. All 20 fetches parsed an
address and 20 addressed versions were persisted. No parser miss or detail
failure occurred. The final current-state snapshot at 18:33:33 local contained
5,921 listings, 5,601 latest-known addresses and 320 missing (94.59%). The
absolute missing count rose because the same discovery run added 20 new NhaTot
listings faster than its unchanged 20-detail budget enriched old backlog; this
is normal queue growth, not loss of a previously confirmed address. The view
marked 42 latest rows as inherited (37 NhaTroVN, 5 NhaTot).

Recovery remains bounded by the unchanged normal source budgets and schedules.
CafeLand has 268 missing current states: 260 are pending and eight
non-listing/profile rows remain explicitly excluded. NhaTot has 52 and all are
pending after the new discovery. A final current-state recovery dry-run found
312 pending and no unqueued eligible rows. Coverage is therefore not marked
recovered yet.
