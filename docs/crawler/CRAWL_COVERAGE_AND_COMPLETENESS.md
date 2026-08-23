# RoomBeacon Crawl Coverage, Completeness & Acquisition Semantics

Tài liệu này đặc tả chi tiết kiến trúc đo lường độ phủ (**Crawl Coverage**), tính toàn vẹn dữ liệu lịch sử (**Completeness**) và các chế độ thu thập (**Acquisition Modes**) trong hệ thống crawler phân tán **RoomBeacon**.

---

## 1. Bản chất Kỹ thuật của Bài toán Độ phủ (Coverage Problem)

Trong một hệ thống Data Platform / Crawler cấp doanh nghiệp, một nguồn dữ liệu có thể có nhiều trạng thái độ phủ khác nhau tùy thuộc vào đặc thù hạ tầng và chính sách truy cập của website nguồn.

Hệ thống phân tách rạch ròi giữa 2 chiều không gian dữ liệu:
1. **Historical Coverage (Độ phủ Lịch sử / Backfill)**: Dữ liệu đã đăng tải trong quá khứ trước khi hệ thống bắt đầu theo dõi.
2. **Forward Acquisition Coverage (Độ phủ Chiều thuận / Real-time)**: Dữ liệu phát sinh mới từ thời điểm hệ thống bắt đầu giám sát trở đi.

$$\text{Total Market Coverage} = \text{Historical Backfill} + \int_{t_0}^{t_{\text{now}}} \text{Forward Ingest}(t) \, dt$$

---

## 2. Bảng Phân loại Độ phủ theo Nguồn (Source Coverage Matrix)

| Nguồn (Source) | Phương thức Khám phá | Chiến lược Vận chuyển | Historical Coverage | Forward Acquisition | Chế độ Thực thi Phù hợp | Trạng thái Hiện tại |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **NhaTroVN** | Query Pagination (`?page=`) | `HttpFetcher` (HTTP 200) | **COMPLETE** | **ACTIVE** | `INCREMENTAL` (Known-Region Early Stop) | `ACTIVE` |
| **PhongTro123** | Query Pagination (`?page=`) | `HttpFetcher` (HTTP 200) | **IN_PROGRESS** | **ACTIVE** | `BOOTSTRAP_CONTINUE` $\rightarrow$ `INCREMENTAL` | `ACTIVE` |
| **NhaTot** | Landing Category Seed | `BrowserFetcher` (Playwright 200) | **UNAVAILABLE** | **ACTIVE** | `FORWARD_ONLY_INCREMENTAL` | `FORWARD_ACTIVE` |
| **BatDongSan** | Landing Category Seed | `BrowserFetcher` (Playwright 200) | **UNAVAILABLE** | **ACTIVE** | `FORWARD_ONLY_INCREMENTAL` | `FORWARD_ACTIVE` |
| **Muaban** | Sitemap / Landing Seed | `HttpFetcher` / `BrowserFetcher` | **UNAVAILABLE** | **BLOCKED** | `CONTROLLED_BACKOFF` (Health Cooldown) | `ACCESS_BLOCKED` |

---

## 3. Forward-Only Acquisition: Nguyên lý & Triển khai

### 3.1. Tại sao không thể có Historical Completeness trên NhaTot?
- `robots.txt` của Nhà Tốt công khai chỉ thị `Disallow: /*page=`.
- Tiêu chuẩn RFC 9309 bắt buộc crawler phải dừng mọi ý định yêu cầu các URL có dạng `?page=2`, `?page=3`...
- Việc cố tình bypass robots hoặc giả lập trình duyệt để cào 500 trang lịch sử vi phạm tiêu chuẩn kỹ thuật và đạo đức hệ thống.
- Sitemap XML hiện bị bảo vệ bởi WAF (HTTP 403 đối với request direct sitemap).

### 3.2. Giải pháp Forward-Only của RoomBeacon
RoomBeacon định nghĩa năng lực nguồn trong `SourceCapabilities`:
```python
CAPABILITIES = SourceCapabilities(
    access_profile=SourceAccessProfile.DISCOVERY_RESTRICTED,
    supports_pagination=False,
    historical_backfill_supported=False,
    forward_incremental_supported=True,
    seed_page_discovery_supported=True,
    preferred_seed_transport=FetchStrategy.BROWSER,
    preferred_fetch_strategy=FetchStrategy.BROWSER,
    robots_required=True,
    detail_fetch_supported=True,
)
```

