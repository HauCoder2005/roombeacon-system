# KIẾN TRÚC ĐƯỜNG ỐNG TÀI NGUYÊN HÌNH ẢNH (ASSET PIPELINE)

Tài liệu này mô tả chi tiết kiến trúc, cơ chế tải, kiểm thực, điều phối công bằng đa nguồn (Fair Source Scheduling) và lưu trữ tài nguyên nhị phân hình ảnh vào **MinIO Object Storage (`roombeacon-assets`)** trong hệ thống **RoomBeacon**.

---

## 1. Mục Tiêu và Kiến Trúc Tổng Quan

```mermaid
flowchart LR
    Bronze[(post_images)]
    Scheduler[Fair Asset Scheduler]
    Reconciler[Asset Reconciler Service]
    Validate[Download + Magic Bytes]
    MinIO[(MinIO roombeacon-assets)]
    State[(Durable Asset State)]

    Bronze --> Reconciler
    State --> Reconciler
    Reconciler --> Scheduler
    Scheduler --> Validate
    Validate --> MinIO
    Validate --> State
```

### Tại sao cần tách rời Asset Pipeline?
1. **Không nhồi nhét dữ liệu nhị phân vào Database hoặc Parquet**: Cơ sở dữ liệu quan hệ (MySQL Bronze) và tệp phân tích (Silver Parquet) chỉ lưu trữ siêu dữ liệu (Metadata) như URL, kích thước, vị trí ảnh. Dữ liệu nhị phân (Binary stream) thuộc về hệ thống Object Storage (MinIO).
2. **Không cào lại trang web (No Recrawl Needed)**: MySQL Bronze bảng `post_images` đã lưu giữ đầy đủ danh sách URL của các hình ảnh. Asset Reconciler trực tiếp truy vấn danh sách này và tải bù mà không cần crawler quét lại trang chi tiết hay danh mục.
3. **Cách ly tải và bảo vệ crawler**: Nếu một trang web chứa ảnh bị chậm hoặc lỗi tải ảnh, quá trình crawler tin tức không bị nghẽn (decoupled failure boundary).

---

## 2. Phân Định Danh Mục Vòng Đời và Bảng Kiểm Kê (Backlog Accounting)

Để đảm bảo số liệu kiểm kê luôn nhất quán và không bị mơ hồ giữa các loại URL, Asset Pipeline định nghĩa 5 trạng thái vòng đời tách biệt:

- **`TOTAL_METADATA`**: Tổng số hàng bản ghi trong `post_images` của nguồn đó.
- **`STORED`**: Đã tải và lưu trữ thành công trên MinIO (`status == SUCCESS`).
- **`ACTIONABLE_PENDING`**: Các URL dạng HTTP/HTTPS hợp lệ chưa được lưu trên MinIO và không nằm trong trạng thái lỗi vĩnh viễn (sẵn sàng để tải).
- **`RETRYABLE_FAILED`**: Các bản ghi gặp lỗi mạng/timeout tạm thời với số lần thử `attempt_count < max_retries`.
- **`TERMINAL`**: Các bản ghi không thể tải vĩnh viễn (gồm Data URI base64 placeholder, đường dẫn tương đối `/images/...`, lỗi HTTP 404/410, Cloudflare Challenge, magic bytes không hợp lệ).

### Hệ Thức Bất Biến Kiểm Kê (Accounting Invariant):

$$\text{Total Metadata} = \text{Stored} + \text{Actionable Pending} + \text{Retryable Failed} + \text{Terminal}$$

---

## 3. Cơ Chế Điều Phối Đa Nguồn Công Bằng (Fair Multi-Source Scheduling)

### Vấn đề của sắp xếp toàn cục cũ:
Trước đây, câu lệnh chọn ứng viên sử dụng `ORDER BY pi.id DESC LIMIT 1000`. Do NhaTroVN có hàng chục nghìn bản ghi được chèn gần đây với ID cao nhất (ID > 5.300.000), toàn bộ quota của mỗi batch bị NhaTroVN chiếm trọn, khiến các nguồn khác như `phongtro123`, `nhatot`, `batdongsan` rơi vào tình trạng **bị bỏ đói tài nguyên (starvation)**.

### Giải pháp: Fair Quota Allocation với Dynamic Spillover (`FairAssetScheduler`):
1. **Phân bổ hạn ngạch công bằng ban đầu**:
   - Đối với mỗi chu kỳ `batch_size = B` (ví dụ 50 ảnh), hệ thống xác định các nguồn đang hoạt động có ứng viên cần xử lý.
   - Hạn ngạch cơ sở cho mỗi nguồn: $Q = \lfloor B / N_{\text{active}} \rfloor$.
2. **Cơ chế tràn hạn ngạch động (Dynamic Spillover)**:
   - Nếu một nguồn không có đủ ứng viên để lấp đầy quota (ví dụ BatDongSan chỉ còn 2 ảnh), các vị trí trống chưa sử dụng sẽ **tự động tràn (spillover)** và được chia đều cho các nguồn còn lại có nhu cầu cao hơn.
3. **Thứ tự xử lý nội bộ nguồn (Within-Source Ordering)**:
   - Trong từng nguồn cụ thể, các ảnh được truy vấn theo thứ tự **`ORDER BY pi.id ASC`** (ảnh cũ nhất được ưu tiên xử lý trước), giúp giải phóng dần backlog lịch sử và chống lão hóa bản ghi.

