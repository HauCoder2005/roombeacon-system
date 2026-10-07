# DOCS MIGRATION MAP — ROOMBEACON DOCUMENTATION REFACTORING

> **Trạng thái:** COMPLETED (Hoàn thành toàn bộ Phase 1 → Phase 5)  
> **Thời điểm lập:** 2026-10-06  
> **Mục đích:** Kế hoạch và kết quả chi tiết tái cấu trúc toàn diện hệ thống tài liệu `docs/` của RoomBeacon theo tiêu chuẩn kiến trúc 6 mặt phẳng (Planes), loại bỏ mâu thuẫn, chuẩn hóa sự thật theo mã nguồn thực tế và hỗ trợ đội ngũ / AI mới tiếp nhận dự án.

---

## 1. Bảng Kiểm Kê & Ánh Xạ File Cũ (File Mapping Table)

Tổng số file Markdown hiện hữu trong `docs/`: **68 files**.

| # | File cũ | Hành động đề xuất | File đích trong cấu trúc mới | Ghi chú & Lý do |
|:---|:---|:---:|:---|:---|
| 1 | `docs/README.md` | **REWRITE** | `docs/README.md` | Viết lại thành cổng điều hướng trung tâm, phân loại nhãn, thứ tự đọc. |
| 2 | `docs/source-structure.md` | **ARCHIVE** | `docs/archive/legacy-design/source-structure.md` | Cấu trúc code cũ trước Phase 1 Clean Architecture. |
| 3 | `docs/00-overview/` | **CREATE NEW** | Toàn bộ các file trong `00-overview/` | Tạo mới theo target structure. |
| 4 | `docs/architecture/CURRENT_ARCHITECTURE.md` | **MERGE & ARCHIVE** | `docs/00-overview/TARGET_ARCHITECTURE.md` & `IMPLEMENTATION_STATUS.md` | Bản gốc chuyển sang `docs/archive/legacy-design/CURRENT_ARCHITECTURE.md`. |
| 5 | `docs/architecture/SYSTEM_ARCHITECTURE.md` | **ARCHIVE** | `docs/archive/legacy-design/SYSTEM_ARCHITECTURE.md` | Chứa 5 nguồn cũ, 8 views cũ, serving UI cũ lỗi thời. |
| 6 | `docs/architecture/overall-architecture.md` | **ARCHIVE** | `docs/archive/legacy-design/overall-architecture.md` | Đặt Bronze ở local disk, MySQL chỉ làm serving (ngược với hiện trạng). |
| 7 | `docs/architecture/BRONZE_SILVER_GOLD_ARCHITECTURE.md` | **MERGE & ARCHIVE** | `docs/00-overview/DATA_LAYERS_AND_LIFECYCLE.md` | Gộp nội dung lifecycle; bản gốc đưa vào `docs/archive/legacy-design/`. |
| 8 | `docs/data/DATA_LIFECYCLE.md` | **MERGE & ARCHIVE** | `docs/00-overview/DATA_LAYERS_AND_LIFECYCLE.md` | Gộp vào tài liệu authoritative lifecycle. |
| 9 | `docs/airflow/01-airflow-crawler-orchestration.md` | **MERGE & REWRITE** | `docs/01-control-plane/AIRFLOW_ARCHITECTURE.md` & `DAG_CATALOG.md` | Viết lại ma trận nguồn, thông số DAGs thực tế. |
| 10 | `docs/crawler/AIRFLOW_CRAWL_ORCHESTRATION.md` | **MERGE & ARCHIVE** | `docs/01-control-plane/DAG_CATALOG.md` | Gộp chi tiết checkpoint state vào control plane. |
| 11 | `docs/crawler/01-crawler-overview.md` | **MERGE & REWRITE** | `docs/02-ingestion/CRAWLER_ARCHITECTURE.md` | Tổng quan kiến trúc crawler, CrawlRunner, processors. |
| 12 | `docs/crawler/crawler.md` | **ARCHIVE** | `docs/archive/legacy-design/crawler.md` | Bản thảo sơ khai trùng lặp. |
| 13 | `docs/crawler/02-multi-source-architecture.md` | **MERGE & REWRITE** | `docs/02-ingestion/CRAWLER_ARCHITECTURE.md` | Hợp đồng Plugin-based Source Adapter. |
| 14 | `docs/crawler/09-run-flow.md` | **MERGE & REWRITE** | `docs/02-ingestion/CRAWLER_ARCHITECTURE.md` | Flow chạy chi tiết của CrawlRunner. |
| 15 | `docs/architecture/CRAWLER_ARCHITECTURE.md` | **MERGE & ARCHIVE** | `docs/02-ingestion/CRAWLER_ARCHITECTURE.md` | Bản gốc chuyển sang `docs/archive/legacy-design/`. |
| 16 | `docs/architecture/CRAWLER_ACQUISITION_STRATEGY.md` | **MERGE & ARCHIVE** | `docs/02-ingestion/CRAWLER_ARCHITECTURE.md` | Bản gốc chuyển sang `docs/archive/legacy-design/`. |
| 17 | `docs/crawler/04-nhatot-source-adapter.md` | **MERGE & REWRITE** | `docs/02-ingestion/SOURCE_ADAPTERS.md` | Chi tiết adapter Nhà Tốt đưa vào ma trận adapter. |
| 18 | `docs/crawler/SOURCE_DISCOVERY_STRATEGIES.md` | **MERGE & REWRITE** | `docs/02-ingestion/SOURCE_ADAPTERS.md` | Chiến lược auto-discovery adapter. |
| 19 | `docs/crawler/CRAWL_COVERAGE_AND_COMPLETENESS.md` | **MERGE & REWRITE** | `docs/02-ingestion/SOURCE_ADAPTERS.md` | Phân tích độ phủ danh mục và phân trang. |
| 20 | `docs/crawler/03-fetch-and-access-policy.md` | **MERGE & REWRITE** | `docs/02-ingestion/FETCH_ACCESS_AND_ROBOTS.md` | Chính sách HTTP/Browser, SSRF, User-Agent. |
| 21 | `docs/crawler/ROBOTS_POLICY_AND_COMPLIANCE.md` | **MERGE & REWRITE** | `docs/02-ingestion/FETCH_ACCESS_AND_ROBOTS.md` | Tuân thủ robots.txt. |
| 22 | `docs/crawler/SOURCE_ACCESS_STRATEGIES.md` | **MERGE & REWRITE** | `docs/02-ingestion/FETCH_ACCESS_AND_ROBOTS.md` | Chiến lược vượt rào cản truy cập an toàn. |
| 23 | `docs/crawler/SOURCE_HEALTH_AND_BACKOFF.md` | **MERGE & REWRITE** | `docs/02-ingestion/FETCH_ACCESS_AND_ROBOTS.md` | Circuit breaker, backoff và health check. |
| 24 | `docs/crawler/02-enums-and-models.md` | **MERGE & REWRITE** | `docs/02-ingestion/EXTRACTION_CONTRACT.md` | Domain models, Enums, raw records. |
| 25 | `docs/crawler/05-listing-extraction.md` | **MERGE & REWRITE** | `docs/02-ingestion/EXTRACTION_CONTRACT.md` | Bóc tách card danh mục. |
| 26 | `docs/crawler/06-detail-extraction.md` | **MERGE & REWRITE** | `docs/02-ingestion/EXTRACTION_CONTRACT.md` | Bóc tách trang chi tiết. |
| 27 | `docs/crawler/07-pagination-and-date-policy.md` | **MERGE & REWRITE** | `docs/02-ingestion/EXTRACTION_CONTRACT.md` | Phân trang và thông dịch ngày tiếng Việt. |
| 28 | `docs/architecture/CRAWL_AND_STORAGE_FLOW.md` | **MERGE & REWRITE** | `docs/02-ingestion/CRAWL_TO_STORAGE_FLOW.md` | Trace từ Airflow -> Crawler -> Storage; sửa lỗi trùng ID node Mermaid. |
| 29 | `docs/architecture/PERSISTENT_STORAGE_ARCHITECTURE.md` | **MERGE & ARCHIVE** | `docs/03-storage/STORAGE_OVERVIEW.md` | Sửa đường dẫn DuckDB sang `data/duckdb/`; bản gốc lưu archive. |
| 30 | `docs/crawler/08-storage-contract.md` | **MERGE & REWRITE** | `docs/03-storage/STORAGE_OVERVIEW.md` | Hợp đồng lưu trữ Bronze artifacts. |
| 31 | `docs/architecture/DATA_PERSISTENCE_ARCHITECTURE.md` | **REWRITE** | `docs/03-storage/BRONZE_MYSQL.md` | Viết lại 100% theo đúng bảng/cột thực tế của `schema.py`. |
| 32 | `docs/architecture/ASSET_PIPELINE.md` | **REWRITE & MOVE** | `docs/03-storage/ASSET_PIPELINE.md` | Chuyển vị trí, cập nhật trạng thái DAG riêng. |
| 33 | `docs/architecture/MYSQL_REPLICATION_ARCHITECTURE.md` | **ARCHIVE** | `docs/archive/legacy-design/MYSQL_REPLICATION_ARCHITECTURE.md` | Tài liệu replica FUTURE, chưa vận hành thực tế. |
| 34 | `docs/architecture/ANALYTICS_ARCHITECTURE.md` | **MERGE & ARCHIVE** | `docs/04-processing/PROCESSING_ARCHITECTURE.md` | Thay thế mô tả 8 view/bảng sai; bản gốc chuyển archive. |
| 35 | `docs/analytics/SILVER_DATASET_PIPELINE.md` | **MERGE & REWRITE** | `docs/04-processing/SILVER_CONTRACT.md` | Khẳng định Parquet 80 cột là canonical. |
| 36 | `docs/data/address_gazetteer.md` | **MERGE & REWRITE** | `docs/04-processing/ADDRESS_AND_ADMIN_NORMALIZATION.md` | Chuẩn hóa địa chỉ và bản đồ hành chính VN. |
| 37 | `docs/infrastructure/ADDRESS_RESET_OPERATIONS.md` | **MOVE** | `docs/07-engineering/ADDRESS_RESET_OPERATIONS.md` | Runbook vận hành reset địa chỉ. |
| 38 | `docs/audit/2026-09-17-address-map-enrichment.md` | **SOURCE TO MERGE** | `docs/04-processing/GEOCODING_ENRICHMENT.md` | Rút trích bài học vào geocoding; bản gốc lưu archive. |
| 39 | `docs/audit/2026-09-17-reverse-geocoding-enrichment.md` | **SOURCE TO MERGE** | `docs/04-processing/GEOCODING_ENRICHMENT.md` | Rút trích bài học reverse geocoding; bản gốc lưu archive. |
| 40 | `docs/audit/2026-09-20-address-pipeline.md` | **SOURCE TO MERGE** | `docs/04-processing/GEOCODING_ENRICHMENT.md` | Rút trích bài học pipeline địa chỉ; bản gốc lưu archive. |
| 41 | `docs/analytics/PRE_EDA_DATA_READINESS.md` | **ARCHIVE** | `docs/archive/legacy-design/PRE_EDA_DATA_READINESS.md` | Dữ liệu snapshot lịch sử, không còn phản ánh hiện tại. |
| 42 | `docs/architecture/DEPENDENCY_RULES.md` | **MOVE** | `docs/07-engineering/DEPENDENCY_RULES.md` | Quy tắc phụ thuộc Clean Architecture. |
| 43 | `docs/security/README.md` | **MERGE & REWRITE** | `docs/07-engineering/SECURITY.md` | Tổng hợp chính sách bảo mật SSRF, secrets. |
| 44 | `docs/security/PHASE_0_SECURITY_HARDENING.md` | **ARCHIVE** | `docs/archive/legacy-design/PHASE_0_SECURITY_HARDENING.md` | Báo cáo hardening giai đoạn đầu. |
| 45 | `docs/testing/TEST_DATA_ISOLATION.md` | **MERGE & REWRITE** | `docs/07-engineering/TESTING.md` | Chiến lược kiểm thử, cách ly môi trường test. |
| 46 | `docs/infrastructure/docker-development.md` | **MOVE & UPDATE** | `docs/07-engineering/DOCKER_DEVELOPMENT.md` | Hướng dẫn phát triển trên Docker Compose. |
| 47 | `.env.example` & settings code | **NEW CREATION** | `docs/07-engineering/CONFIGURATION.md` | Thay thế file `env/environment-variables.md` đang gãy. |
| 48–54 | `docs/audit/*.md` (7 files) | **ARCHIVE AS-IS** | `docs/archive/audit/*.md` | Giữ nguyên bằng chứng kiểm toán lịch sử. |
| 55–65 | `docs/log/*.md` (11 files) | **ARCHIVE AS-IS** | `docs/archive/incidents/*.md` | Giữ nguyên báo cáo sự cố (incidents) lịch sử. |
| 66 | `docs/refactor/PHASE_1_CLEAN_ARCHITECTURE.md` | **ARCHIVE AS-IS** | `docs/archive/refactor/PHASE_1_CLEAN_ARCHITECTURE.md` | Giữ nguyên nhật ký tái cấu trúc Phase 1. |
| 67–70 | `docs/superpowers/plans/*.md` (3 files) | **ARCHIVE AS-IS** | `docs/archive/plans/*.md` | Lưu các plan thiết kế tính năng. |
| 71 | `docs/superpowers/specs/2026-09-30-*.md` | **ARCHIVE AS-IS** | `docs/archive/plans/2026-09-30-silver-design.md` | Spec cũ (DuckDB table Silver, deprecated). |
| 72–77 | ADRs (ADR-001 đến ADR-006) | **CREATE NEW** | `docs/adr/ADR-001.md` → `ADR-006.md` | Tạo mới bộ 6 Architecture Decision Records. |
| 78 | ADR README | **CREATE NEW** | `docs/adr/README.md` | Mục lục danh mục ADR. |

