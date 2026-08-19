# RoomBeacon — Docker Development Environment

Tài liệu này hướng dẫn cách khởi chạy, kiểm tra và quản lý môi trường phát triển (Development Stack) của dự án **RoomBeacon**.

---

## 1. Kiến trúc Stack Development

```text
Docker Compose
│
├── DATA STORAGE & OBJECT STORAGE
│   ├── mysql-bronze        (Port 127.0.0.1:3307 -> 3306) | roombeacon-data-net
│   ├── mysql-airflow       (Port 127.0.0.1:3308 -> 3306) | roombeacon-orchestration-net
│   └── minio               (Port 127.0.0.1:9000 & 9001)  | roombeacon-data-net
│
├── INITIALIZATION (One-shot)
│   ├── minio-bootstrap     (Khởi tạo 4 buckets: raw, assets, quarantine, exports)
│   └── airflow-init        (Khởi tạo và migrate metadata database trên mysql-airflow)
│
├── ORCHESTRATION (Apache Airflow 3.x)
│   ├── airflow-api-server  (Port 127.0.0.1:8080 -> 8080) | roombeacon-orchestration-net
│   ├── airflow-scheduler   (Điều phối tác vụ DAG)
│   ├── airflow-dag-processor (Phân tích cú pháp DAG files)
│   └── airflow-triggerer   (Xử lý asynchronous triggers)
│
└── PROCESSING RUNTIME
    └── processing          (Python + DuckDB 1.5.5 runtime) | roombeacon-data-net
```

---

## 2. Danh sách Services, Ports & Networks

| Service | Container Name | Host Port | Internal Port | Network | Volume Mount |
|---|---|---|---|---|---|
| `mysql-bronze` | `roombeacon-mysql-bronze` | `127.0.0.1:3307` | `3306` | `roombeacon-data-net` | `roombeacon-mysql-bronze-data` |
| `mysql-airflow` | `roombeacon-mysql-airflow` | `127.0.0.1:3308` | `3306` | `roombeacon-orchestration-net` | `roombeacon-mysql-airflow-data` |
| `minio` | `roombeacon-minio` | `127.0.0.1:9000`<br>`127.0.0.1:9001` | `9000`<br>`9001` | `roombeacon-data-net` | `roombeacon-minio-data` |
| `minio-bootstrap` | `roombeacon-minio-bootstrap` | — | — | `roombeacon-data-net` | — (one-shot exit 0) |
| `airflow-init` | `roombeacon-airflow-init` | — | — | `roombeacon-orchestration-net` | `airflow/` bindings |
| `airflow-api-server` | `roombeacon-airflow-api-server` | `127.0.0.1:8080` | `8080` | `roombeacon-orchestration-net` | `airflow/` bindings |
| `airflow-scheduler` | `roombeacon-airflow-scheduler` | — | — | `roombeacon-orchestration-net` | `airflow/` bindings |
| `airflow-dag-processor`| `roombeacon-airflow-dag-processor`| — | — | `roombeacon-orchestration-net` | `airflow/` bindings |
| `airflow-triggerer` | `roombeacon-airflow-triggerer` | — | — | `roombeacon-orchestration-net` | `airflow/` bindings |
| `processing` | `roombeacon-processing` | — | — | `roombeacon-data-net` | `./data:/data` |

---

## 3. Lệnh vận hành chính (Operational Commands)

### 3.1 Kiểm tra cấu hình và Build Images

```bash
# 1. Kiểm tra cú pháp Compose và biến môi trường
docker compose --env-file .env config

# 2. Build custom images (Airflow + MySQL provider, Processing + DuckDB)
docker compose --env-file .env build
```

### 3.2 Khởi chạy Storage Layer (MySQL + MinIO)

```bash
# Khởi chạy các dịch vụ lưu trữ dữ liệu
docker compose --env-file .env up -d mysql-bronze mysql-airflow minio minio-bootstrap

# Kiểm tra trạng thái healthcheck
docker compose --env-file .env ps
```

### 3.3 Khởi chạy toàn bộ Stack (bao gồm Airflow)

```bash
# Khởi động toàn bộ dịch vụ
docker compose --env-file .env up -d

# Theo dõi logs của một dịch vụ cụ thể
docker compose --env-file .env logs -f airflow-api-server
docker compose --env-file .env logs -f airflow-scheduler
```

### 3.4 Tạm dừng Stack (Bảo toàn dữ liệu)

```bash
# Dừng các containers mà KHÔNG xóa volumes
docker compose --env-file .env stop
```

> [!CAUTION]
> **Tuyệt đối không chạy `docker compose down -v`** trong quá trình development vì lệnh này sẽ xóa toàn bộ dữ liệu trong Named Volumes (`roombeacon-mysql-bronze-data`, `roombeacon-mysql-airflow-data`, `roombeacon-minio-data`).

---

## 4. Kiểm thử chức năng từng thành phần (Functional Testing)

### 4.1 Kiểm tra MySQL Bronze
```bash
docker compose --env-file .env exec mysql-bronze mysql -u roombeacon_crawler -pCHANGE_ME_BRONZE_CRAWLER_PASSWORD -e "SELECT 1; SHOW DATABASES;"
```

### 4.2 Kiểm tra MySQL Airflow Metadata
```bash
docker compose --env-file .env exec mysql-airflow mysql -u airflow -pCHANGE_ME_AIRFLOW_MYSQL_PASSWORD -e "SELECT 1; SHOW DATABASES;"
```

### 4.3 Kiểm tra MinIO Buckets
```bash
docker compose --env-file .env exec minio-bootstrap mc ls myminio/
```

### 4.4 Kiểm tra Processing Runtime + DuckDB
```bash
docker compose --env-file .env run --rm processing python -c "import duckdb; print('DuckDB query test:', duckdb.sql('SELECT 1 as test').fetchone())"
```

---

## 5. Giới hạn bảo mật ở môi trường Development (Known Limitations)

1. **Credentials:** Lấy trực tiếp từ file `.env` qua biến môi trường thông thường (chưa tích hợp Docker Secrets / Vault / KMS).
2. **Localhost Binding:** Các cổng dịch vụ được giới hạn bind về `127.0.0.1` để ngăn chặn truy cập công khai từ bên ngoài mạng nội bộ.
3. **Airflow Auth:** Sử dụng Simple Auth Manager cơ bản phục vụ thử nghiệm nội bộ (`admin:admin`, `viewer:viewer`).
