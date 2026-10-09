# Runbook: Luồng Post-Silver → Data Warehouse (ClickHouse)

> **Plane:** Processing · Analytics & Data Warehouse · Orchestration
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED trong mã nguồn; ClickHouse **tắt mặc định** (profile `warehouse`)
> **Kiểm chứng lần cuối:** 2026-10-07, nhánh `feat/post-silver-platform`
> **Liên quan:** [`architecture/overall-architecture.pdf`](../../architecture/overall-architecture.pdf), [ADR-003](../adr/ADR-003.md), [ADR-004](../adr/ADR-004.md)

---

## 1. Luồng dữ liệu (theo bản vẽ)

```text
MySQL Bronze ──(roombeacon_bronze_snapshot, 01:30 UTC, bounded read-only)──► data/bronze/snapshot/
   │   latest_posts.parquet · raw_evidence.parquet · observations.parquet · metadata.json(watermark)
   └─ Asset: bronze_snapshot   (bỏ qua — không phát Asset — nếu watermark không đổi)
                    ▼
roombeacon_silver_build ── build_silver() ──► data/silver/rental_listings.parquet (+ metadata, output_sha256)
   └─ Asset: silver_rental_listings
                    ▼
roombeacon_curated_observations ──► data/curated_observations/observed_date=YYYY-MM-DD/part_0.parquet (+ _metadata.json)
   └─ Asset: curated_listing_observations
                    ▼
roombeacon_warehouse_load ──► ClickHouse `roombeacon_dw`
   dim_date · dim_source · dim_location · fact_listing_observation · fact_listing_snapshot · agg_market_daily · etl_load_log
   └─ Asset: clickhouse_gold_marts
```

Quy tắc bất biến:

- **Chỉ** `roombeacon_bronze_snapshot` được đọc MySQL Bronze. Mọi bước sau chỉ đọc Parquet.
- Silver **chỉ** được publish bởi `roombeacon_silver_build`. Notebook 02 chỉ đọc và kiểm tra hash so với bản đã publish.
- Mỗi tầng kiểm tra `snapshot_id` và `sha256` của tầng trước; lệch là **fail closed** và giữ nguyên output cũ.
- Mọi lần publish đều atomic: ghi tạm → đọc lại kiểm tra → đổi tên. Lỗi thì khôi phục bản trước.

## 2. DAG

| DAG | Lịch | Đầu vào | Đầu ra | Giới hạn |
|---|---|---|---|---|
| `roombeacon_bronze_snapshot` | `30 1 * * *` | MySQL Bronze (READ ONLY, `MAX_EXECUTION_TIME` 240s, read_timeout 300s) | Asset `bronze_snapshot` | 45 phút/task, pool `duckdb_analytics_pool` |
| `roombeacon_silver_build` | Asset `bronze_snapshot` | snapshot Parquet | Asset `silver_rental_listings` | 75 phút/task |
| `roombeacon_curated_observations` | Asset `silver_rental_listings` | snapshot `observations.parquet` + Silver | Asset `curated_listing_observations` | 45 phút/task; DuckDB 256MB/1 thread, spill ra volume |
| `roombeacon_warehouse_load` | Asset `curated_listing_observations` | curated + Silver | Asset `clickhouse_gold_marts` | Skip nếu `WAREHOUSE_ENABLED` ≠ true |

DAG cũ `roombeacon_silver_materializer` (DuckDB `ATTACH` MySQL, từng bị OOM) **đã bị xoá**.

Đo RAM đỉnh (RSS) trên dữ liệu thật 132,436 tin, với lịch sử tổng hợp ~400k và ~1.2M observations: curated ≈ 370 MB / 420 MB; model + load ≈ 470 MB ở 1.2M. Scheduler hiện giới hạn `mem_limit: 768m`.

## 3. Cấu hình — chỉ `.env.local`

```bash
cp .env.local.example .env.local && chmod 600 .env.local   # rồi điền các *_PASSWORD
```

| Biến | Dùng bởi | Ghi chú |
|---|---|---|
| `BRONZE_MYSQL_HOST_ACCESS_HOST`, `BRONZE_MYSQL_HOST_PORT` | snapshot chạy trên host | Trong Docker vẫn dùng cấu hình Bronze sẵn có của scheduler |
| `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DB` | container ClickHouse (bootstrap admin) | Container từ chối khởi động nếu thiếu password |
| `WAREHOUSE_ENABLED` | DAG/CLI warehouse | Mặc định `false` |
| `WAREHOUSE_CLICKHOUSE_{HOST,HOST_ACCESS_HOST,PORT,DATABASE,USER,PASSWORD,SECURE}` | loader | User loader chỉ có `SELECT, INSERT, CREATE TABLE, DROP TABLE, TRUNCATE` trên `CLICKHOUSE_DB.*` |
| `WAREHOUSE_CONNECT_TIMEOUT_SECONDS`, `WAREHOUSE_QUERY_TIMEOUT_SECONDS` | loader | Giới hạn 1–120s / 1–3600s |
| `WAREHOUSE_READER_USER`, `WAREHOUSE_READER_PASSWORD` | (tuỳ chọn) Power BI / API | Chỉ `SELECT`; profile `roombeacon_reader`: `readonly=2`, tối đa 20 triệu dòng/kết quả, 1800s/truy vấn |

Mật khẩu: 16–128 ký tự trong `[A-Za-z0-9._~+=@%^-]` (script init kiểm tra).

