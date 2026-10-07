# Kiến Trúc Mặt Phẳng Xử Lý Dữ Liệu và Silver (Data Processing & Silver Architecture)

> **Plane:** Processing
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** PARTIAL
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [SILVER_CONTRACT.md](SILVER_CONTRACT.md), [ADDRESS_AND_ADMIN_NORMALIZATION.md](ADDRESS_AND_ADMIN_NORMALIZATION.md)

---

## 1. Vai Trò của DuckDB Trong Mặt Phẳng Xử Lý

Theo bản vẽ chuẩn hóa [**`overall-architecture.pdf`**](../../architecture/overall-architecture.pdf), **DuckDB (Embedded Analytical Engine)** là trung tâm tính toán của **Data Processing and Silver Plane**:

- **Zero-Copy Direct Attach:** DuckDB sử dụng MySQL Extension để kết nối chỉ đọc (`READ_ONLY`) trực tiếp vào cơ sở dữ liệu `roombeacon_bronze`.
- **Tập hợp 13 Analytical Views Bắt buộc:** Quản lý tập trung tại [`analytics/duckdb/views.py:18-32`](../../analytics/duckdb/views.py#L18-L32), phục vụ trích xuất và phân tích:
  1. `acquisition_efficiency`: Hiệu suất thu thập theo nguồn.
  2. `content_changes`: Theo dõi bài đăng có biến động tiêu đề hoặc giá.
  3. `data_quality`: Thống kê tỷ lệ đầy đủ của các trường thông tin.
  4. `fresh_health_matrix`: Ma trận độ tươi mới và sức khỏe của các nguồn.
  5. `latest_posts`: **View trung tâm**, xếp hạng các phiên quan sát và trích xuất trạng thái mới nhất của từng bài đăng (1 dòng / 1 tin).
  6. `listing_lifetime`: Phân tích tuổi thọ bài đăng (`active_days`).
  7. `location_summary`: Phân bố bài đăng và diện tích theo địa bàn.
  8. `observation_provenance`: Nguồn gốc xuất xứ và lịch sử quan sát.
  9. `observations`: Tổng hợp toàn bộ quan sát Bronze.
  10. `price_history`: Lịch sử biến động giá qua các phiên cào.
  11. `replay_summary`: Thống kê các phiên tái xử lý.
  12. `source_activity`: Tần suất thu thập của từng sàn theo ngày.
  13. `unknown_summary`: Thống kê các giá trị không xác định.
  *(Kèm 1 optional view: `latest_posts_enriched.sql`)*.

---

## 2. Quy Trình Trích Xuất Snapshot Parquet (`analytics.bronze.snapshot`)

Để bảo đảm ranh giới an toàn theo **ADR-004**, hệ thống không cho phép các pipeline phân tích kết nối trực tiếp vào MySQL Bronze. Thay vào đó, module [`analytics.bronze.snapshot`](../../analytics/bronze/snapshot.py) thực thi quy trình:

1. Kết nối ngắn hạn vào DuckDB với MySQL Attached.
2. Thực thi view `latest_posts.sql` để lấy trạng thái mới nhất của 132,436 tin đăng.
3. Xuất ra 2 tệp snapshot bất biến:
   - `data/bronze/snapshot/latest_posts.parquet`
   - `data/bronze/snapshot/raw_evidence.parquet`
   - `data/bronze/snapshot/metadata.json` (kèm mã băm SHA-256 xác thực).

---

## 3. Bảng Phân Định: Ai Sinh Ra Silver Canonical?

Trong lịch sử dự án, có sự băn khoăn về việc có hai nơi cùng sinh ra dữ liệu Silver: Notebook 02 và Airflow DAG `roombeacon_silver_materializer`.

Dưới đây là kết quả đối chiếu chính xác từ mã nguồn:

| Tiêu chí | Runner 1: `02_roombeacon_silver.ipynb` | Runner 2: DAG `roombeacon_silver_materializer` |
|---|---|---|
| **Bản chất vai trò** | **Interactive / Development Runner** (Dành cho Data Scientist kiểm thử trực quan, audit phân phối). | **Automated Scheduled Runner** (Dành cho vận hành sản xuất định kỳ lúc 2h sáng). |
| **Logic bóc tách & làm sạch** | Gọi hàm trong [`notebooks.utils.silver_processing`](../../notebooks/utils/silver_processing.py). | Gọi hàm trong [`notebooks.utils.silver_processing`](../../notebooks/utils/silver_processing.py). |
| **Cổng kiểm định chất lượng** | Gọi [`evaluate_pre_silver_quality_gate`](../../notebooks/utils/silver_processing.py#L74). | Gọi [`evaluate_pre_silver_quality_gate`](../../notebooks/utils/silver_processing.py#L74). |
| **Class xuất bản tệp** | [`SilverMaterializer`](../../analytics/silver/materializer.py#L52). | [`SilverMaterializer`](../../analytics/silver/materializer.py#L52). |
| **Tệp đích xuất bản** | `data/silver/rental_listings.parquet` | `data/silver/rental_listings.parquet` |
| **Số dòng & Số cột** | 132,436 dòng — **80 cột** | 132,436 dòng — **80 cột** |
| **Kết luận kỹ thuật** | **CẢ HAI DÙNG CHUNG 1 CODEBASE DUY NHẤT VÀ SINH RA DUY NHẤT 1 TẬP SILVER CANONICAL.** Không hề có bản mirror thứ hai hay schema khác biệt. |

---

## 4. Tầng Lịch Sử Quan Sát Đã Curate (Historical Curated Observations — PLANNED)

Theo bản vẽ thiết kế, DuckDB có đường mũi tên nét đứt kết xuất sang **Historical Curated Observations**:

- **Bản chất nghiệp vụ:** Đây là tầng dữ liệu lịch sử quan sát đã được làm sạch và chuẩn hóa (SCD2 versions + sightings) lưu dưới dạng Parquet nén phân vùng theo thời gian (`data/curated_observations/`).
- **Nguồn cấp cho Data Warehouse:** Đây là nguồn dữ liệu chuẩn hóa đầu vào để nạp vào bảng `fact_listing_observation` trong ClickHouse Data Warehouse (OLAP, FUTURE).
- **Trạng thái:** **PLANNED** (đang chuẩn bị trên nhánh `feat/storage-plane-alignment` thông qua DAG `roombeacon_curated_observations`).