### 3.3. Luồng Thu thập (Forward Flow)
1. **Lập kế hoạch (`CrawlPlanner`)**:
   - Nhận diện `historical_backfill_supported == False`.
   - Lập kế hoạch với chế độ `FORWARD_ONLY_INCREMENTAL`, `safety_max_pages = 1`, `start_page = 1`.
   - Tuyệt đối không sinh `BOOTSTRAP_FULL` hay tăng `current_page > 1`.
2. **Thẩm định (`SourceQualifier`)**:
   - Kiểm tra `RobotsPolicy` đối với URL Landing Seed (`https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh`).
   - Kết quả: `ALLOWED` (HTTP 200).
3. **Thực thi (`CrawlRunner`)**:
   - `BrowserFetcher` sử dụng Playwright Chromium headless tải và render JavaScript đầy đủ.
   - `NhatotListingParser` bóc tách danh sách 25 cards tin đăng.
   - So khớp định danh duy nhất `(source, source_listing_id)` với `LocalSeenListingRepository`.
   - **Phiên 1**: Phát hiện 24 tin mới $\rightarrow$ Ghi nhận 24 bản ghi vào Bronze Dataset (`/data/bronze/nhatot/...`) $\rightarrow$ Cập nhật danh sách seen IDs.
   - **Phiên 2 (Re-run ngay)**: Toàn bộ 25 tin đều là tin đã biết $\rightarrow$ `records_new = 0`, `records_created = 0`, `bronze_path = None`, không sinh file Bronze rỗng $\rightarrow$ Dừng ngay với lý do `KNOWN_REGION_REACHED`.
4. **Cập nhật Vết Checkpoint (`update_checkpoint`)**:
   - Giữ nguyên `bootstrap_completed = False` và `last_full_crawl_at = None`.
   - Cập nhật `last_success_at = now`, `last_watermark_at = now`, `consecutive_failures = 0`.
   - Nguồn luôn sẵn sàng cho chu kỳ cào gia tăng tiếp theo.

---

## 4. Báo cáo Độ phủ Chuẩn xác (Accuracy Reporting Standards)

Hệ thống cấm tuyệt đối việc báo cáo sai lệch trạng thái hoàn tất:
- **KHÔNG BAO GIỜ** đánh dấu `HISTORICAL_COMPLETE` cho Nhà Tốt hoặc các nguồn Forward-Only.
- Báo cáo Airflow Run Summary luôn phản ánh trung thực:
  - **NhaTot**: Acquisition = `FORWARD_ONLY`, Browser = `AVAILABLE`, Historical = `UNAVAILABLE`.
  - **PhongTro123**: Historical = `IN_PROGRESS` (Continuation Page N), Mode = `BOOTSTRAP_CONTINUE`.
  - **NhaTroVN**: Historical = `COMPLETE`, Mode = `INCREMENTAL`.
  - **Muaban / BatDongSan**: Content = `ACCESS_CHALLENGED` / `ACCESS_BLOCKED`, Health = `COOLDOWN_ACTIVE`.

---

## 5. Câu hỏi Phỏng vấn Kỹ thuật (Interview Q&A)

### Q1: Làm thế nào hệ thống biết khi nào nên dừng cào phân trang?
*A: Hệ thống áp dụng 3 cơ chế dừng độc lập:*
1. *Dừng theo nguồn (`SOURCE_END`): Trang hiện tại không còn thẻ tin nào hoặc parser không tìm thấy liên kết Next Page.*
2. *Dừng theo vùng tin đã biết (`KNOWN_REGION_REACHED`): Trong chế độ `INCREMENTAL`, khi gặp liên tiếp `stop_after_known_pages` trang chỉ chứa toàn tin đã có trong `SeenListingRepository` (streak >= 2 đối với phân trang thông thường, hoặc streak >= 1 đối với forward-only).*
3. *Dừng theo ngưỡng an toàn (`MAX_PAGES_REACHED` / `MAX_RECORDS_REACHED`): Đảm bảo phiên cào không chạy vô tận khi có sự cố vòng lặp trang từ phía nguồn.*

### Q2: Tại sao không dùng ID tự tăng (Auto-increment ID) làm Watermark cho tất cả các nguồn?
*A: Các nguồn dữ liệu khác nhau có cấu trúc định danh khác nhau (VD: NhaTot dùng ID số nhưng phân tán theo chuyên mục, BatDongSan dùng mã tin, NhaTroVN dùng mã tin theo thứ tự đăng). Do đó, Watermark chuẩn hóa của RoomBeacon sử dụng `crawled_at / posted_at` (ISO 8601 Timestamp) kết hợp với tập hợp Persistent Seen Listing IDs `(source, source_listing_id)` để đảm bảo tính bất biến và triệt tiêu trùng lặp trên tầng Bronze.*
