# RoomBeacon — Airflow-Driven Generic Crawler Orchestration

> **Trạng thái: CURRENT.** Airflow chỉ điều phối; application use cases giữ crawl behavior. Xem [Current Architecture](../architecture/CURRENT_ARCHITECTURE.md) cho dependency direction.

Tài liệu này mô tả kiến trúc và luồng vận hành điều phối Crawler thông qua **Apache Airflow UI** (Entry point chính thức của hệ thống).

---

## 1. Kiến trúc luồng điều phối (Orchestration Architecture)

```text
01_config_load_sources
  → 02_config_plan_crawls
  → 03_crawl_check_eligibility[]
  → 04_crawl_execute_source[]
  → 05_storage_save_bronze[]
  → 06_state_update_checkpoint[]
  → 07_analytics_refresh_duckdb
  → 08_assets_sync_minio
  → 09_report_run_summary
```

Tasks 03–06 giữ dynamic mapping theo source plan. Task 04 gọi application crawl
use case; task 05 là Bronze/MySQL persistence boundary. Historical DAG runs vẫn
hiển thị task IDs cũ.

- 01–02 = CONFIG
- 03–04 = CRAWL
- 05 = STORAGE
- 06 = STATE
- 07 = ANALYTICS
- 08 = ASSETS
- 09 = REPORT

`04_crawl_execute_source[]` là task thực sự thực hiện crawl website. Page,
listing, detail, deferred backlog và frontier vẫn là application internals,
không phải Airflow nodes.

`08_assets_sync_minio` là một task không mapped. Nó đọc unique image references
đã persist trong MySQL `post_images`, gọi application Asset Reconciler theo batch
bounded/fair, rồi lưu binary đã validate vào MinIO. Image failure không rollback
Bronze/MySQL đã commit. DAG `roombeacon_asset_reconciler` cũ chỉ còn là manual
recovery/backfill path (`schedule=None`); main crawler DAG là scheduled authority.

---

## 2. Các tham số Runtime (DAG Parameters)

| Tham số | Kiểu dữ liệu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `url` | `string` | `https://phongtro123.com/tinh-thanh/ho-chi-minh` | Đường dẫn danh mục cần crawl (hỗ trợ tự động các nguồn đã đăng ký như Phongtro123, NhaTot, v.v.). |
| `max_pages` | `integer` | `1` | Số trang listing tối đa cần duyệt (1 - 20). |
| `max_records` | `integer` | `20` | Số tin đăng tối đa cần trích xuất (1 - 500). |
| `crawl_details` | `boolean` | `false` | Bật/tắt việc thu thập chi tiết từng tin đăng (mặc định False cho bước kiểm chứng listing). |
| `max_details_per_run` | `integer` | `20` | Giới hạn số request detail trang con trong run. |

Trong flow production `AUTO`, `crawl_details` đến từ scheduled target của source;
các production adapters bật detail acquisition và vẫn bị giới hạn bởi
`max_details_per_run`. Default `debug_crawl_details=false` chỉ áp dụng cho
`DEBUG_SINGLE_TARGET` khi operator không bật explicit.

Budget này áp dụng riêng cho mỗi source execution. Production seeds hiện dùng
40 cho PhongTro123, 40 cho NhaTroVN và 20 cho NhaTot; debug/default và các source
khác vẫn là 20. Trước khi acquire listing
pages, crawler dùng budget để drain durable deferred backlog của source/target,
ưu tiên item chưa từng detail và chưa nằm trong retry backoff. Detail success giữ
TTL metadata qua các run; unchanged + TTL-valid không được fetch lại. Vì vậy 20
details/run là tốc độ progressive enrichment, không phải lifetime coverage cap.
Các source có queue và budget riêng nên backlog lớn không gây starvation chéo.

---

## 3. Hướng dẫn sử dụng trên Airflow UI

1. Truy cập Airflow UI tại: `http://localhost:8080` (hoặc cổng cấu hình).
2. Tìm DAG: `roombeacon_crawler`.
3. Bấm nút **Trigger DAG w/ config** (biểu tượng Play có bánh răng).
4. Nhập đường dẫn `url` mong muốn (ví dụ: `https://phongtro123.com/tinh-thanh/ho-chi-minh` hoặc `https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh`).
5. Bấm **Trigger** để bắt đầu phiên crawl.
6. Mở Task Log của `04_crawl_execute_source[]` để theo dõi crawl; xem
   `05_storage_save_bronze[]` cho persistence.

## 4. Source schedule matrix

| Source | Status | Strategy | Listing | Detail | Schedule |
|---|---|---|---|---|---|
| PhongTro123 | active | HTTP | pagination | budget 40 | 45 min |
| NhaTroVN | active | HTTP | pagination | budget 40 | 60 min |
| NhaTot | active | Browser | forward-only | budget 20 | 60 min |
| BatDongSan / MuaBan | controlled | HTTP challenged | policy-controlled | disabled | existing |
| ChoThueNha | Batch 1 active | HTTP | first page | budget 20 | 120 min |
| TroMoi | Batch 1 active | HTTP | first page; query pages denied by robots | budget 20 | 120 min |
| Guland | Batch 1 active | HTTP | first page; JS pagination pending | budget 20 | 120 min |
| ChoThuePhongTro / Mogi | Batch 2 disabled | HTTP | query pagination | parser ready | none |
| CafeLand | Batch 3 disabled | HTTP | path pagination | parser ready | none |
| PhongTroToanQuoc | blocked/disabled | Browser candidate | unverified | disabled | none |

---

## 5. Nguyên tắc thiết kế & Bảo mật

* **Độc lập kiến trúc:** Crawler Core không import Airflow. Chiều phụ thuộc chỉ đi một chiều: `Airflow DAG -> Crawler`.
* **Generic & Source-Agnostic:** URLValidator không chứa domain hardcode. Toàn bộ logic theo domain nằm trong Adapter.
* **An toàn URL:** Chặn hoàn toàn SSRF (localhost, 127.0.0.1, private IP, AWS/GCP metadata endpoints).
* **Tuân thủ Robots.txt:** `ROBOTS_DENIED` dừng an toàn và chuyển trạng thái Airflow thành `SKIPPED`, tuyệt đối không bypass.
* **Bảo vệ Secret:** Toàn bộ log của Airflow task không in credentials hay access keys.
* **CLI vai trò:** CLI (`python -m roombeacon_crawler.main`) chỉ phục vụ chẩn đoán (`--diagnostics`), debug và smoke test cục bộ.
