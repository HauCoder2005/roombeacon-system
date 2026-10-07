# Notebook 01: Phân Tích Khám Phá Dữ Liệu (EDA) — Hướng Dẫn Kỹ Thuật

Tài liệu này cung cấp hướng dẫn kỹ thuật chi tiết theo từng cell và cẩm nang debug cho `notebooks/01_roombeacon_eda.ipynb`.

---

## 1. Tổng Quan và Vai Trò Kiến Trúc

`01_roombeacon_eda.ipynb` là một **notebook kiểm toán quan sát hoàn toàn chỉ đọc (read-only)**. Vai trò của nó trong pipeline RoomBeacon là:
- Thiết lập đường cơ sở dữ liệu (data baseline) cho snapshot Bronze thô (132.436 tin đăng thu thập được).
- Kiểm toán tính toàn vẹn của khóa chính, quy luật dữ liệu bị thiếu và sự khác biệt giữa các nguồn thu thập.
- Định lượng phân phối giá trị số, tỷ lệ lỗi phân tích cú pháp, và sự không nhất quán giữa giá và diện tích.
- Nhận diện các dữ liệu nhiễu không phải phòng thuê thông thường (tin bán nhà, sang nhượng quán/mặt bằng, thuê nguyên tòa nhà) và các sai lệch tọa độ bản đồ.
- Rút ra các yêu cầu thực nghiệm làm căn cứ để hiện thực hóa trong `02_roombeacon_silver.ipynb`.

> [!NOTE]
> Notebook này hoạt động ở chế độ chỉ đọc. Notebook không thay đổi dữ liệu thô, không sửa đổi các bảng trong cơ sở dữ liệu, và không ghi đè hay tạo mới dataset Parquet trên đĩa.

---

## 2. Dữ Liệu Đầu Vào và Điều Kiện Tiên Quyết

- **Thư mục đầu vào:** `data/bronze/snapshot/`
  - `latest_posts.parquet` (132.436 dòng, 20 cột): Bản ghi quan sát mới nhất theo từng `rental_post_id`.
  - `raw_evidence.parquet` (132.436 dòng, 11 cột): Chuỗi văn bản thô chưa bóc tách (`price_raw`, `area_raw`, `currency`, `period`) dùng để kiểm tra dòng dõi dữ liệu số.
  - `metadata.json`: Chữ ký hash SHA-256, số dòng và mốc thời gian quan sát.
- **Hàm nạp dữ liệu:** `analytics.bronze.snapshot.load_bronze_snapshot(SNAPSHOT_DIR)`.
- **Hạt nhân dữ liệu (Grain):** Chính xác một bản ghi cho mỗi `rental_post_id`.
- **Khung thời gian:** 2026-09-20 12:48:44 đến 2026-09-30 10:42:53 (~10 ngày).

---

## 3. Hướng Dẫn Chi Tiết Từng Phần và Từng Cell

### Phần 00: Khởi Tạo Môi Trường và Nạp Dữ Liệu (Cells 000–003)

- **Cell 000 (Markdown):** Tiêu đề notebook và tổng quan kiến trúc.
- **Cell 001 (Code):** Khởi tạo các thư viện Python (`numpy`, `pandas`, `matplotlib`, `plotly`, `duckdb`) và các hàm tiện ích từ `notebooks/utils/`.
  - Cấu hình `sys.path` bằng `setup_project_path()` để notebook chạy được từ cả thư mục gốc lẫn thư mục `notebooks/`.
  - Cấu hình hiển thị pandas và giao diện mặc định của Plotly (`plotly_white`).
- **Cell 002 (Markdown):** Giải thích phạm vi dữ liệu runtime.
- **Cell 003 (Code):** Gọi hàm `load_bronze_snapshot(SNAPSHOT_DIR)`.
  - Trả về `df_latest`, `raw_evidence`, và `run_context`.
  - Xác nhận thời gian nạp cục bộ $< 2$–$3$ giây nhờ cơ chế memory-mapping của Parquet.

