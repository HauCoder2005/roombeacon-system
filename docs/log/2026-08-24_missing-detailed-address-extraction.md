# Incident — Missing Detailed Address Extraction

> Ngày: 2026-08-24  
> Thành phần: detail parsers, Bronze mapping và address persistence  
> Trạng thái: **RESOLVED**

## Triệu chứng

Nhiều observations chỉ có district/city như `Quận 12, TP Hồ Chí Minh`, dù detail page công bố street/ward/district/city. Giá trị coarse hữu ích cho listing discovery nhưng không phải full address.

## Phạm vi và root cause

- PhongTro123 detail page có hàng semantic `Địa chỉ:` và JSON-LD `PostalAddress.streetAddress`; parser cũ chỉ tìm generic address class. Module còn thiếu import `re`, nên nhánh derive listing ID có thể làm cả parse rơi vào safe failure.
- NhaTroVN detail page có JSON-LD `Residence.address` và address node trong standalone room card; parser cũ chỉ phụ thuộc class `rs-card-address` toàn document.
- `BronzeMapper` đã ưu tiên `detail.address_raw` cho `address_raw`/`location_raw`; loader và persistence cũng đã ưu tiên address detail. Data loss bắt đầu ở extraction, không phải do schema.

## Source audit

| Source | Listing location | Detail full address | Active extraction |
|---|---|---|---|
| phongtro123 | coarse location | **AVAILABLE** | semantic `Địa chỉ:` row, JSON-LD fallback; fixed and live smoke PASS |
| nhatrovn | coarse hoặc masked street/location | **AVAILABLE** | `Residence.address`, scoped main-card fallback; fixed and live smoke PASS |
| nhatot | coarse location | **AVAILABLE** | Product PostalAddress, exact semantic address section; fixed and live browser smoke PASS |
| batdongsan | coarse location | **BLOCKED/NOT USED** trong scheduled flow | parser tồn tại nhưng capability `detail_fetch_supported=False` |
| muaban | coarse location | **BLOCKED/NOT USED** trong scheduled flow | parser tồn tại nhưng capability `detail_fetch_supported=False` |

Không báo full-address support cho source bị policy/capability chặn.

## Fix

- Giữ `ListingDetailRaw.address_raw`/`RentalBronzeRecord.address_raw` làm full source-near raw value; không thêm alias field hoặc migration.
- PhongTro123 ưu tiên label/value relationship, không dùng row index hoặc global address search.
- NhaTroVN ưu tiên structured Residence data, sau đó chỉ tìm trong main listing card.
- NhaTot ưu tiên Product/Offer PostalAddress, sau đó exact `Địa chỉ bất động sản` section; đã bỏ generic `address`/`location` scan.
- Recommended listings, breadcrumb và modal không tham gia fallback.
- Detail full address tiếp tục thắng listing coarse location trong `BronzeMapper`.
- Production scheduled targets bật `crawl_details=True`; trước runtime validation,
  các adapter vô tình dùng default `False`, khiến normal DAG chỉ ghi lightweight
  observations và không gọi detail parser.

## Persistence và analytics

`post_addresses.full_address_text` đã đủ dung lượng và được ghi từ `observation.address_raw or observation.location_raw`. `v_observations` expose giá trị đó ở `address_raw` và `location_raw`; `v_latest_posts.location_raw` cũng lấy `full_address_text`. Đây là Bronze/latest-state representation, không phải Silver cleaning.

## Validation

- Sanitized fixture regressions bao phủ semantic row, structured data, missing/malformed/district-only, recommendation/breadcrumb isolation và merge precedence.
- Focused reset operations suite: 22/22 PASS; address regressions remain included in full suite.
- Full regression sau runtime fix: 314/314 PASS.
- DAG import validation: 5/5 PASS.
- Controlled live smoke qua `DetailCrawlPipeline`: NhaTroVN PASS; PhongTro123 PASS; NhaTot PASS. Không persist dữ liệu smoke.

## Reset và real recrawl

`scripts/reset_roombeacon_data.py` hỗ trợ ba mode loại trừ nhau: `--dry-run`,
`--backup-only`, và destructive `--confirm-reset-roombeacon`. Wrapper chạy command
trong Airflow scheduler container để dùng đúng RoomBeacon runtime config và Docker
network; operator không truyền host hoặc credential. Replica là optional
infrastructure concern, không phải reset gate. MinIO objects không bị reset nên
không có MinIO authentication/inventory gate.

Pre-reset dry-run đã PASS 12 tables. Backup
`/data/backups/reset_20260824_064739` có manifest `VERIFIED`, logical dump non-empty
và 921 checksum entries. Confirmed reset tạo thêm verified safety backup
`/data/backups/reset_20260824_064821`, reset đúng 12 Bronze business tables và
application-owned `bronze/state/discovery/manifests`. Clean baseline xác nhận cả
12 tables bằng 0 và không còn stale state. Airflow metadata, MinIO binaries và
Docker volumes không bị xóa.

Run đầu tiên `manual__2026-08-24T06:50:12.455213+00:00` hoàn tất toàn bộ DAG graph
nhưng chỉ tạo lightweight observations; runtime metrics đã phát hiện
`detail_requested=0`. Sau khi bật detail acquisition tại scheduled source seeds,
focused tests, full regression và DAG imports đều PASS. Retry run
`manual__2026-08-24T06:58:36.839336+00:00` chứng minh NhaTot và NhaTroVN; supported
single-target DAG run `manual__2026-08-24T07:01:02.415125+00:00` chứng minh
PhongTro123. Mỗi source có 20 detail requests thành công và 20 full addresses
persisted; `detail_address_parse_failed=0`.

