# Tổng Quan Mặt Phẳng Lưu Trữ Thô và Bronze (Raw & Bronze Storage Overview)

> **Plane:** Storage
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** hỗn hợp — xem bảng
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [BRONZE_MYSQL.md](BRONZE_MYSQL.md), [OBJECT_STORAGE_MINIO.md](OBJECT_STORAGE_MINIO.md), [ASSET_PIPELINE.md](ASSET_PIPELINE.md)

---

## 1. Nguyên Tắc Đĩa Máy Chủ Làm Nguồn Chân Lý (Host Source of Truth)

Toàn bộ các container Docker trong RoomBeacon (MySQL, MinIO, Airflow) đều được cấu hình gắn kết trực tiếp với hệ thống tệp của máy chủ thông qua **Docker Bind Mounts** (cấu hình trong [`docker-compose.yml:138,255,330`](../../docker-compose.yml#L138)):

- Dữ liệu không lưu ẩn trong các Docker Named Volumes trừu tượng mà nằm minh bạch tại thư mục `${ROOMBEACON_DATA_DIR:-./data}/` trên máy chủ host.
- Cho phép quản trị viên máy chủ trực tiếp kiểm tra, sao lưu, nén hoặc di chuyển dữ liệu mà không cần thông qua các công cụ can thiệp container phức tạp.

---

## 2. Phân Bổ Thành Phần Theo Bản Vẽ Kiến Trúc

Theo bản vẽ chuẩn hóa [**`overall-architecture.pdf`**](../../architecture/overall-architecture.pdf), **Raw and Bronze Storage Plane** bao gồm hai khối lưu trữ trọng tâm:

1. **MySQL Bronze (Crawler Structured Data):** Lưu trữ toàn bộ dữ liệu quan sát có cấu trúc theo mô hình SCD2 trong cơ sở dữ liệu `roombeacon_bronze` (port 3307), đảm bảo tính toàn vẹn giao dịch (Unit of Work). Xem chi tiết tại [**BRONZE_MYSQL.md**](BRONZE_MYSQL.md).
2. **MinIO (RAW: HTML, JSON, Images):** Lưu trữ đối tượng S3-compatible:
   - **Images:** Lưu trữ hình ảnh tin đăng tại bucket `roombeacon-assets` (**IMPLEMENTED**). Xem [**OBJECT_STORAGE_MINIO.md**](OBJECT_STORAGE_MINIO.md).
   - **Raw HTML & JSON:** Lưu trữ mã HTML gốc và payload JSON thô (**PLANNED**). Hiện tại code crawler ghi nhận `minio bypassed` do đang đóng băng crawler; đây là một gap mở kỹ thuật.

---

## 3. Cây Thư Mục Dữ Liệu `data/` & Thống Kê Dung Lượng Thực Tế

Bảng thống kê dung lượng thực tế trên đĩa máy chủ (theo số liệu báo cáo của Chủ dự án ngày 2026-10-06):

| Thư mục vật lý | Dung lượng | Bản chất kỹ thuật & Phân loại lưu trữ |
|:---|---:|:---|
| [`data/mysql`](../../data/mysql) | **~13.0 GB** | **MySQL 8.4 InnoDB Tablespaces:** Gồm `mysql/bronze/` chứa các bảng lịch sử quan sát SCD2 và `mysql/airflow/` chứa metadata Airflow. |
| [`data/minio`](../../data/minio) | **~3.5 GB** | **MinIO S3 Object Storage:** Chứa hàng chục ngàn tệp nhị phân hình ảnh tin đăng tại bucket `roombeacon-assets`. |
| [`data/bronze`](../../data/bronze) | **~2.0 GB** | **Raw JSON Artifacts:** Tệp JSON ghi lại kết quả thô của từng phiên cào: `<source>/<YYYY-MM-DD>/run_<id>/listings.json`. |
| [`data/backups`](../../data/backups) | **~228 MB** | **Sao lưu Định kỳ:** Các bản xuất dump nén (`mysqldump`) của cơ sở dữ liệu. |
| [`data/manifests`](../../data/manifests) | **~83 MB** | **Nhật ký Bóc tách URL:** Ghi nhận metadata kỹ thuật chi tiết của từng lượt tải trang HTML. |
| [`data/state`](../../data/state) | **~46 MB** | **Trạng thái Bền vững:** Điểm kiểm soát (`checkpoints`), danh sách ID đã thấy (`seen_ids`), hàng đợi `deferred_details` và trạng thái `assets`. |
| [`data/silver`](../../data/silver) | **~32 MB** | **Canonical Silver Parquet:** Tệp `rental_listings.parquet` (80 cột, 132,436 tin) kèm metadata JSON. |
| [`data/modeling`](../../data/modeling) | **~25 MB** | **Artifacts Machine Learning:** Trọng số mô hình `champion_model.joblib` (Benchmark V3 LightGBM F4), kết quả validation, profile đặc trưng. |
| [`data/duckdb`](../../data/duckdb) | **~1.8 MB** | **Metadata DuckDB:** Tệp database cục bộ và thư mục tạm `tmp/` phục vụ động cơ OLAP in-memory. |

---

## 4. Kế Hoạch Đồng Bộ Lưu Trữ Trên Nhánh `feat/storage-plane-alignment` (PLANNED)

Để tối ưu hóa dung lượng lưu trữ đĩa và chuẩn bị dữ liệu đầu vào cho Data Warehouse, nhánh `feat/storage-plane-alignment` đang triển khai các giải pháp (ở trạng thái **PLANNED**):

1. **`rental_post_sightings`:** Bổ sung bảng ghi nhận số lần xuất hiện của tin đăng, loại bỏ việc nhân bản vô hạn các record version nặng.
2. **Version-on-Change:** Chỉ ghi version mới vào `rental_post_versions` khi phát hiện `content_hash` thay đổi.
3. **Con trỏ thay cho `source_payload`:** Đưa trường JSON lớn ra ngoài bảng MySQL, chỉ lưu URI con trỏ trỏ tới artifact file.
4. **DAG `roombeacon_raw_archiver`:** Đóng gói và lưu trữ nén các tệp JSON/HTML thô lên MinIO RAW có chính sách retention.
5. **DAG `roombeacon_curated_observations`:** DuckDB quét MySQL Bronze và xuất bản các tệp Parquet **Historical Curated Observations**, làm nguồn cấp cho ClickHouse Data Warehouse.
