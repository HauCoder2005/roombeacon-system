# RoomBeacon Documentation Index

> Mục đích: trả lời “tôi muốn tìm thông tin X thì đọc file nào?”.
>
> Trạng thái: **CURRENT / AUTHORITATIVE INDEX**.

Khi tài liệu mâu thuẫn, thứ tự ưu tiên là: **source code → tests → DAGs → Current Architecture → tài liệu chuyên đề**.

## Bắt đầu từ đâu?

| Tôi muốn biết… | Đọc tài liệu |
|---|---|
| Hệ thống hiện chạy như thế nào | [Current Architecture](architecture/CURRENT_ARCHITECTURE.md) |
| Trace từng bước từ Airflow, crawler tới Bronze/MySQL/MinIO | [Crawl & Storage Flow](architecture/CRAWL_AND_STORAGE_FLOW.md) |
| Bronze, latest-state, EDA, Silver, Gold khác nhau thế nào | [Data Lifecycle](data/DATA_LIFECYCLE.md) |
| Một crawl run thực thi ra sao | [Crawler Overview](crawler/01-crawler-overview.md) và [Run Flow](crawler/09-run-flow.md) |
| Airflow điều phối task nào | [Crawler Airflow Orchestration](airflow/01-airflow-crawler-orchestration.md) |
| Robots, retry, source access | [Fetch & Access Policy](crawler/03-fetch-and-access-policy.md) |
| Observation được persist thế nào | [Data Persistence](architecture/DATA_PERSISTENCE_ARCHITECTURE.md) |
| Asset image đi tới MinIO thế nào | [Asset Pipeline](architecture/ASSET_PIPELINE.md) |
| DuckDB và latest-state Parquet | [Analytics Architecture](architecture/ANALYTICS_ARCHITECTURE.md) |
| Initial Data Quality EDA hiện có | [EDA notebook](../notebooks/01_rental_eda.ipynb) và [Data Lifecycle](data/DATA_LIFECYCLE.md) |
| Chạy development stack | [Docker Development](infrastructure/docker-development.md) |
| Cấu hình runtime | [Environment Variables](env/environment-variables.md) |
| Test không chạm production data | [Test Isolation](testing/TEST_DATA_ISOLATION.md) |
| Security invariants | [Security Index](security/README.md) |
| Vì sao code có cấu trúc hiện tại | [Phase 1 Refactor](refactor/PHASE_1_CLEAN_ARCHITECTURE.md) |
| Finding lịch sử / incident | [Audit](audit/README.md) / [Incident Log](log/README.md) |

## Authoritative documents

- [Root README](../README.md): entry point và project status.
- [Current Architecture](architecture/CURRENT_ARCHITECTURE.md): runtime/components hiện tại.
- [Crawl & Storage Flow](architecture/CRAWL_AND_STORAGE_FLOW.md): code path authoritative từ trigger đến storage và analytics.
- [Data Lifecycle](data/DATA_LIFECYCLE.md): semantics data layers và hai loại EDA.
- [Dependency Rules](architecture/DEPENDENCY_RULES.md): boundary rules.

Các tài liệu khác bổ sung chi tiết, không override bốn tài liệu trên.

## Phân loại documentation

### CURRENT

- `architecture/CURRENT_ARCHITECTURE.md`, `ASSET_PIPELINE.md`, `CRAWLER_ACQUISITION_STRATEGY.md`, `DATA_PERSISTENCE_ARCHITECTURE.md`, `DEPENDENCY_RULES.md`
- `crawler/01-*` đến `crawler/09-*`, `CRAWL_COVERAGE_AND_COMPLETENESS.md`, `ROBOTS_POLICY_AND_COMPLIANCE.md`, `SOURCE_*`
- `airflow/01-airflow-crawler-orchestration.md`
- `data/DATA_LIFECYCLE.md`
- `security/*`, `testing/*`, `infrastructure/docker-development.md`

### PARTIAL / CẦN ĐỌC CÙNG SOURCE

- `architecture/ANALYTICS_ARCHITECTURE.md`: DuckDB current; terminology cũ có thể gọi latest-state output là Silver.
- `analytics/PRE_EDA_DATA_READINESS.md`: evidence tại một snapshot lịch sử, không phải live metrics.
- `analytics/SILVER_DATASET_PIPELINE.md`: mô tả current materializer nhưng output là latest-state snapshot.
- `../notebooks/01_rental_eda.ipynb`: Initial Data Quality EDA hiện có; không phải Clean Analytical EDA trên Silver.
- `env/environment-variables.md`: catalog rộng hơn active runtime; `.env.example` là cấu hình mẫu.

### HISTORICAL / INCIDENT — GIỮ NGUYÊN EVIDENCE

- `audit/*`
- `log/*`
- `refactor/*`

Các file này mô tả thời điểm cụ thể; remediation status có thể được thêm ở đầu nhưng evidence lịch sử không bị rewrite.

### FUTURE DESIGN / LEGACY, KHÔNG AUTHORITATIVE

- `architecture/overall-architecture.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/MYSQL_REPLICATION_ARCHITECTURE.md`
- `architecture/PERSISTENT_STORAGE_ARCHITECTURE.md` ở các phần chưa có runtime evidence
- `source-structure.md`
- `crawler/crawler.md`
- `crawler/08-storage-contract.md` ở phần Raw object storage

Những tài liệu này được giữ làm design context. Không dùng chúng để kết luận một component đã được triển khai.

## CURRENT và FUTURE

**IMPLEMENTED:** crawler, JSON/MySQL Bronze, reconciliation, asset MinIO path, DuckDB views, latest-state Parquet.

**PARTIAL:** Initial Data Quality EDA, repository-wide Clean Architecture composition ownership.

**PLANNED:** versioned cleaning rules, cleaned semantic Silver, clean analytical EDA.

**FUTURE / NOT IMPLEMENTED:** Gold, serving API/UI, ClickHouse runtime, MySQL replica service, active Raw HTML object uploader.
