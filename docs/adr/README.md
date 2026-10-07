# Architecture Decision Records (ADR)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** hỗn hợp — xem bảng
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [ADR-001.md](ADR-001.md), [ADR-002.md](ADR-002.md), [ADR-003.md](ADR-003.md), [ADR-004.md](ADR-004.md), [ADR-005.md](ADR-005.md), [ADR-006.md](ADR-006.md)

---

## Danh mục Quyết định Kiến trúc

| Mã ADR | Tiêu đề quyết định | Trạng thái | Mặt phẳng chính |
|:---:|:---|:---:|:---|
| [**ADR-001**](ADR-001.md) | Bronze lịch sử tiếp tục lưu trong MySQL `roombeacon_bronze` (SCD2), MinIO RAW và kế hoạch kiểm soát tăng trưởng | **ACCEPTED** | Raw and Bronze Storage Plane |
| [**ADR-002**](ADR-002.md) | MySQL ở tầng Serving chỉ đóng vai trò Application OLTP (Users, Favorites) — Không chứa Listings | **ACCEPTED** | Application Serving Plane |
| [**ADR-003**](ADR-003.md) | DuckDB làm In-Memory Processing Engine và Parquet làm Persistent Canonical Silver | **ACCEPTED** | Data Processing and Silver Plane |
| [**ADR-004**](ADR-004.md) | Tách biệt OLTP / OLAP bằng Snapshot Parquet; Hoãn CDC / Kafka; ClickHouse là Data Warehouse tương lai | **ACCEPTED** | Data Processing & Analytics Plane |
| [**ADR-005**](ADR-005.md) | Phân tách DAG Airflow theo Phân vùng Nghiệp vụ (Domain) và liên kết bằng Airflow Assets | **ACCEPTED** | Orchestration Plane |
| [**ADR-006**](ADR-006.md) | Nguyên tắc Toàn vẹn Toạ độ Không gian, Không Nội suy và Cách ly Toạ độ Mẫu | **ACCEPTED** | Data Processing and Silver Plane |

---

## Cấu trúc Chuẩn của một Bản ghi ADR

Mỗi ADR trong thư mục này tuân thủ cấu trúc:
1. **Bối cảnh (Context):** Vấn đề kỹ thuật hoặc bài toán nghiệp vụ cần giải quyết.
2. **Các phương án đã cân nhắc (Considered Alternatives):** Đánh giá ưu / nhược điểm của từng lựa chọn.
3. **Quyết định (Decision):** Lựa chọn chính thức được thông qua và cơ sở lý luận.
4. **Hệ quả & Rủi ro (Consequences & Risks):** Các đánh đổi (trade-offs), rủi ro kỹ thuật và biện pháp giảm thiểu.
5. **Kế hoạch hành động (Action Plan):** Các bước triển khai cụ thể gắn với trạng thái (IMPLEMENTED / PLANNED / FUTURE).
