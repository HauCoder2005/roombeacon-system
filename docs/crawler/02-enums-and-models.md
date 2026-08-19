# 02 — Enums and Data Models

Tài liệu này mô tả chi tiết hệ thống Enum và Domain Models sử dụng trong RoomBeacon Crawler.

---

## 1. Enums (`roombeacon_crawler.enums`)

* **`CrawlStatus`**:
  * `SUCCESS`: Request thành công (HTTP 2xx).
  * `BAD_REQUEST`: HTTP 400.
  * `UNAUTHORIZED`: HTTP 401.
  * `ACCESS_DENIED`: HTTP 403 thông thường.
  * `CLOUDFLARE_CHALLENGE`: 403 hoặc 200 chứa trang thử thách bảo mật của Cloudflare.
  * `NOT_FOUND`: HTTP 404.
  * `RATE_LIMITED`: HTTP 429 Too Many Requests.
  * `SERVER_ERROR`: HTTP 5xx.
  * `TIMEOUT`: Hết thời gian chờ kết nối / phản hồi.
  * `CONNECTION_ERROR`: Lỗi mạng hoặc DNS.
  * `ROBOTS_DENIED`: Bị cấm bởi `robots.txt`.
  * `PARSE_ERROR`: Lỗi cấu trúc không thể bóc tách.
  * `UNKNOWN`: Lỗi không xác định.

* **`FetchStrategy`**:
  * `HTTP`: Sử dụng HTTPX AsyncClient.
  * `BROWSER`: Sử dụng Playwright Chromium.

* **`FetchAction`**:
  * `PARSE`: Cho phép chuyển response sang Extract Box.
  * `COOLDOWN`: Tạm dừng chờ đợi do bị rate limit.
  * `RETRY_LATER`: Thực hiện retry lại sau một khoảng thời gian backoff.
  * `STOP`: Dừng tiến trình xử lý request/nguồn này.

* **`CrawlTargetType`**:
  * `LISTING_PAGE`: Trang danh sách tin đăng.
  * `DETAIL_PAGE`: Trang chi tiết tin đăng.
  * `ASSET`: Hình ảnh hoặc tài nguyên nhúng.

* **`CrawlDateMode`**:
  * `LATEST`: Quét các tin mới nhất (giới hạn trang an toàn).
  * `DATE_RANGE`: Quét trong khoảng ngày `date_from` $\rightarrow$ `date_to`.
  * `FULL_HISTORY`: Quét toàn bộ lịch sử khả dụng.

---

## 2. Models (`roombeacon_crawler.models`)

* **`CrawlTarget`**: Đại diện một URL cần xử lý kèm metadata phát hiện (`url`, `source`, `target_type`, `page_number`, `parent_url`, `listing_id`, `discovered_at`).
* **`CapturedResponse`**: Kết quả phản hồi mạng thô (`request_url`, `final_url`, `status_code`, `html`, `headers`, `fetch_strategy`, `fetched_at`, `elapsed_ms`).
* **`CrawlMetadata`**: Audit trail kỹ thuật đầy đủ của từng request (`run_id`, `http_status`, `server`, `cf_ray`, `html_size`, `started_at`, `finished_at`, `retry_count`, `robots_allowed`, `crawl_status`).
* **`ListingCardRaw`**: Dữ liệu thô bóc tách từ card trên trang listing (`title_raw`, `price_raw`, `area_raw`, `location_raw`, `posted_at_raw`, `seller_name_raw`, `thumbnail_url_raw`, `card_position`, `page_number`).
* **`ListingDetailRaw`**: Dữ liệu thô bóc tách từ trang chi tiết (`title_raw`, `price_raw`, `area_raw`, `address_raw`, `location_raw`, `description_raw`, `posted_at_raw`, `property_type_raw`, `furnishing_raw`, `deposit_raw`, `seller_name_raw`, `image_urls_raw`, `amenities_raw`).
* **`RentalBronzeRecord`**: Bản ghi hợp nhất chuẩn hóa cho lớp Bronze Dataset (`listing_id`, `source`, `url`, các trường thô, `crawl_run_id`, `crawled_at`).
* **`CrawlRunResult`**: Thống kê kết quả toàn bộ một phiên crawl (`run_id`, `pages_success`, `pages_failed`, `details_success`, `details_failed`, `records_created`, `duplicates_skipped`, `errors`).
