# Hướng Dẫn Phát Triển Trên Docker Compose (Docker Development)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [CONFIGURATION.md](CONFIGURATION.md), [../01-control-plane/AIRFLOW_ARCHITECTURE.md](../01-control-plane/AIRFLOW_ARCHITECTURE.md)

---

## 1. Danh Mục Các Dịch Vụ & Cổng Kết Nối (Service & Port Catalog)

Cụm dịch vụ được định nghĩa trong [`docker-compose.yml`](../../docker-compose.yml):

| Tên Container | Hình ảnh (Image) | Cổng Host | Vai trò chức năng |
|---|---|:---:|---|
| **`roombeacon-mysql-bronze`** | `mysql:8.4` | `3307` $\rightarrow$ `3306` | Cơ sở dữ liệu Bronze lưu trữ lịch sử quan sát SCD2 (`roombeacon_bronze`). |
| **`roombeacon-mysql-airflow`** | `mysql:8.4` | `3308` $\rightarrow$ `3306` | Cơ sở dữ liệu lưu trữ metadata riêng cho Airflow (`airflow`). |
| **`roombeacon-minio`** | `bitnamilegacy/minio:latest` | `9000`, `9001` | Object Storage tương thích S3 lưu trữ tệp hình ảnh tài nguyên. |
| **`roombeacon-airflow-scheduler`** | `roombeacon-airflow-custom:3.3.1` | — | Bộ lập lịch và điều phối các DAG tasks. |
| **`roombeacon-airflow-api-server`** | `roombeacon-airflow-custom:3.3.1` | `8080` | Airflow Web UI và REST API quản trị (`http://localhost:8080`). |
| **`roombeacon-airflow-dag-processor`** | `roombeacon-airflow-custom:3.3.1` | — | Tiến trình phân tích cú pháp tệp DAG độc lập. |
| **`roombeacon-airflow-triggerer`** | `roombeacon-airflow-custom:3.3.1` | — | Quản lý các trigger sự kiện bất đồng bộ. |

---

## 2. Quy Trình Khởi Động Cho Máy Mới (Clean Setup)

1. **Chuẩn bị biến môi trường:**
   ```bash
   cp .env.example .env
   ```
2. **Cấp quyền ghi thư mục dữ liệu cho UID 1000:**
   *(Lưu ý từ kiểm toán Clean Clone 2026-09-16: Airflow chạy với UID 1000; các thư mục bind mount bắt buộc phải có quyền ghi cho người dùng này)*:
   ```bash
   mkdir -p data/mysql data/minio data/bronze data/state data/silver data/duckdb data/backups
   chmod -R 775 data/
   ```
3. **Khởi động cụm dịch vụ:**
   ```bash
   docker compose up -d
   ```
4. **Kiểm tra trạng thái sức khỏe:**
   ```bash
   docker compose ps
   ```

---

## 3. Các Lệnh Vận Hành Thường Dùng

- Xem nhật ký Airflow Scheduler:
  ```bash
  docker compose logs -f airflow-scheduler
  ```
- Kết nối vào MySQL Bronze dòng lệnh:
  ```bash
  docker exec -it roombeacon-mysql-bronze mysql -u roombeacon -p123456789 roombeacon_bronze
  ```
- Dừng toàn bộ cụm dịch vụ an toàn:
  ```bash
  docker compose down
  ```
