# Danh Mục Cấu Hình Biến Môi Trường (Runtime Configuration)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [DOCKER_DEVELOPMENT.md](DOCKER_DEVELOPMENT.md), [SECURITY.md](SECURITY.md)

---

## 1. Cơ Cấu Cấu Hình Runtime

Hệ thống quản lý cấu hình thông qua tệp `.env` tại thư mục gốc, được sao chép và điều chỉnh từ mẫu [`.env.example`](../../.env.example). 

Mã nguồn Python sử dụng thư viện Pydantic / dataclass tại [`crawler/src/roombeacon_crawler/config/get_env.py`](../../crawler/src/roombeacon_crawler/config/get_env.py) để nạp và xác thực kiểu dữ liệu của các biến môi trường một cách an toàn.

---

## 2. Danh Mục Các Biến Môi Trường Chính

### 2.1. Cấu Hình Đường Dẫn Dữ Liệu & Docker
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `ROOMBEACON_DATA_DIR` | `./data` | Thư mục gốc trên máy chủ host dùng làm bind mount cho toàn bộ dữ liệu. |
| `AIRFLOW_UID` | `1000` | User ID của Linux user chạy tiến trình Airflow trong container. |

### 2.2. MySQL #1 — RoomBeacon Bronze Database
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `BRONZE_MYSQL_CONTAINER_NAME` | `roombeacon-mysql-bronze` | Tên container Docker của MySQL Bronze. |
| `BRONZE_MYSQL_HOST` | `mysql-bronze` (nội bộ Docker) / `127.0.0.1` (host) | Tên hostname hoặc IP kết nối. |
| `BRONZE_MYSQL_PORT` | `3306` | Cổng nội bộ container. |
| `BRONZE_MYSQL_HOST_PORT` | `3307` | Cổng công khai ra ngoài host của MySQL Bronze. |
| `BRONZE_MYSQL_DATABASE` | `roombeacon_bronze` | Tên cơ sở dữ liệu lưu trữ lịch sử SCD2. |
| `BRONZE_MYSQL_USER` | `roombeacon` | Tên người dùng database. |
| `BRONZE_MYSQL_PASSWORD` | `123456789` | Mật khẩu kết nối database. |

### 2.3. MySQL #2 — Airflow Metadata Database
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `AIRFLOW_MYSQL_CONTAINER_NAME` | `roombeacon-mysql-airflow` | Tên container Docker của MySQL Airflow. |
| `AIRFLOW_MYSQL_HOST` | `mysql-airflow` | Hostname nội bộ trong Docker network. |
| `AIRFLOW_MYSQL_HOST_PORT` | `3308` | Cổng công khai ra ngoài host của MySQL Airflow. |
| `AIRFLOW_MYSQL_DATABASE` | `airflow` | Tên cơ sở dữ liệu metadata của Airflow. |

### 2.4. MinIO S3 Object Storage
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `MINIO_HOST` | `minio` / `127.0.0.1` | Endpoint kết nối dịch vụ MinIO. |
| `MINIO_PORT` | `9000` | Cổng API S3. |
| `MINIO_CONSOLE_PORT` | `9001` | Cổng Web UI quản trị MinIO. |
| `MINIO_ROOT_USER` | `roombeacon` | Tài khoản Root quản trị MinIO. |
| `MINIO_ROOT_PASSWORD` | `123456789` | Mật khẩu Root quản trị MinIO. |
| `MINIO_BUCKET_ASSETS` | `roombeacon-assets` | Tên bucket lưu trữ tệp hình ảnh. |

### 2.5. DuckDB Analytics & Processing
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `DUCKDB_DATA_DIR` | `./data/duckdb` | Thư mục lưu trữ database cục bộ trên host. |
| `DUCKDB_DATABASE` | `/data/duckdb/roombeacon_analytics.duckdb` | Đường dẫn tệp database trong container. |
| `DUCKDB_TEMP_DIRECTORY` | `/data/duckdb/tmp` | Thư mục tạm xử lý các truy vấn lớn. |
| `DUCKDB_MEMORY_LIMIT` | `4GB` | Giới hạn RAM tối đa cho DuckDB engine. |
| `DUCKDB_THREADS` | `4` | Số luồng CPU song song cho DuckDB. |

### 2.6. Cấu Hình Crawler Toàn Cục
| Biến môi trường | Giá trị mặc định mẫu | Ý nghĩa kỹ thuật |
|---|---|---|
| `CRAWLER_DEFAULT_DELAY_SECONDS` | `1.5` | Khoảng nghỉ mặc định giữa hai lượt request (giây). |
| `CRAWLER_MAX_CONCURRENCY` | `1` | Số request đồng thời tối đa trên một domain. |
| `CRAWLER_MAX_RETRIES` | `3` | Số lần thử lại tối đa khi gặp lỗi mạng tạm thời. |
| `CRAWLER_ROBOTS_CACHE_HOURS` | `24` | Thời gian lưu cache tệp `robots.txt` (giờ). |
