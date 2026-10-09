# Danh Mục Các Luồng Điều Phối (DAG Catalog)

> **Plane:** Control
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** hỗn hợp — xem bảng
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [AIRFLOW_ARCHITECTURE.md](AIRFLOW_ARCHITECTURE.md), [../02-ingestion/CRAWLER_ARCHITECTURE.md](../02-ingestion/CRAWLER_ARCHITECTURE.md)

---

## 1. Danh Mục 6 DAGs Thực Tế trong Mã Nguồn

| DAG ID | Tệp mã nguồn (`file:line`) | Domain | Chu kỳ chạy (Schedule) | Trạng thái kỹ thuật |
|---|---|---|---|:---:|
| **`roombeacon_crawler`** | [`airflow/dags/crawler/roombeacon_crawler.py:174`](../../airflow/dags/crawler/roombeacon_crawler.py#L174) | Ingestion | `*/5 * * * *` (Mỗi 5 phút) | **IMPLEMENTED & FROZEN** |
| **`roombeacon_bronze_reconciler`** | [`airflow/dags/reconciliation/roombeacon_bronze_reconciler.py:14`](../../airflow/dags/reconciliation/roombeacon_bronze_reconciler.py#L14) | Ingestion | `0 */6 * * *` (Mỗi 6 giờ) | **IMPLEMENTED** |
| **`roombeacon_asset_reconciler`** | [`airflow/dags/assets/roombeacon_asset_reconciler.py:14`](../../airflow/dags/assets/roombeacon_asset_reconciler.py#L14) | Ingestion | `None` (Kích hoạt thủ công / Backfill) | **IMPLEMENTED** |
| **`roombeacon_silver_materializer`** | [`airflow/dags/analytics/roombeacon_silver_materializer.py:16`](../../airflow/dags/analytics/roombeacon_silver_materializer.py#L16) | Processing | `0 2 * * *` (2h sáng hàng ngày) | **IMPLEMENTED** |
| **`roombeacon_geocoding`** | [`airflow/dags/enrichment/roombeacon_geocoding.py:9`](../../airflow/dags/enrichment/roombeacon_geocoding.py#L9) | Processing | `17 * * * *` (Phút 17 mỗi giờ) | **IMPLEMENTED (PARTIAL)** |
| **`roombeacon_system_healthcheck`** | [`airflow/dags/system/roombeacon_healthcheck.py:39`](../../airflow/dags/system/roombeacon_healthcheck.py#L39) | Ops | `*/15 * * * *` (Mỗi 15 phút) | **IMPLEMENTED** |

---

## 2. Chi Tiết Từng DAG Thực Tế

### 2.1. `roombeacon_crawler` (FROZEN — Chuỗi 9 Tasks)
DAG cào dữ liệu cốt lõi, điều phối qua chuỗi 9 bước tuyến tính:
1. `01_config_load_sources`: Nạp cấu hình scheduled seeds từ các Source Adapters đã đăng ký.
2. `02_config_plan_crawls`: Lập kế hoạch cào (chọn các target đến hạn dựa trên checkpoints).
3. `03_crawl_check_eligibility`: Kiểm tra điều kiện tiên quyết (URL hợp lệ, robots.txt, circuit breaker health). *(Mapped task)*
4. `04_crawl_execute_source`: Kích hoạt `CrawlRunner` thực hiện cào dữ liệu và sinh artifacts. *(Mapped task)*
5. `05_storage_save_bronze`: Nạp artifacts và lưu trữ vào MySQL Bronze trong transaction UoW. *(Mapped task)*
6. `06_state_update_checkpoint`: Cập nhật mốc checkpoint thành công và danh sách tin đã thấy. *(Mapped task)*
7. `07_analytics_refresh_duckdb`: Tải lại và làm mới các Analytical Views trong DuckDB.
8. `08_assets_sync_minio`: Kích hoạt một đợt tải ảnh bounded/fair scheduling vào MinIO S3.
9. `09_report_run_summary`: Báo cáo tổng hợp số liệu của phiên cào.

### 2.2. `roombeacon_bronze_reconciler`
- **Mục đích:** Quét toàn bộ các thư mục artifacts trên đĩa host (`data/bronze/`) để đối chiếu với các bản ghi quan sát trong bảng `rental_post_versions` của MySQL.
- **Hành động:** Tự động phát hiện các run bị thiếu sót trong MySQL (ví dụ do sập nguồn đột ngột khi crawler đang ghi) và kích hoạt nạp bù tự động (`self-healing`).

### 2.3. `roombeacon_asset_reconciler`
- **Mục đích:** Chạy độc lập để tải bù và đối soát hình ảnh từ bảng `post_images` vào MinIO (`roombeacon-assets`).
- **Cơ chế:** Áp dụng `FairAssetScheduler`, kiểm tra Magic Bytes và lưu trạng thái bền vững tại `data/state/assets/`.

### 2.4. `roombeacon_silver_materializer`
- **Mục đích:** Xây dựng và xuất bản tệp Canonical Silver Parquet định kỳ mỗi ngày.
- **Quy trình 4 bước:**
  1. `verify_analytics_connection`: Xác minh view `v_latest_posts` khả dụng và tuân thủ ràng buộc 1 dòng / 1 bài đăng.
  2. `materialize_silver`: Gọi `notebooks.utils.silver_processing.build_silver_dataset` và chạy qua Pre-Silver Quality Gate; xuất ra file Parquet tạm.
  3. `validate_silver_output`: Đọc lại file Parquet, kiểm tra số dòng, số cột (80 cột) và tính duy nhất của ID.
  4. `summarize_silver_run`: Thay thế nguyên tử (atomic replace) vào `data/silver/rental_listings.parquet` và xuất bản siêu dữ liệu JSON.

### 2.5. `roombeacon_geocoding`
- **Mục đích:** Tác vụ làm giàu toạ độ địa lý chạy mỗi giờ (Phút 17).
- **Quy trình:**
  1. `enrich_addresses`: Gọi `GeocodeEnrichmentJob` với `NominatimReverseGeocoder` xử lý một batch nhỏ (mặc định 10 records).
  2. `refresh_addresses`: Làm mới view địa chỉ DuckDB sau khi làm giàu.
- **Hiện trạng:** Đang ở mức thử nghiệm (PARTIAL); tỷ lệ toạ độ tin cậy mới đạt 1.7%.

### 2.6. `roombeacon_system_healthcheck`
- **Mục đích:** Kiểm tra sức khỏe toàn diện của hạ tầng: kết nối MySQL Bronze, kết nối MySQL Airflow, MinIO Object Storage, và dung lượng đĩa khả dụng.

---

## 3. Các DAGs Mục Tiêu Theo Bản Vẽ Kiến Trúc (PLANNED)

| DAG ID dự kiến | Mặt phẳng (Plane) | Mục đích nghiệp vụ | Kích hoạt (Trigger) |
|---|---|---|---|
| **`roombeacon_raw_archiver`** | Raw & Bronze Storage | Nén và đóng gói các tệp JSON/HTML thô lên MinIO RAW, dọn dẹp đĩa host theo chính sách retention. | Lịch định kỳ hàng ngày. |
| **`roombeacon_curated_observations`** | Data Processing & Silver | DuckDB quét MySQL Bronze và kết xuất tệp Parquet Historical Curated Observations làm nguồn cấp cho ClickHouse DW. | Chạy sau khi cào và đối soát Bronze hoàn tất. |
| **`roombeacon_model_shadow`** | Machine Learning | Nạp model LightGBM F4 chạy dự đoán bóng, theo dõi drift và phân tích sai số trên dữ liệu Silver mới. | Kích hoạt khi Silver Parquet được cập nhật. |