## Data Science impact

Coarse location không đủ cho geocoding, street/ward grouping hoặc location-quality analysis. Runtime report tiếp tục tách `coarse_location_coverage` và `full_address_coverage`; không gộp thành một “address coverage”.

Run summary hiện xuất metrics theo source: `full_address_present`, `full_address_missing`, `coarse_only_address`, `detail_address_extracted` và `detail_address_parse_failed`. Fetch failure không bị gán nhầm thành parse failure. Post-recrawl integrity checks: orphan versions 0, posts without versions 0, same-run duplicates 0 và stable-identity duplicates 0. DuckDB `v_observations` có 1,961 rows; `v_latest_posts` có đúng 1,899 rows cho 1,899 distinct listings.

## Progressive enrichment follow-up

Coverage audit phát hiện detail success từ deferred processor ban đầu chỉ ghi vào
same-run `updated_seen_meta`. Page loop sau đó đọc snapshot cũ, ghi đè timestamp
và enqueue lại cùng listing khi budget đã hết. Scheduler nay ưu tiên durable
backlog trước new/changed/TTL-expired work; card processing đọc same-run metadata
trước persisted snapshot và giữ `detail_status`. Retry failures dùng exponential
backoff, còn never-attempted items đi trước retries. Simulation 50 eligible items,
budget 10 qua ba processor restarts đạt 30 unique details, backlog 40 → 30 → 20,
overlap giữa các run bằng 0.

### Detail metric semantics

Runtime có hai boundary detail: backlog được xử lý trước page acquisition và
immediate detail của card vừa parse. `details_success`/`details_failed` là tổng
hai boundary; `detail_succeeded`/`detail_failed` đi cùng `detail_requested` và chỉ
đo immediate card path; `deferred_*` là breakdown backlog. Log kết thúc run và
Airflow acquisition summary phải dùng aggregate totals, đồng thời in breakdown
Immediate/Deferred riêng. Trước fix, CrawlRunner đọc hai session fields aggregate
không bao giờ được cập nhật và summary ghi immediate-only counter, nên một run có
20 Bronze details từ backlog bị hiển thị sai thành 0 detail success.

Ví dụ NhaTot run `run_20260824_073134`: backlog 9 được xử lý thành công, 11 card
được detail ngay, tổng 20. Trong 25 page cards còn lại, 8 unchanged + TTL-valid
được skip và 6 hết budget được deferred; queue vì vậy thỏa `9 - 9 + 6 = 6`.
34 observations là 9 backlog observations cộng 25 page-card observations, không
phải 34 detail-eligible requests cùng lúc.

Sau khi progressive scheduling và identity propagation đã có regression coverage,
production throughput được tăng có giới hạn: PhongTro123 và NhaTroVN từ 20 lên
40 detail requests cho mỗi eligible source execution; NhaTot và các source còn
lại giữ 20. Page budget, Airflow schedule, retry/rate-limit/robots/source-health,
frontier, parser và persistence không đổi. Mức 40 phải qua ba normal executions
mỗi source; nếu xuất hiện 429/access challenge hoặc failure-rate bất thường thì
rollback về 20.

### Production validation at budget 40

Ba scheduled NORMAL executions liên tiếp đã xác nhận mức 40 ổn định. Không run
nào dùng FORCE_FULL; schedule, page budget và source policy không thay đổi.

| Source | Run | Attempted | Succeeded | Failed | Backlog before | New deferred | Backlog after | Repeated | HTTP 429 | Access challenge | Avg latency |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PhongTro123 | `run_20260824_100003` | 40 | 40 | 0 | 957 | 7 | 924 | 0 | 0 | 0 | 791.88 ms |
| PhongTro123 | `run_20260824_111503` | 40 | 40 | 0 | 924 | 0 | 884 | 0 | 0 | 0 | 950.96 ms |
| PhongTro123 | `run_20260824_123003` | 40 | 40 | 0 | 884 | 2 | 846 | 0 | 0 | 0 | 810.17 ms |
| NhaTroVN | `run_20260824_100003` | 40 | 39 | 1 | 812 | 0 | 773 | 0 | 0 | 0 | 615.94 ms |
| NhaTroVN | `run_20260824_111503` | 40 | 40 | 0 | 773 | 1 | 734 | 0 | 0 | 0 | 522.96 ms |
| NhaTroVN | `run_20260824_123003` | 40 | 40 | 0 | 734 | 0 | 694 | 0 | 0 | 0 | 490.22 ms |

NhaTroVN có một `not_found` ở execution đầu (1/120 attempts); item đi qua retry
policy hiện hữu và hai execution sau không có failure. Không có 429 hoặc access
challenge. Exact stable-identity overlap giữa các execution liên tiếp bằng 0.
MySQL read-only verification xác nhận toàn bộ 239/239 detail-success identities
có `post_addresses.full_address_text` và giá trị full address khớp artifact
(PhongTro123 120/120, NhaTroVN 119/119).

Kết luận: giữ budget 40 cho PhongTro123 và NhaTroVN. Backlog giảm lần lượt
957 → 846 và 812 → 694; rollback về 20 không cần thiết. Mức 60 chỉ có thể
được cân nhắc trong một thay đổi và validation riêng, không thuộc lần này.