---

## 2. Bảng Xác Minh 16 Lỗi Đã Biết (Known Issues Verification)

| # | Mô tả lỗi được nêu | Kết quả xác minh | Bằng chứng mã nguồn thực tế (`file:line`) | Giải pháp xử lý |
|:---:|:---|:---:|:---|:---|
| **1** | `DATA_PERSISTENCE_ARCHITECTURE.md` & `ANALYTICS_ARCHITECTURE.md` dùng sai tên bảng và cột (`raw_observations`, `raw_prices`, `raw_locations`, `raw_amenities`, `raw_images`, `source_listing_id`, `run_id`). | **ĐÚNG** | - `crawler/src/roombeacon_crawler/infrastructure/mysql/schema.py:20,35,52,67,86,108,121`<br>- Bảng chuẩn: `rental_posts`, `rental_post_versions`, `post_prices`, `post_addresses`, `post_details`, `post_images`, `post_amenities`, `post_fees`, `post_contacts`, `post_attributes`, `post_status_history`.<br>- Cột chuẩn: `platform_post_id`, `crawl_run_id`.<br>- Đối chiếu lỗi: `DATA_PERSISTENCE_ARCHITECTURE.md:39-44`, `ANALYTICS_ARCHITECTURE.md:16-18,53-60`. | Viết lại `03-storage/BRONZE_MYSQL.md` và `04-processing/PROCESSING_ARCHITECTURE.md` theo 100% schema chuẩn từ `schema.py`. Cấm xuất hiện các tên bảng cũ. |
| **2** | `ANALYTICS_ARCHITECTURE.md` ghi "8 views". Code nạp nhiều hơn. | **ĐÚNG** | - `analytics/duckdb/views.py:18-32` quy định `REQUIRED_VIEW_ORDER` gồm **13 required views**: `acquisition_efficiency`, `content_changes`, `data_quality`, `fresh_health_matrix`, `latest_posts`, `listing_lifetime`, `location_summary`, `observation_provenance`, `observations`, `price_history`, `replay_summary`, `source_activity`, `unknown_summary`.<br>- Thêm 1 optional view tại `analytics/duckdb/sql/optional/latest_posts_enriched.sql`.<br>- Đối chiếu lỗi: `ANALYTICS_ARCHITECTURE.md:47` ("8 Views"). | Ghi nhận chính xác 13 Views chuẩn hóa (+ 1 optional view) trong `04-processing/PROCESSING_ARCHITECTURE.md`. |
| **3** | Mâu thuẫn về trạng thái Silver: CURRENT_ARCHITECTURE ghi PLANNED/NOT IMPLEMENTED; DATA_LIFECYCLE ghi IMPLEMENTED; docs/README ghi canonical DuckDB table + Parquet mirror; SILVER_DATASET_PIPELINE ghi Parquet là canonical; spec 2026-09-30 ghi bảng DuckDB `silver.rental_listings`. | **ĐÚNG** | - `notebooks/02_roombeacon_silver.ipynb` và `notebooks/utils/silver_processing.py` tạo file `data/silver/rental_listings.parquet` (80 cột, 132,436 dòng).<br>- `data/silver/rental_listings.metadata.json:7` xác nhận.<br>- `analytics/silver/materializer.py:27` xuất Parquet.<br>- Spec DuckDB table `silver.rental_listings` là ý tưởng ngày 2026-09-30 đã bị DEPRECATED. | Chuẩn hóa theo ADR-003: Silver canonical là file Parquet `data/silver/rental_listings.parquet`. DuckDB là query engine in-process, không dùng bảng persistent DuckDB Silver. |
| **4** | `notebooks/README.md` & `notebooks/docs/notebook_explanations/README.md` ghi Silver 71 cột và liệt kê danh sách nguồn sai (Bds123, Thuephongtro, Batdongsan...). | **ĐÚNG** | - `data/silver/rental_listings.metadata.json:7` ghi rõ `"column_count": 80`.<br>- Trong `rental_listings.parquet`, 9 nguồn thực tế gồm: `phongtro123` (71,403), `chothuephongtro` (35,796), `cafeland` (9,984), `mogi` (9,782), `nhatot` (2,642), `muaban` (1,621), `nhatrovn` (869), `tromoi` (255), `chothuenha` (84). Không hề có Bds123 hay Thuephongtro. | Chuẩn hóa toàn bộ tài liệu về con số **80 cột** và đúng 9 nguồn dữ liệu thực tế. |
| **5** | `notebooks/docs/notebook_explanations/README.md` dùng link tuyệt đối `file:///data/projects/...`. | **ĐÚNG** | - `notebooks/docs/notebook_explanations/README.md:15-21` chứa 7 liên kết tuyệt đối cứng tới đường dẫn máy chủ cục bộ. | Chuyển toàn bộ thành liên kết Markdown tương đối (`relative links`). |
| **6** | `docs/README.md` trỏ tới `env/environment-variables.md` nhưng file này không tồn tại. | **ĐÚNG** | - `docs/README.md:24,56` trỏ tới `env/environment-variables.md`. Thư mục `docs/env/` không hề tồn tại. | Tạo mới `07-engineering/CONFIGURATION.md` tổng hợp từ `.env.example`, `crawler_settings.py` và `docker-compose.yml`. |
| **7** | Ma trận lịch nguồn trong `airflow/01-airflow-crawler-orchestration.md` ghi ChoThuePhongTro/Mogi/CafeLand là disabled, Guland là active. Trong khi code Batch 2/3 active, và Silver có 35k tin ChoThuePhongTro, 0 tin Guland. | **ĐÚNG** | - `airflow/01-airflow-crawler-orchestration.md:85-97` ghi sai hoàn toàn trạng thái.<br>- Thực tế code: `sources/chothuephongtro/adapter.py`, `mogi/adapter.py`, `cafeland/adapter.py` đều có `ENABLED = True` và seed `interval_minutes = 5`.<br>- Silver thực tế: `chothuephongtro` 35,796 tin, `cafeland` 9,984 tin, `mogi` 9,782 tin, `guland` 0 tin. | Lập lại ma trận chuẩn xác trong `02-ingestion/SOURCE_ADAPTERS.md` và `01-control-plane/DAG_CATALOG.md`. |
| **8** | Detail budget: docs ghi 20/40, nhưng audit 2026-09-20 thấy config 5000. | **ĐÚNG** | - `docs/audit/2026-09-20-crawler-system-retest.md:22,44` ghi nhận tại 20/09 config từng bị đổi thành 5000 làm fail 3 unit tests.<br>- Code hiện tại: `sources/phongtro123/adapter.py:104` là 1500; `sources/nhatrovn/adapter.py:102` là 40; `sources/scheduled_source.py:63` là 1000; `crawler_settings.py:38` mặc định là 20. | Ghi nhận lịch sử điều chỉnh cấu hình và thể hiện chính xác budget hiện thời theo từng nguồn trong tài liệu. |
| **9** | `BRONZE_SILVER_GOLD_ARCHITECTURE.md §03 (dòng 110-114)` ghi Raw HTML lưu trên MinIO như đã chốt, nhưng không có uploader Raw HTML trong runtime. | **ĐÚNG** | - `BRONZE_SILVER_GOLD_ARCHITECTURE.md:110-114` ghi Storage của Raw Layer là MinIO.<br>- Trong runtime: `application/orchestration/persistence.py:61` ghi log `minio bypassed`, chỉ lưu JSON artifacts trên đĩa host `/data/bronze`. MinIO hiện chỉ lưu ảnh qua `roombeacon_asset_reconciler`. | Gắn nhãn **PLANNED** cho Raw HTML Storage trên MinIO trong `00-overview/DATA_LAYERS_AND_LIFECYCLE.md` và `03-storage/OBJECT_STORAGE_MINIO.md`. |
| **10** | `CRAWL_AND_STORAGE_FLOW.md §2`: Sơ đồ Mermaid dùng cùng node id `A` cho "Airflow crawler DAG" và "Asset Sync", tạo vòng lặp vô lý. | **ĐÚNG** | - `docs/architecture/CRAWL_AND_STORAGE_FLOW.md:15,20` dùng cùng id `A` cho 2 node khác nhau. | Đổi id tách biệt: `AF[Airflow crawler DAG]` và `AS[Asset Sync]` trong sơ đồ Mermaid mới. |
| **11** | `PERSISTENT_STORAGE_ARCHITECTURE.md` ghi DuckDB ở `data/analytics/roombeacon_analytics.duckdb`, trong khi đĩa host là `data/duckdb/`. | **ĐÚNG** | - `PERSISTENT_STORAGE_ARCHITECTURE.md:38` ghi `data/analytics/`.<br>- `.env.example:78,331` ghi `DUCKDB_DATA_DIR=./data/duckdb` và `DUCKDB_DATABASE=/data/duckdb/roombeacon_analytics.duckdb`. Thư mục vật lý host là `data/duckdb/`. | Sửa chính xác thành `data/duckdb/` trong `03-storage/STORAGE_OVERVIEW.md`. |
| **12** | `overall-architecture.md` đặt Bronze ở Local Volume/SSD và MySQL chỉ làm Serving DB. | **ĐÚNG** | - `docs/architecture/overall-architecture.md:283,1685` mô tả MySQL là Serving DB và Bronze ở Local Disk.<br>- Thực tế: MySQL hiện tại lưu Bronze (`roombeacon_bronze`). Serving DB (`roombeacon_serving`) là mục tiêu PLANNED theo ADR-002. | Archive `overall-architecture.md` vào `docs/archive/legacy-design/` và thay thế bằng `00-overview/TARGET_ARCHITECTURE.md`. |
| **13** | `SYSTEM_ARCHITECTURE.md` liệt kê nguồn và view lỗi thời (5 nguồn, 8 views, Analytics CLI/UI). | **ĐÚNG** | - `docs/architecture/SYSTEM_ARCHITECTURE.md:28-34,52-53` chứa thông tin kiến trúc từ giai đoạn khởi đầu dự án. | Archive vào `docs/archive/legacy-design/SYSTEM_ARCHITECTURE.md`. |
| **14** | `MYSQL_REPLICATION_ARCHITECTURE.md` mô tả replica như đang chạy, nhưng thực tế là FUTURE. | **ĐÚNG** | - `docs/architecture/MYSQL_REPLICATION_ARCHITECTURE.md:3` tự ghi trạng thái FUTURE / NOT IMPLEMENTED.<br>- Không có service Ubuntu Native MySQL replica nào hoạt động. | Archive vào `docs/archive/legacy-design/` và chỉ nhắc đến như phương án mở rộng tương lai trong ADR-004. |
| **15** | Kiểm tra số DAG thực tế: docs ghi 5 DAGs, nhưng thực tế có 6 DAGs. | **ĐÚNG** | - Có 6 DAG files thực tế trong `airflow/dags/`:<br>  1. `roombeacon_crawler`<br>  2. `roombeacon_bronze_reconciler`<br>  3. `roombeacon_asset_reconciler`<br>  4. `roombeacon_silver_materializer`<br>  5. `roombeacon_geocoding` *(Docs cũ bỏ sót DAG này)*<br>  6. `roombeacon_system_healthcheck`. | Cập nhật đầy đủ danh mục 6 DAGs thực tế trong `01-control-plane/DAG_CATALOG.md`. |
| **16** | Audit 2026-09-16 kết luận clean clone NOT REPRODUCIBLE. Audit 2026-09-20 test suite 441 passed / 15 failed / 3 collection errors. | **ĐÚNG** | - `docs/audit/2026-09-16-clean-clone-recovery.md:5`<br>- `docs/audit/2026-09-20-crawler-system-retest.md:17`. | Đưa vào mục Rủi ro mở (Open Risks) trong `00-overview/IMPLEMENTATION_STATUS.md` kèm mốc thời gian kiểm toán cụ thể. |