> Lưu ý bảo mật: scheduler nhận toàn bộ `.env.local` qua `env_file`, kể cả mật khẩu admin ClickHouse. Loader chỉ dùng biến `WAREHOUSE_*`. Muốn tách hẳn thì để mật khẩu admin ở nơi khác sau lần khởi tạo đầu tiên.

## 4. Kích hoạt lần đầu (người vận hành chạy)

1. Build lại image Airflow (cài package `roombeacon-warehouse`, pin `clickhouse-connect==0.8.18`):
   `⚠ PRODUCTION: docker compose build airflow-scheduler airflow-dag-processor airflow-api-server airflow-triggerer | image mới cần package warehouse | rollback: docker compose up -d --no-build với tag image cũ`
2. Tạo lại scheduler để nhận `env_file` và mount mới:
   `⚠ PRODUCTION: docker compose up -d airflow-scheduler airflow-dag-processor | áp dụng env_file .env.local + mount processing/warehouse src | rollback: git checkout <commit trước> -- docker-compose.yml && docker compose up -d airflow-scheduler airflow-dag-processor`
3. Chạy snapshot ngay (không đợi 01:30), phần còn lại sẽ tự chạy theo Asset:
   `⚠ PRODUCTION: docker compose exec airflow-scheduler airflow dags trigger roombeacon_bronze_snapshot | snapshot đầu tiên có observations.parquet và watermark | rollback: không ghi MySQL; snapshot cũ còn trong data/backups nếu cần`
4. Bật ClickHouse:
   `⚠ PRODUCTION: docker compose --profile warehouse up -d clickhouse | khởi tạo roombeacon_dw và user loader | rollback: docker compose --profile warehouse stop clickhouse (volume roombeacon-clickhouse-data giữ dữ liệu; xoá hẳn: docker volume rm roombeacon-clickhouse-data)`
5. Đặt `WAREHOUSE_ENABLED=true` trong `.env.local`, tạo lại scheduler (bước 2) rồi trigger lại `roombeacon_warehouse_load`, hoặc đợi lần curated kế tiếp.

## 5. Kiểm tra

```bash
python -m roombeacon_warehouse.run --dry-run          # chỉ build model từ Parquet, không kết nối ClickHouse
python -m pytest tests/warehouse tests/processing     # gồm golden Silver 132,436 x 80
```

SQL kiểm tra trong ClickHouse (dùng user loader hoặc reader):

```sql
SELECT snapshot_id, loaded_at, table_row_counts FROM roombeacon_dw.etl_load_log ORDER BY loaded_at DESC LIMIT 5;
SELECT d.district, m.market_date, sum(m.listings_observed), median(m.median_price)
FROM roombeacon_dw.agg_market_daily m
JOIN roombeacon_dw.dim_location d ON d.location_key = m.district_location_key
GROUP BY d.district, m.market_date ORDER BY m.market_date DESC LIMIT 20;
```

## 6. Ngữ nghĩa và giới hạn đã biết

- **Market eligibility** (`is_market_eligible`): giá của observation đạt `validate_price = ACCEPTED_CLEAN` **và** trạng thái *mới nhất* của tin trên Silver có `price_model_suitability = SUPPORTED` và `listing_intent ∈ {RENT, UNKNOWN}`. Phần ngữ nghĩa (intent/suitability) theo bài đăng chứ không theo từng observation.
- `agg_market_daily` dùng **trạng thái cuối ngày** của mỗi tin. Vì vậy số liệu không bị lệch bởi việc crawler gặp lại cùng một tin nhiều lần trong ngày (5 phút/lần).
- Địa giới: dùng `province/district_text_extracted` và `ward_current` của Silver; khoảng 44.7k tin thiếu quận nằm ở `location_level = UNKNOWN`. Không có toạ độ nào được suy diễn (ADR-006).
- Silver hiện có trên đĩa (do notebook ghi ngày 05/10) **không có `output_sha256`**, nên curated sẽ từ chối nó cho tới khi `roombeacon_silver_build` publish lại.
- `EXCHANGE TABLES` atomic theo từng bảng. Nếu lỗi xảy ra giữa chuỗi exchange (hiếm), chạy lại DAG sẽ đưa mọi bảng về cùng một snapshot.
- Thay đổi schema bảng ClickHouse cần migration chủ động: loader so `system.columns` với khai báo và fail closed nếu lệch.

## 7. Power BI (tài khoản reader)

- Điền `WAREHOUSE_READER_*` **trước** lần khởi động ClickHouse đầu tiên, script init sẽ tạo user với profile `roombeacon_reader`.
- Nếu ClickHouse đã khởi tạo trước đó, tạo user hoặc gắn profile bằng tài khoản admin:
  `⚠ PRODUCTION: docker compose --profile warehouse exec clickhouse bash -c 'CLICKHOUSE_PASSWORD="$CLICKHOUSE_PASSWORD" clickhouse client --user "$CLICKHOUSE_USER" -q "ALTER USER \`$WAREHOUSE_READER_USER\` SETTINGS PROFILE '"'"'roombeacon_reader'"'"'"' | áp profile reader cho user đã có | rollback: ALTER USER ... SETTINGS NONE`
- Power BI Desktop (Windows) dùng ClickHouse ODBC driver, kết nối `127.0.0.1:8123`. Từ máy khác thì đi qua `ssh -L 8123:127.0.0.1:8123 <user>@<máy-linux>`, không mở port ra mạng.
- Nên Import các bảng mart và dim; với `fact_listing_observation` thì lọc theo ngày hoặc dùng DirectQuery.
