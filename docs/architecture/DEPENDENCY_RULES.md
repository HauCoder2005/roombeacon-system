# RoomBeacon Dependency Rules & Architectural Invariants

Tài liệu này đặc tả tường minh ma trận các quy tắc phụ thuộc (**Allowed and Forbidden Imports**) giữa các tầng trong hệ thống RoomBeacon.

---

## 1. Ma Trận Cho Phép / Cấm Phụ Thuộc (Dependency Matrix)

| Tầng (Layer) | Được phép Import | TUYỆT ĐỐI CẤM Import |
| :--- | :--- | :--- |
| **`domain/`** | Python Standard Library (`dataclasses`, `datetime`, `abc`, `re`, `typing`, `enum`) | `SQLAlchemy`, `pymysql`, `duckdb`, `playwright`, `httpx`, `minio`, `airflow`, `os.getenv()`, `sources/*` |
| **`application/`** | `domain/*`, Python Standard Library | `SQLAlchemy`, `Playwright`, `DuckDB SQL`, `airflow.decorators`, Direct SQL strings |
| **`sources/`** | `domain/*`, `BeautifulSoup` / `lxml`, `re`, `json` | `SQLAlchemy`, `MySQL`, `DuckDB`, `Airflow`, Các source adapter khác |
| **`infrastructure/`** | `domain/*`, `application/ports/*`, `SQLAlchemy`, `HTTPX`, `Playwright`, `MinIO` | `airflow.dags`, `analytics/duckdb/views` |
| **`analytics/`** | `duckdb`, `pandas`, `config/*` | `crawler/pipeline/*`, `playwright`, `httpx`, Airflow DAG logic |
| **`airflow/dags/`** | `application/*`, `domain/*`, `infrastructure/*`, `airflow` | `Playwright` direct logic, Raw HTML parsing, Direct MySQL `INSERT` strings |

---

## 2. Quy Tắc Chi Tiết theo Từng Thành Phần

### 2.1. Quy tắc Tầng Domain (Domain Purity)
- Tầng Domain đại diện cho tri thức cốt lõi của RoomBeacon.
- Không chứa mã kết nối mạng, không chứa mã database, không gọi biến môi trường trực tiếp (`os.getenv()`).

### 2.2. Quy tắc Nguồn Độc Lập (Source Isolation)
- Module `sources/nhatot/` không được phép import từ `sources/phongtro123/` hay `sources/nhatrovn/`.
- Thay đổi selector hoặc logic của một website không bao giờ ảnh hưởng đến các website khác.

### 2.3. Quy tắc Ranh Giới SQL (SQL Isolation)
- **MySQL SQL**: Chỉ được phép xuất hiện tại `infrastructure/mysql/`.
- **DuckDB Analytical SQL**: Chỉ được phép xuất hiện tại `analytics/duckdb/sql/`.
- **Cấm hoàn toàn**: Viết câu lệnh SQL trong `sources/`, `CrawlRunner`, hay Airflow DAG.

### 2.4. Quy tắc Logging Tập Trung
- Mỗi tầng chỉ log ngữ cảnh mà nó sở hữu:
  - Source: Log bóc tách HTML, selectors, fallback fields.
  - Crawler Core: Log phiên cào, số trang, số bản ghi, checkpoint.
  - Persistence: Log transaction, số bản ghi đã insert/upsert.
  - Analytics: Log tạo view, nạp SQL, thời gian truy vấn.
  - Airflow: Log tổng quan task DAG.
