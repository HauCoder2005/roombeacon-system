# Quy Trình Vận Hành Đặt Lại & Phục Hồi Dữ Liệu (Reset and Restore Operations)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [../04-processing/ADDRESS_AND_ADMIN_NORMALIZATION.md](../04-processing/ADDRESS_AND_ADMIN_NORMALIZATION.md), [DOCKER_DEVELOPMENT.md](DOCKER_DEVELOPMENT.md)

---

## 1. Công Cụ & Môi Trường Thực Thi

- **Script nghiệp vụ:** `scripts/reset_roombeacon_data.py`
- **Script bao bọc (Host Wrapper):** `scripts/run_reset_roombeacon.sh`

> **Nguyên tắc an toàn:** Quá trình Reset bắt buộc chạy **bên trong container `roombeacon-airflow-scheduler`** để tái sử dụng đúng cấu hình runtime và mạng Docker nội bộ. Người vận hành không truyền mật khẩu cơ sở dữ liệu trên dòng lệnh.

---

## 2. Các Chế Độ Vận Hành (Operational Modes)

1. **`--dry-run`:**
   - Kiểm tra cấu hình runtime, kiểm tra quyền ghi của database `roombeacon_bronze`.
   - Không thực hiện sao lưu, không tạm dừng DAG, không sửa đổi dữ liệu và không xóa tệp tin.
2. **`--backup-only`:**
   - Tạo bản sao lưu logic MySQL (`mysqldump`) + sao lưu trạng thái crawler trong `/data/state`.
   - Xác thực mã kiểm tra `checksum` của bản backup; không dừng DAG và không xóa dữ liệu.
3. **`--confirm-reset-roombeacon`:**
   - Thực thi sao lưu có kiểm định $\rightarrow$ Tạm dừng các writers đang chạy $\rightarrow$ Làm sạch các bảng nghiệp vụ Bronze $\rightarrow$ Xóa trạng thái filesystem của crawler $\rightarrow$ Xác nhận số dòng về 0.
4. **`--trigger-recrawl`:**
   - Chỉ dùng kèm `--confirm-reset-roombeacon`: Tự động unpause và kích hoạt DAG `roombeacon_crawler` để bắt đầu cào mới từ đầu sau khi reset thành công.

---

## 3. Ranh Giới Ngoài Phạm Vi (Out of Scope)

- **MinIO Object Binaries:** Quá trình reset không xóa các tệp ảnh trong MinIO `roombeacon-assets`. Việc dọn dẹp ảnh mồ côi thuộc về quy trình bảo trì riêng.
- **Airflow Metadata:** Không can thiệp vào database `airflow` (các log lịch sử DAG run được bảo toàn).
