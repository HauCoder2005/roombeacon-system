# Ma Trận Hiện Trạng Triển Khai (Implementation Status)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** hỗn hợp — xem bảng
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md), [GAP_AND_MIGRATION_PLAN.md](GAP_AND_MIGRATION_PLAN.md)

---

## 1. Ma Trận Thành Phần × Trạng Thái × Bằng Chứng Mã Nguồn

| Mặt phẳng theo Bản vẽ | Thành phần kỹ thuật | Trạng thái kỹ thuật | Bằng chứng mã nguồn & Cấu hình (`file:line`) |
|---|---|:---:|---|
| **External Actors** | 12 Cổng thông tin BĐS nguồn | **IMPLEMENTED** | Nguồn công khai: Phongtro123, Chothuephongtro, Cafeland, Mogi, Nhatot... |
| | Developer / Operator | **IMPLEMENTED** | Quản trị viên điều hành qua Airflow Webserver UI (port 8080) và Bash CLI. |
| **Orchestration Plane** | Apache Airflow Runtime (Scheduler, API Server, Triggerer, Dag Processor) | **IMPLEMENTED** | [`docker-compose.yml:365-690`](../../docker-compose.yml#L365-L690); image `roombeacon-airflow-custom:3.3.1`; metadata DB tại `.env.example:55-75`. |
| | Ingestion DAG (`roombeacon_crawler`) | **IMPLEMENTED & FROZEN** | [`airflow/dags/crawler/roombeacon_crawler.py:174`](../../airflow/dags/crawler/roombeacon_crawler.py#L174); chuỗi 9 tasks hoàn chỉnh. **Đóng băng hoàn toàn.** |
| | Reconciler DAGs (`bronze_reconciler`, `asset_reconciler`) | **IMPLEMENTED** | [`airflow/dags/reconciliation/roombeacon_bronze_reconciler.py:14`](../../airflow/dags/reconciliation/roombeacon_bronze_reconciler.py#L14), [`airflow/dags/assets/roombeacon_asset_reconciler.py:14`](../../airflow/dags/assets/roombeacon_asset_reconciler.py#L14). |
| | Processing DAGs (`silver_materializer`, `geocoding`) | **IMPLEMENTED / PARTIAL** | [`airflow/dags/analytics/roombeacon_silver_materializer.py:16`](../../airflow/dags/analytics/roombeacon_silver_materializer.py#L16) (`0 2 * * *`), [`airflow/dags/enrichment/roombeacon_geocoding.py:9`](../../airflow/dags/enrichment/roombeacon_geocoding.py#L9) (batch 10 records). |
| | System Healthcheck DAG (`roombeacon_system_healthcheck`) | **IMPLEMENTED** | [`airflow/dags/system/roombeacon_healthcheck.py:39`](../../airflow/dags/system/roombeacon_healthcheck.py#L39); chu kỳ 15 phút. |
| **Crawler Execution Plane (FROZEN)** | Lõi Engine (`CrawlRunner`) & Processors | **IMPLEMENTED & FROZEN** | [`crawler/src/roombeacon_crawler/pipeline/crawl_runner.py:182`](../../crawler/src/roombeacon_crawler/pipeline/crawl_runner.py#L182); Clean Architecture 428 LOC. |
| | Bộ đăng ký đa nguồn (`SourceRegistry`) | **IMPLEMENTED & FROZEN** | [`crawler/src/roombeacon_crawler/sources/registry.py:22`](../../crawler/src/roombeacon_crawler/sources/registry.py#L22); 12 adapters. |
| | 9 Source Adapters hoạt động thực tế | **IMPLEMENTED & FROZEN** | `phongtro123`, `chothuephongtro`, `cafeland`, `mogi`, `nhatot`, `muaban`, `nhatrovn`, `tromoi`, `chothuenha`. |
| | 3 Source Adapters giới hạn / tắt | **PARTIAL / DISABLED** | `batdongsan` (card OK, detail tắt); `guland` (vướng JS); `phongtrotoanquoc` (`ENABLED=False`). |
| | Chính sách Robots, RateLimit, Retry | **IMPLEMENTED & FROZEN** | [`crawler/src/roombeacon_crawler/policies/robots_policy.py`](../../crawler/src/roombeacon_crawler/policies/robots_policy.py), `rate_limit_policy.py`, `retry_policy.py`. |
| **Raw & Bronze Storage Plane** | MySQL Bronze Database (`roombeacon_bronze`) | **IMPLEMENTED** | `docker-compose.yml:118-185` (port host 3307); 11 bảng quan hệ trong [`schema.py:9-183`](../../crawler/src/roombeacon_crawler/infrastructure/mysql/schema.py#L9-L183); dung lượng ~13.0 GB. Xem [ADR-001](../adr/ADR-001.md). |
| | MinIO Object Storage (`roombeacon-assets` - Images) | **IMPLEMENTED** | `docker-compose.yml:315-360`; dung lượng ~3.5 GB; chính sách bucket tại `infrastructure/minio/bootstrap.sh`. |
| | Local JSON Bronze Artifacts | **IMPLEMENTED** | Thư mục `data/bronze/` (~2.0 GB); lưu JSON phân cấp nguồn/ngày/phiên cào. |
| | MinIO RAW (HTML & JSON Uploader) | **PLANNED** | [`persistence.py:61`](../../crawler/src/roombeacon_crawler/application/orchestration/persistence.py#L61) ghi log `minio bypassed`. Nét liền trên bản vẽ nhưng chưa có code. Cần sửa crawler (đang FROZEN) $\rightarrow$ **Gap mở**. |
| | Nhánh lưu trữ `feat/storage-plane-alignment` | **PLANNED** | `rental_post_sightings`, `version-on-change`, con trỏ JSON, DAG `roombeacon_raw_archiver`, DAG `roombeacon_curated_observations`. |
| **Data Processing & Silver Plane** | Bronze Snapshot Parquet Export | **IMPLEMENTED** | [`analytics/bronze/snapshot.py:26-30`](../../analytics/bronze/snapshot.py#L26-L30); xuất `latest_posts.parquet` và `raw_evidence.parquet` (132,436 tin). |
| | DuckDB In-Memory OLAP Engine & 13 Views | **IMPLEMENTED** | [`analytics/duckdb/views.py:18-32`](../../analytics/duckdb/views.py#L18-L32); 13 required SQL views nạp tự động; tệp host `data/duckdb/`. Xem [ADR-003](../adr/ADR-003.md). |
| | Canonical Silver Parquet Dataset | **IMPLEMENTED** | File `data/silver/rental_listings.parquet` (80 cột, 132,436 dòng); code tại [`notebooks/utils/silver_processing.py`](../../notebooks/utils/silver_processing.py) và [`SilverMaterializer`](../../analytics/silver/materializer.py#L52). |
| | Chuẩn hóa Địa chỉ & Bản đồ Hành chính | **IMPLEMENTED** | [`notebooks/utils/address_parser.py`](../../notebooks/utils/address_parser.py), `ward_normalization.py` (Gazetteer Việt Nam). |
| | Historical Curated Observations (Parquet) | **PLANNED** | Nét đứt trên bản vẽ. Do DuckDB sinh ra từ SCD2 versions + sightings; nguồn cấp cho ClickHouse Data Warehouse. |
| **Analytics & Data Warehouse Plane** | ClickHouse Data Warehouse (OLAP) | **FUTURE** | Toàn bộ Plane là **FUTURE**. Gồm: Analytical/Dimensional Modeling, Fact tables (`fact_listing_observation`, snapshot), Dimensions (`dim_date`, `dim_location`, `dim_source`), Gold / Data Marts (`agg_market_daily`, etc.). Xem [ADR-004](../adr/ADR-004.md). |
| **Machine Learning Plane** | ML Processing / Feature Contracts (F1–F5) | **IMPLEMENTED** *(Notebook)* | [`notebooks/03_roombeacon_processing.ipynb`](../../notebooks/03_roombeacon_processing.ipynb); rào chắn chống rò rỉ dữ liệu. |
| | Modeling & Benchmark V3 Protocol | **IMPLEMENTED** *(Notebook)* | [`notebooks/04_roombeacon_modeling.ipynb`](../../notebooks/04_roombeacon_modeling.ipynb); thẩm định nhóm theo thời gian (Group-aware Temporal Split). |
| | Champion Model Artifact (LightGBM F4 RAW) | **IMPLEMENTED** *(Artifact)* | Khóa tại `data/modeling/roombeacon_price_benchmark_v3/champion_model.joblib` (MAE 904k VND, R² 0.22). |
| | Shadow Validation & Drift Monitoring | **IMPLEMENTED** *(Notebook)* | [`notebooks/06_roombeacon_shadow_validation.ipynb`](../../notebooks/06_roombeacon_shadow_validation.ipynb). |
| | Performance Benchmark Runtime | **IMPLEMENTED** *(Notebook)* | [`notebooks/07_roombeacon_performance_benchmark.ipynb`](../../notebooks/07_roombeacon_performance_benchmark.ipynb). |
| **Search & Discovery Plane** | Nearby Rental Search (Spatial / Haversine) | **IMPLEMENTED** *(Prototype)* | [`notebooks/05_roombeacon_nearby_rental_search.ipynb`](../../notebooks/05_roombeacon_nearby_rental_search.ipynb); đọc trực tiếp từ Silver Parquet, tính Haversine vector hóa kết hợp fallback 3 cấp. |
| **Application Serving Plane** | Model Serving Runtime | **FUTURE** | Runtime nạp Champion LightGBM phục vụ suy luận dự báo giá. |
| | Backend API Gateway (FastAPI) | **FUTURE** | Cung cấp REST/GraphQL API kết nối Search, ML và Gold Data Marts. |
| | MySQL Application OLTP (`roombeacon_app`) | **FUTURE** | Lưu `users`, `favorites`, `saved_searches`. **Không chứa tin đăng!** Xem [ADR-002](../adr/ADR-002.md). |
| | Web / Mobile Application | **FUTURE** | Giao diện người dùng cuối tìm kiếm phòng trọ và xem thống kê thị trường. |

---

## 2. Danh Mục Rủi Ro Mở Kỹ Thuật (Open Risks & Gaps)

### Rủi ro 1: Tốc độ Tăng trưởng Dung lượng MySQL Bronze (~13.0 GB sau 10 ngày)
- **Tình trạng:** Database MySQL tăng nhanh, nghi vấn do chèn version mới mỗi phiên cào dù `content_hash` không đổi (kết hợp tần suất cào 5 phút).
- **Kế hoạch ứng phó:** Nhánh `feat/storage-plane-alignment` đang chuẩn bị các giải pháp: `rental_post_sightings`, `version-on-change`, tách `source_payload` thành con trỏ (xem [ADR-001](../adr/ADR-001.md)).

### Rủi ro 2: Thiếu Lưu trữ MinIO RAW (HTML, JSON) — Gap Mở Do Đóng Băng Crawler
- **Tình trạng:** Trên bản vẽ kiến trúc, khối MinIO (RAW: HTML, JSON, Images) vẽ nét liền (ngụ ý luồng chuẩn), nhưng trong thực tế code `persistence.py:61` ghi `minio bypassed`, chỉ lưu JSON artifacts trên đĩa host.
- **Rào cản:** Để tải Raw HTML lên MinIO, cần sửa mã nguồn crawler. Nhưng **Crawler Execution Plane hiện đang ĐÓNG BĂNG (FROZEN)** theo chỉ đạo của chủ dự án. Do đó, đây là một **Gap mở** cần giải quyết khi Ingestion Plane được phê duyệt mở khóa.

### Rủi ro 3: Thiếu Chính sách Retention cho JSON Bronze Artifacts (~2.0 GB)
- **Tình trạng:** Thư mục `data/bronze` lưu hàng ngàn tệp JSON của từng run, đang trùng vai trò lưu trữ với MySQL Bronze nhưng chưa có quy trình nén, archive ra S3 hoặc xóa định kỳ.

### Rủi ro 4: Kiểm toán Tính Khả Lặp Clean Clone (Audit 2026-09-16)
- **Tình trạng:** Biên bản kiểm toán ngày 16/09/2026 ([`docs/archive/audit/2026-09-16-clean-clone-recovery.md`](../archive/audit/2026-09-16-clean-clone-recovery.md)) kết luận môi trường **NOT REPRODUCIBLE** theo hợp đồng `git clone + docker compose up` trên máy trống hoàn toàn nếu thiếu cấu hình quyền ghi thư mục host UID 1000 và các tệp `.env`.

### Rủi ro 5: Trạng thái Bộ Test Suite (Audit 2026-09-20)
- **Tình trạng:** Biên bản kiểm toán ngày 20/09/2026 ([`docs/archive/audit/2026-09-20-crawler-system-retest.md`](../archive/audit/2026-09-20-crawler-system-retest.md)) ghi nhận kết quả chạy test: **441 passed, 15 failed, 3 collection errors**. Các lỗi gồm thiếu Airflow dependencies trên host, lệch hợp đồng cấu hình detail budget và quyền MinIO.

### Rủi ro 6: Độ Phủ Toạ độ Địa lý Quá Thấp (~1.7%)
- **Tình trạng:** Chỉ 2,277 trong tổng số 132,436 tin đăng có toạ độ thực sự đáng tin cậy. Dù có 118,864 tin có địa chỉ văn bản, nhưng tiến trình Geocoding tự động chưa được triển khai ở quy mô lớn, khiến tính năng tìm kiếm theo bán kính phải lùi bước về tìm kiếm theo Phường/Quận cho 98.3% tin đăng.