> Debug note: Cấu hình renderer của Plotly mặc định là `'plotly_mimetype+notebook_connected'`. Trong môi trường terminal không có giao diện đồ họa hoặc trình xem notebook không hỗ trợ widget tương tác, biểu đồ Plotly có thể hiển thị dưới dạng khoảng trắng hoặc fallback tĩnh. Hãy mở notebook bằng trình duyệt tiêu chuẩn (VS Code Notebook hoặc JupyterLab) để tương tác đầy đủ với biểu đồ.

---

### Phần 01: Tổng Quan Dataset và Hạt Nhân Dữ Liệu (Cells 004–016)

- **Cell 004–005 (Markdown):** Tiêu đề mục Tổng quan và Nạp Dataset.
- **Cell 006 (Code):** Sao chép `df_latest` sang biến làm việc `df` để bảo vệ dữ liệu snapshot trong bộ nhớ.
- **Cell 007–009 (Markdown & Code):** Kiểm toán hạt nhân dữ liệu (grain).
  - Xác nhận tổng số dòng: `132.436`.
  - Chạy lệnh kiểm tra tính duy nhất: `assert len(df) == df["rental_post_id"].nunique()`.
- **Cell 010–011 (Markdown & Code):** Xem trước 10 dòng đầu tiên trên toàn bộ 20 trường dữ liệu Bronze.
- **Cell 012 (Code):** Xây dựng bảng kiểm toán cấu trúc các trường (`field_overview`):
  - Báo cáo tên cột, kiểu dữ liệu, số lượng null, tỷ lệ phần trăm null, và số giá trị duy nhất (unique).
- **Cell 013–014 (Markdown & Code):** Tính toán phân phối theo cổng nguồn thu thập (`source_distribution`):
  - Cho thấy Phongtro123 (71.403 tin) và Chothuephongtro (35.796 tin) chiếm đa số dung lượng (~81%), tiếp theo là Cafeland (9.984 tin), Mogi (9.782 tin), Nhatot (2.642 tin), Muaban (1.621 tin), Nhatrovn (869 tin), Tromoi (255 tin), và Chothuenha (84 tin).
- **Cell 015–016 (Markdown & Code):** Kiểm toán độ bao phủ thời gian (`temporal_coverage`):
  - Kiểm tra ngày nhỏ nhất và lớn nhất trên các trường `latest_observed_at`, `first_observed_at`, và `last_observed_at`.
  - Khẳng định cửa sổ dữ liệu thực nghiệm kéo dài khoảng 10 ngày.

---

### Phần 02: Cấu Trúc và Tính Toàn Vẹn Dữ Liệu (Cells 017–026)

- **Cell 017–019 (Markdown & Code):** Kiểm toán tính toàn vẹn định danh (`identifier_integrity`).
  - Kiểm tra giá trị null và tính duy nhất của `rental_post_id` và `source_listing_id`.
  - Nhận diện: `rental_post_id` là duy nhất toàn cục, nhưng `source_listing_id` có thể trùng lặp giữa các cổng nguồn (`source_code`) khác nhau.
- **Cell 020–022 (Markdown & Code):** Kiểm toán các bản ghi trùng lặp (`duplicate_checks`, `duplicate_urls`).
  - Kiểm tra sự trùng lặp hoàn toàn trên tiêu đề, địa chỉ và URL.
  - Phát hiện nhiều `rental_post_id` khác nhau chia sẻ chung một URL listing (do tin được đăng lại hoặc crawl lại tại các thời điểm khác nhau).
- **Cell 023–024 (Markdown & Code):** Kiểm toán tính nhất quán thời gian (`temporal_checks`).
  - Xác nhận `first_observed_at <= last_observed_at` và `first_observed_at <= latest_observed_at <= last_observed_at`.
  - Phát hiện 0 trường hợp đảo ngược thời gian nghiêm trọng trong Bronze.