---

## 4. Mô Hình Trạng Thái Bền Vững (Durable Asset State)

Để đảm bảo quy trình đối soát có khả năng sống sót sau khi khởi động lại container, Airflow restart hoặc reboot máy chủ, toàn bộ trạng thái tài nguyên được lưu trên ổ đĩa vật lý máy chủ tại `/data/state/assets/{source}/{asset_id}.json`.

- **Quy ước Object Key**: `source/platform_post_id/img_<position>_<url_hash>.<ext>` (Ví dụ: `phongtro123/12345/img_1_a30cf423.jpg`).
- **Tính lũy đọng (Idempotency)**: Khi chạy lại, các ảnh có trạng thái `SUCCESS` được bỏ qua 100% (`already_stored > 0, attempted = 0, uploaded = 0`), không tạo tải thừa ra Internet hay ghi đè lặp lại lên MinIO.

---

## 5. Cơ Chế Kiểm Thực An Toàn (Download & Validation)

Mọi tệp tin trước khi được lưu vào MinIO đều phải vượt qua chuỗi kiểm tra an toàn:
1. **Kiểm tra giao thức**: Chỉ chấp nhận `http://` hoặc `https://`.
2. **Kiểm tra HTTP Status**: Chỉ chấp nhận `200 OK`. Lỗi 400/403/404/410 $\rightarrow$ `TERMINAL_FAILURE`. Lỗi 429/5xx/timeout $\rightarrow$ `RETRYABLE_FAILURE`.
3. **Phát hiện HTML/JSON giả mạo**: Header chứa `text/html` hoặc `application/json` (Cloudflare Challenge) $\rightarrow$ `TERMINAL_FAILURE (HTML_CHALLENGE)`.
4. **Kiểm tra Magic Bytes**: Nhận diện đúng cấu trúc nhị phân của `JPEG`, `PNG`, `WebP`, `GIF`.
5. **Giới hạn dung lượng**: Từ chối tệp rỗng (0 bytes) hoặc vượt quá 15 MB.

---

## 6. Tự Động Hóa Qua Airflow DAG

DAG `roombeacon_asset_reconciler` (`airflow/dags/assets/roombeacon_asset_reconciler.py`) chạy định kỳ mỗi 30 phút (`15,45 * * * *`) với ngân sách an toàn (`batch_budget = 50`), tự động tạo báo cáo kiểm toán chi tiết theo từng nguồn sau mỗi chu kỳ.

---

## 7. Định Danh Tài Nguyên Độc Nhất & Quy Mô Khối Lượng Thực Tế (Unique Asset Identity & Backlog Sizing)

### 7.1 Phân biệt Hàng Metadata (`post_images`) và Tệp Ảnh Vật Lý Thực Tế
- Trong cơ sở dữ liệu Bronze, mỗi lần quan sát (observation/version) của tin đăng có thể ghi nhận lại danh sách ảnh của bài đăng đó.
- Do đó, **59.697 hàng bản ghi `post_images`** chỉ đại diện cho số lần liên kết quan sát, trong đó có tới **50.477 hàng lặp lại qua các phiên bản (Cross-version Duplicates, chiếm 84,55%)**.
- Số lượng tệp ảnh URL độc nhất thực tế toàn hệ thống chỉ là **9.199 ảnh HTTP hợp lệ** (trong đó `phongtro123` chiếm 7.320 ảnh, `nhatrovn` chiếm 1.539 ảnh, `nhatot` chiếm 311 ảnh, `batdongsan` chiếm 29 ảnh).

### 7.2 Nguồn gốc xuất xứ ảnh (Card Thumbnail vs Detail Gallery)
- **PhongTro123, NhaTot, BatDongSan**: Dữ liệu hiện tại chủ yếu là ảnh đại diện thu nhỏ (Thumbnail) trích xuất từ trang danh mục (Card-level pagination), với mật độ trung bình ~1 ảnh/tin đăng.
- **NhaTroVN**: Có sự phân hóa rõ rệt:
  - 1.063 tin đăng lightweight chỉ có thumbnail (~1,37 ảnh/tin).
  - 103 tin đăng đã được nạp chi tiết (detail-enriched) chứa bộ sưu tập ảnh phòng thực tế (Gallery) với mật độ trung bình **4,54 ảnh/tin**.
- **Kết luận**: Việc thiếu ảnh gallery ở các nguồn khác là do chưa thu thập trang chi tiết (Detail Page Crawling), không phải do lỗi của Asset Pipeline.

### 7.3 Định cỡ dung lượng và Tính toán thông lượng Backlog
- Dựa trên 39 mẫu ảnh thực tế đã lưu trong MinIO:
  - Dung lượng trung vị: **71,27 KB/ảnh** (trung bình: 133,26 KB).
  - Tổng dung lượng ước tính cho toàn bộ 9.160 ảnh còn lại: **~653 MB** (mức trần: ~2,29 GB).
- Với cấu hình an toàn hiện tại (50 ảnh/run, 48 run/ngày = 2.400 ảnh/ngày):
  - Thời gian hoàn tất nạp bù toàn bộ backlog độc nhất: **~3,8 ngày**.
  - Không cần thiết lập thông lượng ồ ạt, tránh rủi ro nghẽn mạng hoặc kích hoạt cơ chế phòng vệ (Rate Limit/WAF) của các nền tảng nguồn.

