# Chiến Lược Kiểm Thử & Cách Ly Dữ Liệu (Testing & Test Data Isolation)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [DEPENDENCY_RULES.md](DEPENDENCY_RULES.md), [DOCKER_DEVELOPMENT.md](DOCKER_DEVELOPMENT.md)

---

## 1. Nguyên Tắc Cách Ly Dữ Liệu Kiểm Thử (Test Data Isolation)

Hệ thống tuân thủ nguyên tắc cách ly tuyệt đối: **Kiểm thử không bao giờ được phép đọc, sửa đổi hoặc xóa dữ liệu trên cơ sở dữ liệu sản xuất `roombeacon_bronze` hay tệp canonical Silver**.

### Quy chuẩn môi trường:
- **Biến môi trường bắt buộc:** Khi chạy test, biến `ROOMBEACON_ENV=test` được kích hoạt.
- **Cơ sở dữ liệu kiểm thử riêng:** Sử dụng `BRONZE_MYSQL_DATABASE=roombeacon_bronze_test`. Mọi bảng trong DB test được khởi tạo và xóa sạch sau mỗi phiên integration test.
- **Thư mục lưu trữ tạm thời:** Sử dụng thư mục tạm (`tmp_path` của pytest) cho các tệp JSON và Parquet trong quá trình chạy test.

---

## 2. Phân Cấp Bộ Kiểm Thử (Test Hierarchy)

1. **Unit Tests (`tests/unit/`):**
   - Kiểm tra độc lập các Parser, Regex, Date Interpreter, Address Parser, và các hàm toán học.
   - Chạy hoàn toàn trên bộ nhớ RAM, không yêu cầu dịch vụ mạng hay database Docker.
2. **Integration Tests (`tests/integration/`):**
   - Kiểm tra tương tác giữa các Repository và MySQL Test Database.
   - Kiểm tra kết nối DuckDB và cơ chế trích xuất snapshot.
3. **Quality Gate Tests (`notebooks/utils/silver_processing.py`):**
   - Kiểm tra các bất biến trước khi xuất bản Silver: bảo toàn số dòng, không trùng ID, tính hợp lệ của dải giá và diện tích.

---

## 3. Lệnh Chạy Kiểm Thử Chuẩn

Để chạy bộ kiểm thử an toàn trên môi trường máy chủ:

```bash
ROOMBEACON_ENV=test \
BRONZE_MYSQL_DATABASE=roombeacon_bronze_test \
./venv/bin/python -m pytest -q --tb=short
```

---

## 4. Ghi Nhận Hiện Trạng Kiểm Toán Bộ Test (Audit 2026-09-20)

Theo biên bản kiểm toán kỹ thuật ngày 20/09/2026 ([`docs/audit/2026-09-20-crawler-system-retest.md`](../archive/audit/2026-09-20-crawler-system-retest.md)):
- Kết quả ghi nhận tại thời điểm kiểm toán: **441 passed, 15 failed, 3 collection errors**.
- *Phân loại lỗi:* 7 lỗi và 3 collection errors do môi trường máy chủ host thiếu các thư viện Airflow SDK nội bộ; 3 lỗi do lệch hợp đồng cấu hình detail budget (tạm đặt 5000 khi test); 2 lỗi về quyền bucket MinIO.
- *Ghi chú vận hành:* Cần đồng bộ môi trường virtualenv của host với container và chuẩn hóa các fixture trước khi công bố bộ test đạt 100% xanh lá.