- **Cell 025–026 (Markdown & Code):** Kiểm tra phạm vi giá trị cơ bản (`range_checks`).
  - Kiểm tra biên không âm đối với `price_amount`, `area_value`, và `active_days`.

---

### Phần 03: Phân Tích Dữ Liệu Bị Thiếu (Cells 027–035)

- **Cell 027–029 (Markdown & Code):** Ma trận thiếu dữ liệu tổng thể (`missing_flags = df.isna()`).
  - Trực quan hóa tỷ lệ thiếu dữ liệu trên toàn bộ các cột.
- **Cell 030–031 (Markdown & Code):** Bảng các trường quan trọng bị thiếu (`important_fields`).
  - Đánh giá `title_raw`, `price_amount`, `area_value`, `best_address_text`, và `map_latitude`.
- **Cell 032–033 (Markdown & Code):** Tỷ lệ thiếu dữ liệu phân nhóm theo cổng nguồn (`missingness_by_source`).
  - Làm rõ sự phân hóa sâu sắc giữa các cổng:
    - Mogi cung cấp gần như 100% tọa độ (`map_latitude`).
    - Chợ Tốt và Phongtrọ123 thiếu tọa độ trên 90% số tin đăng, chỉ dựa vào chuỗi địa chỉ văn bản.
- **Cell 034–035 (Markdown & Code):** Mẫu hình đồng thiếu (co-missingness).
  - Khẳng định `map_latitude` và `map_longitude` luôn bị thiếu đồng thời trong 100% trường hợp (không có hiện tượng có vĩ độ mà thiếu kinh độ).

---

### Phần 04: Chất Lượng Dữ Liệu Số và Phân Tích Ngoại Lai (Cells 036–049)

- **Cell 036–037 (Markdown & Code):** Lọc các trường số ứng viên (`price_amount`, `area_value`).
- **Cell 038–041 (Markdown & Code):** Phân phối giá và phát hiện ngoại lai theo phương pháp IQR.
  - Tính các phân vị: Phân vị 1 (P01), 25 (Q1), 50 (trung vị), 75 (Q3), 95, 99 và giá trị lớn nhất (Max).
  - Phát hiện các giá trị cực đoan: giá bằng 0 VNĐ hoặc chỉ 10.000 VNĐ, và các mức giá vượt quá 50.000.000.000 VNĐ (50 tỷ VNĐ).
  - Chỉ ra rằng các tin đăng hàng chục tỷ đồng thực chất là tin bán bất động sản bị cào nhầm vào chuyên mục cho thuê.
- **Cell 042–045 (Markdown & Code):** Phân phối diện tích và phát hiện ngoại lai IQR.
  - Diện tích dao động từ 0 m² đến hơn 10.000 m². Trung vị diện tích là ~25 m² (phù hợp với phòng trọ/studio thực tế).
- **Cell 046–047 (Markdown & Code):** Các trường số khác (`active_days`).
- **Cell 048–049 (Markdown & Code):** Tính nhất quán giữa Giá và Diện tích (`price_area_mask`).
  - Tính toán đơn giá thô `price_per_area` (VNĐ/m²).
  - Chỉ ra các tin đăng phi lý: giá 50 triệu cho phòng 10 m² hoặc giá 500 nghìn cho nhà 500 m².

---

### Phần 05: Phân Tích Chất Lượng Văn Bản (Cells 050–054)

- **Cell 050–052 (Markdown & Code):** Kiểm toán các trường văn bản (`title_raw`, `full_address_text`, `location_raw`).
  - Nhận diện các thực thể HTML (`&amp;`, `&quot;`, `&#39;`), khoảng trắng bất thường, ký tự xuống dòng thừa, và viết hoa toàn bộ.