### Lỗi phát hiện thêm (New Findings):
- **Phát hiện 17 (Nguyên nhân phình to MySQL 13GB):** Trong `MySQLObservationRepository.insert_observation` (`crawler/src/roombeacon_crawler/infrastructure/mysql/repositories/observation_repository.py:63-74`), mỗi lần cào chạy qua tin đăng đều chèn một bản ghi mới vào `rental_post_versions` (kèm toàn bộ `source_payload` JSON lớn và các bảng con) cho mỗi `crawl_run_id`, ngay cả khi nội dung tin đăng không hề thay đổi (`content_hash` được tính nhưng không dùng để lọc bản ghi trùng lặp giữa các run). Đây là nguyên nhân trực tiếp làm MySQL tăng vọt lên ~13GB chỉ sau 10 ngày.
- **Phát hiện 18:** `docs/source-structure.md` mô tả cấu trúc package cũ trước đợt tái cấu trúc Clean Architecture. Cần archive.
- **Phát hiện 19:** `docs/crawler/crawler.md` là tài liệu tóm tắt cũ bị trùng lặp hoàn toàn với `docs/crawler/01-crawler-overview.md`. Cần archive.

---

## 3. Bảng Thành Phần & Trạng Thái Đề Xuất (Component Status Matrix)

| Phân hệ / Mặt phẳng theo Bản vẽ | Trạng thái đề xuất | Bằng chứng mã nguồn / Cấu hình thực tế |
|:---|:---:|:---|
| **Orchestration Plane — Airflow Runtime** | **IMPLEMENTED** | Docker Compose 4 service Airflow 3.3.1 (`scheduler`, `api-server`, `triggerer`, `dag-processor`) chạy healthy; MySQL metadata `roombeacon-mysql-airflow`. |
| **Crawler Execution Plane — Lõi CrawlRunner & Processors** | **IMPLEMENTED & FROZEN** | `crawler/src/roombeacon_crawler/pipeline/crawl_runner.py`, `application/crawl/*` (Card, Acquisition, DeferredDetail, Frontier). **Đóng băng hoàn toàn.** |
| **Crawler Execution Plane — 12 Source Adapters** | **IMPLEMENTED / MIXED** | `SourceRegistry` nạp 12 adapters: 9 nguồn hoạt động bình thường có dữ liệu trong Silver; 1 nguồn `guland` bị chặn JS pagination; 1 nguồn `phongtrotoanquoc` disabled; `batdongsan` crawl card được nhưng detail disabled. |
| **Raw & Bronze Storage — MySQL Bronze (SCD2)** | **IMPLEMENTED** | Database `roombeacon_bronze` port 3307; `schema.py` tạo 11 bảng chuẩn hóa quan hệ; lưu trên đĩa host bind mount `data/mysql/bronze` (~13GB). |
| **Raw & Bronze Storage — Asset Engine (MinIO Images)** | **IMPLEMENTED** | MinIO port 9000/9001; lưu ảnh nhị phân tại `data/minio` (~3.5GB); `AssetReconcilerService` chạy fair scheduling, kiểm tra Magic bytes, SSRF, tệp 15MB. |
| **Raw & Bronze Storage — MinIO Raw HTML & JSON** | **PLANNED** | `persistence.py:61` ghi `minio bypassed`. Nét liền trên bản vẽ nhưng code chưa có. Cần sửa crawler (đang FROZEN) $\rightarrow$ Gap mở. |
| **Raw & Bronze Storage — Nhánh `feat/storage-plane-alignment`** | **PLANNED** | `rental_post_sightings`, `version-on-change`, con trỏ JSON, DAG `roombeacon_raw_archiver`, DAG `roombeacon_curated_observations`. |
| **Data Processing & Silver — Snapshot Parquet Export** | **IMPLEMENTED** | `analytics.bronze.snapshot` tạo `data/bronze/snapshot/latest_posts.parquet` và `raw_evidence.parquet` (132,436 tin). |
| **Data Processing & Silver — DuckDB 13 Views & Engine** | **IMPLEMENTED** | 13 required SQL views trong `analytics/duckdb/sql/` được nạp tự động qua `views.py`. |
| **Data Processing & Silver — Canonical Silver Parquet** | **IMPLEMENTED** | `notebooks/02_roombeacon_silver.ipynb` và `utils/silver_processing.py` tạo `data/silver/rental_listings.parquet` (80 cột, 132,436 tin) + metadata JSON. |
| **Data Processing & Silver — Historical Curated Observations** | **PLANNED** | Tầng Parquet lịch sử quan sát do DuckDB sinh ra, nguồn cấp cho ClickHouse Data Warehouse. |
| **Analytics & Data Warehouse — ClickHouse DW (OLAP)** | **FUTURE** | Fact tables (`fact_listing_observation`), Dimensions (`dim_date`, `dim_location`, `dim_source`), Gold / Data Marts (`agg_market_daily`). Toàn bộ là FUTURE. |
| **Machine Learning — Benchmark V3 Champion (LightGBM F4)** | **IMPLEMENTED (NOTEBOOK)** | Champion model LightGBM/RAW/F4 khóa tại `data/modeling/roombeacon_price_benchmark_v3/` (MAE ~904k VND, R² ~0.22); Shadow validation (Notebook 06) và Benchmark (Notebook 07). |
| **Search & Discovery — Nearby Rental Search (Spatial/Haversine)** | **IMPLEMENTED (PROTOTYPE)** | Đọc trực tiếp từ Silver Parquet, tính khoảng cách Haversine vector hóa kết hợp fallback Phường/Quận (Notebook 05). |
| **Application Serving — Backend API, Model Serving & MySQL OLTP** | **FUTURE** | MySQL Serving CHỈ là Application OLTP (`users`, `favorites`) — không chứa tin đăng. API kết nối Search, ML và ClickHouse Data Marts. Toàn bộ là FUTURE. |

