# RoomBeacon — Airflow-Driven Generic Crawler Orchestration

Tài liệu này mô tả kiến trúc và luồng vận hành điều phối Crawler thông qua **Apache Airflow UI** (Entry point chính thức của hệ thống).

---

## 1. Kiến trúc luồng điều phối (Orchestration Architecture)

```text
Airflow UI
    │ (User bấm "Trigger DAG w/ config" và truyền tham số `url`)
    ▼
DAG: `roombeacon_crawler`
    │
    ├── Task 1: `validate_target_url`
    │     ├── URLValidator: Kiểm tra scheme (http/https), cú pháp, chặn SSRF (localhost, private IPs, cloud metadata)
    │     └── SourceResolver: Kiểm tra tính khả dụng của Source Adapter trong SourceRegistry
    │
    └── Task 2: `execute_crawler_run`
          └── CrawlRunner.execute_crawl(...)  (Public Application Boundary)
                │
                ├── SourceRegistry.resolve(url) -> SiteAdapter (NhaTot, Phongtro123, ...)
                ├── RobotsPolicy: Đánh giá robots.txt độc lập theo domain (ROBOTS_DENIED -> Controlled Skip)
                ├── StrategySelector: Chọn HTTP Fetcher hoặc Playwright Browser Fetcher
                ├── ListingCrawlPipeline -> Site ListingParser & ListingValidator
                ├── DetailCrawlPipeline  -> Site DetailParser & DetailValidator
                └── BronzeMapper -> Output Local Bronze Dataset (`data/bronze/<source>/...`)
```

---

## 2. Các tham số Runtime (DAG Parameters)

| Tham số | Kiểu dữ liệu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `url` | `string` | `https://phongtro123.com/tinh-thanh/ho-chi-minh` | Đường dẫn danh mục cần crawl (hỗ trợ tự động các nguồn đã đăng ký như Phongtro123, NhaTot, v.v.). |
| `max_pages` | `integer` | `1` | Số trang listing tối đa cần duyệt (1 - 20). |
| `max_records` | `integer` | `20` | Số tin đăng tối đa cần trích xuất (1 - 500). |
| `crawl_details` | `boolean` | `false` | Bật/tắt việc thu thập chi tiết từng tin đăng (mặc định False cho bước kiểm chứng listing). |
| `max_details_per_run` | `integer` | `20` | Giới hạn số request detail trang con trong run. |

---

## 3. Hướng dẫn sử dụng trên Airflow UI

1. Truy cập Airflow UI tại: `http://localhost:8080` (hoặc cổng cấu hình).
2. Tìm DAG: `roombeacon_crawler`.
3. Bấm nút **Trigger DAG w/ config** (biểu tượng Play có bánh răng).
4. Nhập đường dẫn `url` mong muốn (ví dụ: `https://phongtro123.com/tinh-thanh/ho-chi-minh` hoặc `https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh`).
5. Bấm **Trigger** để bắt đầu phiên crawl.
6. Mở Task Log của task `execute_crawler_run` để theo dõi tiến trình bóc tách và thống kê kết quả.

---

## 4. Nguyên tắc thiết kế & Bảo mật

* **Độc lập kiến trúc:** Crawler Core không import Airflow. Chiều phụ thuộc chỉ đi một chiều: `Airflow DAG -> Crawler`.
* **Generic & Source-Agnostic:** URLValidator không chứa domain hardcode. Toàn bộ logic theo domain nằm trong Adapter.
* **An toàn URL:** Chặn hoàn toàn SSRF (localhost, 127.0.0.1, private IP, AWS/GCP metadata endpoints).
* **Tuân thủ Robots.txt:** `ROBOTS_DENIED` dừng an toàn và chuyển trạng thái Airflow thành `SKIPPED`, tuyệt đối không bypass.
* **Bảo vệ Secret:** Toàn bộ log của Airflow task không in credentials hay access keys.
* **CLI vai trò:** CLI (`python -m roombeacon_crawler.main`) chỉ phục vụ chẩn đoán (`--diagnostics`), debug và smoke test cục bộ.