- **Cell 053–054 (Markdown & Code):** Phân tích độ dài văn bản (`length_fields`).
  - Phát hiện các tiêu đề ngắn dưới 5 ký tự (như `"..."`, `"thuê"`, `"nhà"`), không đủ cung cấp ngữ nghĩa để phân loại.

---

### Phần 06: Chất Lượng Địa Chỉ và Vị Trí (Cells 055–065)

- **Cell 055–057 (Markdown & Code):** Chạy thử nghiệm bóc tách địa chỉ bằng `apply_address_parsing`.
  - Phân tách chuỗi địa chỉ thành: `street`, `ward`, `district`, `province`.
  - Theo dõi trạng thái phân tích: `PARSED`, `FALLBACK_PARSED`, `UNPARSED`.
- **Cell 058–061 (Markdown & Code):** Phân tích độ dài địa chỉ và định dạng ngoại lai.
  - Phân tích các địa chỉ rỗng hoặc các mô tả quá dài bị điền nhầm vào ô địa chỉ.
- **Cell 062–063 (Markdown & Code):** Kiểm toán sáp nhập đơn vị hành chính (`administrative_status`).
  - Áp dụng `apply_ward_mapping` để nhận diện các phường cũ đã sáp nhập (đặc biệt là việc thành lập TP. Thủ Đức năm 2021).
  - Gắn cờ các tên phường trùng lặp giữa nhiều quận (như "Phường 1", "Phường 2", "Phường Tân Hưng").
- **Cell 064–065 (Markdown & Code):** Chất lượng tọa độ và kiểm tra biên địa lý (bounding box).
  - Kiểm tra biên TP.HCM (vĩ độ ~10.3 đến 11.2, kinh độ ~106.3 đến 107.1).
  - Phát hiện ~7,98% tin đăng có tọa độ chia sẻ chung cùng một điểm làm tròn nhưng có chuỗi địa chỉ đường phố xung đột nhau (điểm mặc định/centroid của cổng thông tin).

---

### Phần 07: Chất Lượng Dữ Liệu Theo Cổng Nguồn (Cells 066–067)

- **Cell 066–067 (Markdown & Code):** Bảng điểm so sánh chất lượng giữa các crawler (`source_quality_flags`).
  - Đo lường độ đầy đủ của giá, diện tích, địa chỉ, và tọa độ trên từng cổng thông tin.

---

### Phần 08: Phân Tích Mối Quan Hệ Giữa Các Biến (Cells 068–090)

- **Cell 068–070 (Markdown & Code):** Quan hệ giữa Giá và Diện tích trên các cặp giá trị dương.
  - Lọc các khu vực có số mẫu tối thiểu `MIN_LOCATION_SAMPLE = 50`.
- **Cell 071–076 (Markdown & Code):** Mối quan hệ Vị trí x Giá và Vị trí x Diện tích giữa các phường.
  - Tính trung vị giá, diện tích và đơn giá VNĐ/m² cho từng phường.
- **Cell 077–084 (Markdown & Code):** Thiên lệch định giá giữa các nguồn.
  - Chứng minh các cổng chuyên sinh viên (Phongtrọ123) có giá trung vị thấp hơn rõ rệt so với cổng căn hộ trung-cao cấp (Mogi, Batdongsan).
- **Cell 085–090 (Markdown & Code):** Ảnh hưởng của độ phân giải địa chỉ lên giá.
  - Đo lường mức độ ổn định của giá đối với các tin đăng phân tích địa chỉ thành công so với thất bại.

---

### Phần 09: Đánh Giá Tính Sẵn Sàng Của Dữ Liệu RoomBeacon (Cells 091–107)