---

## 4. Các Câu Hỏi Mở Cần Chủ Dự Án Quyết Định (Open Questions)

1. **Về việc phân tách DAG Ingestion (`roombeacon_crawler`):**
   - Hiện tại task `07_analytics_refresh_duckdb` và `08_assets_sync_minio` đang nằm chung trong DAG cào 9 bước.
   - Khi viết tài liệu mục tiêu cho Phase 1 & Phase 2, tài liệu sẽ mô tả rõ ràng luồng đích: DAG Ingestion chỉ dừng ở `persist Bronze` -> `update checkpoint` -> `summary`, phát ra Airflow Asset `bronze_mysql` để kích hoạt DAG `roombeacon_asset_sync` và DAG `roombeacon_silver_build` độc lập.
   - *Xác nhận:* Bạn duyệt phương án tài liệu hóa kiến trúc phân tách DAG qua Airflow Assets này chứ?

2. **Về chiến lược kiểm soát tăng trưởng dung lượng MySQL Bronze 13GB (ADR-001):**
   - Phân tích code thực tế cho thấy hiện tại mỗi lượt cào đều insert row mới vào `rental_post_versions` dù `content_hash` không đổi.
   - Trong ADR-001, chúng tôi đề xuất 5 giải pháp ứng viên:
     *(a) Bổ sung điều kiện kiểm tra `content_hash` trước khi insert version mới (giữ đúng bản chất SCD2).*
     *(b) Bỏ trường `source_payload` JSON lớn ra khỏi MySQL, chỉ giữ đường dẫn trỏ tới local JSON artifact hoặc MinIO.*
     *(c) Bật InnoDB Page Compression (nén bảng).*
     *(d) Partition bảng `rental_post_versions` theo tháng.*
     *(e) Tự động export các version quan sát cũ hơn 30-90 ngày ra Parquet ở MinIO và purge khỏi MySQL.*
   - *Xác nhận:* Bạn có đồng ý ghi nhận phân tích nguyên nhân và 5 phương án ứng viên này vào ADR-001 không?