- **Cell 091–093 (Markdown & Code):** Tính sẵn sàng của các trường cốt lõi (`title_text`, `price_numeric`).
- **Cell 094–095 (Markdown & Code):** Khả năng sử dụng của tiêu đề phòng thuê (`title_length >= 5`).
- **Cell 096–097 (Markdown & Code):** Bộ lọc khả năng sử dụng của giá và diện tích.
- **Cell 098–099 (Markdown & Code):** Tính sẵn sàng phân giải vị trí (`parsed_address`).
- **Cell 100–101 (Markdown & Code):** Tính sẵn sàng độ tin cậy tọa độ (`coordinate_audit`).
- **Cell 102–103 (Markdown & Code):** Cờ sẵn sàng đặc thù cho từng nguồn.
- **Cell 104–105 (Markdown & Code):** Bằng chứng về tin đăng lặp lại / repost.
- **Cell 106–107 (Markdown & Code):** Bảng tổng kết tính sẵn sàng (`overall_readiness`).

---

### Phần 10 & 11: Kết Quả Kiểm Toán và Yêu Cầu Xử Lý (Cells 108–111)

- **Cell 108–109 (Markdown & Code):** Tổng kết ngắn gọn bằng văn bản về các phát hiện thực nghiệm cốt lõi.
- **Cell 110–111 (Markdown & Code):** Thiết lập các yêu cầu xử lý chính thức cho tầng Silver (`processing_requirements`):
  1. Chuẩn hóa văn bản và đưa về dạng Unicode NFC.
  2. Bóc tách và chuẩn hóa phân cấp hành chính phường, quận.
  3. Xác thực giá và diện tích đối chiếu với bằng chứng chuỗi thô của crawler.
  4. Phân loại độ tin cậy tọa độ và cô lập các điểm mặc định (hotspots).
  5. Gom cụm các tin đăng trùng lặp/repost giữa các nguồn.
  6. Gắn cờ trạng thái chất lượng dòng mà không được xóa bỏ các dòng dữ liệu bẩn.

---

## 4. Các Phát Hiện Thực Nghiệm Cốt Lõi

1. **Khóa chính sạch sẽ:** Trường `rental_post_id` đạt 100% tính duy nhất và không bị null trong Bronze.
2. **Sự khan hiếm tọa độ:** Hơn 89,8% tin đăng Bronze thô hoàn toàn không có tọa độ bản đồ.
3. **Hiện tượng ghim điểm giả (Hotspots):** Trong số các tin có tọa độ, khoảng 10.533 tin dùng chung tọa độ giống hệt nhau nhưng có địa chỉ đường phố mâu thuẫn hoàn toàn (tọa độ trung tâm hành chính của quận).
4. **Nhiễu phi cho thuê:** Tập dữ liệu thô bị lẫn các tin bán bất động sản (bán nhà, bán đất), sang nhượng hợp đồng/mặt bằng kinh doanh, và cho thuê cả tòa nhà.
5. **Đơn vị giá phức tạp:** Giá thuê trong tiêu đề và mô tả xuất hiện nhiều dạng viết tắt ("3tr5", "11 tỷ", "3.500.000 vnđ", "15k/ngày").

---

## 5. Cẩm Nang Debug Dành Cho Lập Trình Viên

### Cách Chạy Notebook 01
1. Đảm bảo các file snapshot đã sẵn sàng:
   ```bash
   ls -la data/bronze/snapshot/
   ```
2. Mở notebook và chạy tuần tự từ cell đầu đến cell cuối. Thời gian thực thi thông thường mất ~45–60 giây.

### Xử Lý Sự Cố Thường Gặp
- **Nếu `Cell 003` báo lỗi `BronzeSnapshotError`:**
  - Kiểm tra xem file `data/bronze/snapshot/latest_posts.parquet` và `raw_evidence.parquet` có tồn tại không.
  - Chạy lệnh sau để tạo lại snapshot nếu file bị thiếu:
    ```bash
    python -m analytics.bronze.snapshot
    ```
- **Nếu biểu đồ Plotly không hiển thị:**
  - Kiểm tra xem môi trường xem notebook có hỗ trợ JavaScript của Plotly không.
  - Có thể chuyển tạm renderer tại Cell 001 để debug chế độ headless: `pio.renderers.default = "png"`.