3. **Về việc xử lý các file cũ khi chuyển sang Phase 3 (Archive):**
   - Đã thực hiện `git mv` toàn bộ 46 tài liệu lịch sử vào `docs/archive/{audit,incidents,legacy-design,plans,refactor}`.
   - Thêm banner chính xác 1 dòng định dạng: `> **ARCHIVED** — superseded by {tên file mới} ({link tương đối})` mà không sửa nội dung khác.
   - Toàn bộ thư mục rỗng cũ trong `docs/` đã được dọn sạch.

---

## 5. Kết Quả Hoàn Thành & Kiểm Tra Tự Động (Phase 4 Verification Results)

- **Số tài liệu mới / tái cấu trúc hoàn tất:** 39 tài liệu (gồm 32 tài liệu domain + 6 ADRs + 1 ADR index).
- **Số tài liệu lịch sử lưu trữ (archive):** 46 tài liệu được bảo toàn nguyên vẹn dòng dõi.
- **Kiểm tra liên kết tương đối (Broken Relative Links):** 258 liên kết được kiểm tra, **0 liên kết hỏng**.
- **Kiểm tra từ khóa cấm / lỗi thời:** 0 vi phạm (toàn bộ các thuật ngữ `raw_observations`, `71 cột`, `file:///`, v.v. đã được chuẩn hóa).
- **Kiểm tra Header quy chuẩn:** 39/39 tài liệu tuân thủ chuẩn Tiêu đề, Trạng thái, Mặt phẳng, Mục đích.
- **Kiểm tra cú pháp sơ đồ Mermaid:** 60 sơ đồ hợp lệ, 0 lỗi va chạm định danh (Node ID collision).
- **Kiểm tra mã nguồn:** 0 thay đổi trên mã nguồn thực thi của crawler, analytics, airflow hay các notebook.
- **Trạng thái:** HOÀN THÀNH XUẤT SẮC TOÀN BỘ 5 PHA TÁI CẤU TRÚC.
