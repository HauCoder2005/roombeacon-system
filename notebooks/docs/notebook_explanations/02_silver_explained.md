# Notebook 02: Chuyển Đổi Bronze Sang Silver — Hướng Dẫn Kỹ Thuật

Tài liệu này cung cấp hướng dẫn kỹ thuật chi tiết theo từng cell và cẩm nang debug cho `notebooks/02_roombeacon_silver.ipynb`.

---

## 1. Tổng Quan và Vai Trò Kiến Trúc

`02_roombeacon_silver.ipynb` là **động cơ chuyển đổi dữ liệu chuẩn hóa (canonical data transformation engine)** của pipeline RoomBeacon. Nó biến đổi snapshot Bronze thô thành dataset Silver phục vụ sản xuất (`data/silver/rental_listings.parquet`).

### Các Bất Biến Kiến Trúc Cốt Lõi:
1. **Bảo toàn 100% Số Dòng (Row Preservation):**
   - Mọi bản ghi Bronze thô đều được giữ lại nguyên vẹn.
   - Đầu vào: 132.436 dòng $\rightarrow$ Đầu ra: 132.436 dòng.
   - Tuyệt đối không xóa, không lọc bỏ hay nhân đôi bản ghi trong quá trình biến đổi.
2. **Tính Bất Biến Của Dòng Dõi Thô (Raw Lineage Immutability):**
   - Toàn bộ 20 cột Bronze ban đầu được giữ nguyên vẹn từng ký tự.
   - Các giá trị đã làm sạch và bằng chứng chất lượng được gắn thêm vào các cột mới (tổng cộng 80 cột).
3. **Phân Loại, Không Loại Bỏ (Classify, Never Drop):**
   - Các giá trị ngoại lai thống kê, tin đăng nghi trùng lặp, và giá chưa xác thực đều được gắn nhãn trạng thái rõ ràng, không bao giờ bị loại khỏi bảng.
4. **Cổng Kiểm Soát Chất Lượng Tiền Silver (Pre-Silver Quality Gate):**
   - Trước khi ghi file Parquet ra đĩa, dataset bắt buộc phải vượt qua 10 phép kiểm tra bất biến nghiêm ngặt. Nếu có bất kỳ điều kiện nào thất bại, quá trình dừng ngay lập tức.

---

## 2. Thông Số Đầu Vào và Đầu Ra

- **Đầu vào:**
  - `data/bronze/snapshot/latest_posts.parquet` (132.436 dòng)
  - `data/bronze/snapshot/raw_evidence.parquet` (132.436 dòng)
  - `data/bronze/snapshot/metadata.json`
- **Đầu ra:**
  - `data/silver/rental_listings.parquet` (32,4 MB, 132.436 dòng, 80 cột)
  - `data/silver/rental_listings.metadata.json` (Lược đồ phiên bản 2.1.0, tóm tắt kiểm toán chất lượng, chữ ký hash dòng dõi)

---

## 3. Hướng Dẫn Chi Tiết Từng Phần và Từng Cell

### Phần 00: Khởi Tạo Môi Trường và Các Hàm Tiện Ích (Cells 00–02)

- **Cell 00 (Markdown):** Tiêu đề notebook và các nguyên lý kiến trúc của tầng Silver.
- **Cell 01 (Code):** Khởi tạo thư viện (`numpy`, `pandas`, `duckdb`, `matplotlib`) và các hàm nghiệp vụ:
  - `load_bronze_snapshot` từ `analytics.bronze.snapshot`
  - `build_silver_dataset`, `evaluate_pre_silver_quality_gate` từ `notebooks.utils.silver_processing`
  - Các hàm báo cáo kiểm toán từ `notebooks.utils.silver_reporting`
  - Định nghĩa các hàm vẽ biểu đồ: `barh_table` và `grouped_coverage`.
- **Cell 02 (Markdown):** Tổng quan kiến trúc pipeline chuyển đổi Silver.

---

### Phần 01: Nạp Snapshot Bronze (Cells 03–04)

- **Cell 03 (Markdown):** Giải thích nguồn dữ liệu Bronze.
- **Cell 04 (Code):** Gọi hàm `load_bronze_snapshot(SNAPSHOT_DIR)`:
  - Nạp `bronze_df` (132.436 dòng) và `raw_evidence` (132.436 dòng).
  - Hiển thị ID snapshot và xác nhận số dòng.

---

### Phần 02: Ma Trận Hợp Đồng Chuyển Đổi (Cells 05–06)

- **Cell 05 (Markdown):** Mô tả lược đồ và hợp đồng biến đổi dữ liệu.
- **Cell 06 (Code):** Hiển thị bảng `processing_contract` chi tiết các phép biến đổi:
  - Chuẩn hóa văn bản, ý định tin đăng, bóc tách địa chỉ, ánh xạ phường, kiểm thực giá/diện tích, phân loại ngoại lai, độ tin cậy tọa độ, phát hiện trùng lặp và chất lượng tổng hợp của dòng.

---

### Phần 03: Chuẩn Hóa Văn Bản Chung (Cells 07–08)

- **Cell 07 (Markdown):** Các quy tắc chuẩn hóa văn bản.
- **Cell 08 (Code):** Gọi hàm `build_silver_dataset(bronze_df, raw_evidence)`.
  - Áp dụng `apply_text_standardization` lên `title_raw`, `full_address_text`, `location_raw`, và `best_address_text`.
  - Chuẩn hóa Unicode về dạng chuẩn NFC.
  - Xóa bỏ thực thể HTML (`&amp;`, `&nbsp;`), xóa dấu câu thừa ở cuối câu, thu gọn khoảng trắng liên tiếp và chuyển chuỗi rỗng thành `pd.NA`.
  - Hiển thị bảng đo lường mức độ thay đổi văn bản (số ký tự thay đổi, số dòng được chuẩn hóa).

---

### Phần 04: Đánh Giá Chất Lượng Tiêu Đề và Ngữ Nghĩa Tin Đăng (Cells 09–10)

- **Cell 09 (Markdown):** Quy tắc chất lượng tiêu đề và ngữ nghĩa tin đăng.
- **Cell 10 (Code):**
  - Đánh giá `title_quality_status`:
    - `USABLE`: Độ dài tiêu đề $\ge 5$ ký tự.
    - `TOO_SHORT`: Độ dài tiêu đề $< 5$ ký tự.
    - `MISSING`: Tiêu đề bị null hoặc toàn khoảng trắng.
  - Gọi hàm `apply_listing_semantics`:
    - Phân loại `listing_intent`: `RENT` (thuê), `SALE` (bán), `TRANSFER` (sang nhượng), `UNKNOWN` (chưa rõ).
    - Phân loại `rental_scope`: `SINGLE_OR_ORDINARY_UNIT` (phòng/căn hộ đơn lẻ), `WHOLE_BUILDING` (nguyên tòa), `MULTI_UNIT_BUSINESS` (kinh doanh nhiều phòng trọ/dãy trọ), `UNKNOWN`.
    - Gắn kèm chuỗi bằng chứng và lý do phân loại.

---

### Phần 05: Chuẩn Hóa và Phân Tích Cú Pháp Địa Chỉ (Cells 11–12)

- **Cell 11 (Markdown):** Quy tắc trích xuất phân cấp địa chỉ.
- **Cell 12 (Code):**
  - Gọi hàm `apply_address_parsing`:
    - Bóc tách ra `street_text_extracted` (đường), `ward_text_extracted` (phường), `district_text_extracted` (quận), `province_text_extracted` (tỉnh/thành phố).
    - Xác định `parse_status`: `PARSED`, `FALLBACK_PARSED`, `UNPARSED`.
  - Hiển thị độ bao phủ các thành phần địa chỉ trước và sau khi bóc tách.

---

### Phần 06: Ánh Xạ Đơn Vị Hành Chính (Cells 13–14)

- **Cell 13 (Markdown):** Quy tắc chuẩn hóa phường và quận.
- **Cell 14 (Code):**
  - Gọi hàm `apply_ward_mapping`:
    - Chuẩn hóa tên phường (`ward_normalized`) theo danh mục hành chính chính thức của TP.HCM.
    - Ánh xạ các đơn vị hành chính cũ về đơn vị hành chính hiện tại (`ward_current`), đặc biệt là việc sáp nhập Quận 2, Quận 9 và Quận Thủ Đức thành TP. Thủ Đức năm 2021.
    - Xác định `ward_mapping_status`: `EXACT`, `FUZZY`, `HISTORIC`, `AMBIGUOUS`, `UNRESOLVED`.
  - Hiển thị bảng phân bố trạng thái ánh xạ phường.

---

### Phần 07: Xác Thực Giá và Tăng Cường Độ Tin Cậy Mục Tiêu (Cells 15–16)

- **Cell 15 (Markdown):** Hợp đồng dòng dõi và độ tin cậy của giá.
- **Cell 16 (Code):**
  - Gọi `validate_numeric_candidates` trên bằng chứng giá thô:
    - Đối chiếu giá trị `price_amount` trong DB với chuỗi thô `price_raw` cào được.
    - Chạy bộ bóc tách regex độc lập `parse_rental_price_evidence`.
    - Phân loại mức độ đồng thuận giữa 2 bộ parser trong `price_parser_comparison_status`: `MATCH`, `DISAGREEMENT`, `REPARSED_ONLY`, `EXISTING_ONLY`, `NO_PRICE_EVIDENCE`, `UNCOMPARABLE`.
  - Đánh giá độ tin cậy mục tiêu thông qua `evaluate_price_target_trust`:
    - Gán nhãn `price_target_trust_status`:
      - `TRUSTED_EXISTING`: Giá crawler sẵn có khớp hoàn toàn với giá bóc tách từ chuỗi thô.
      - `TRUSTED_REPARSED`: Giá crawler bị thiếu hoặc lỗi, nhưng giá bóc tách từ chuỗi thô đạt chuẩn sạch và cùng dòng dõi.
      - `PARSER_DISAGREEMENT_REVIEW`: Hai parser bất đồng giá trị; cần đánh giá lại.
      - `SUSPECT_UNIT_SCALE`: Đơn vị tiền tệ bị nghi vấn (ví dụ tiền tỷ cho phòng trọ đơn lẻ).
      - `INSUFFICIENT_EVIDENCE`: Thiếu chuỗi văn bản giá thô để kiểm chứng.
      - `MISSING`: Giá hoàn toàn không tồn tại.
    - Gán giá trị mục tiêu vào `price_model_value`: **Chỉ giữ giá trị số cho các dòng đạt chuẩn tin cậy** (`TRUSTED_EXISTING` và `TRUSTED_REPARSED`), gán `np.nan` cho các dòng bị nghi vấn hoặc bất đồng.

> Debug note: `price_model_value` được gán thành `NaN` đối với các dòng có trạng thái `PARSER_DISAGREEMENT_REVIEW` hoặc `SUSPECT_UNIT_SCALE`. Giá trị số làm sạch vẫn được giữ nguyên trong cột `price_amount_clean` để phục vụ kiểm toán, nhưng `price_model_value` bảo đảm rằng các mô hình học máy phía sau không bao giờ bị huấn luyện trên các mức giá còn tranh chấp.

---

### Phần 08: Xác Thực Diện Tích (Cells 17–18)

- **Cell 17 (Markdown):** Quy tắc xác thực diện tích.
- **Cell 18 (Code):**
  - Gọi hàm `validate_numeric_candidates` trên chuỗi diện tích thô (`area_raw`).
  - Gán các cột `area_value_clean`, `area_quality_status`, `area_lineage_aligned`, và `area_regression_status`.
  - Hiển thị bảng báo cáo kiểm toán diện tích.

---

### Phần 09: Cờ Báo Ngoại Lai Số Học (Cells 19–20)

- **Cell 19 (Markdown):** Định nghĩa ngoại lai thống kê.
- **Cell 20 (Code):**
  - Tính toán ngưỡng 1.5 x IQR cho `price_amount_clean` và `area_value_clean`.
  - Gán cờ `price_outlier_flag` và `area_outlier_flag`.
  - Gán nhãn tổng hợp `numeric_outlier_status`:
    - `NOT_OUTLIER`, `PRICE_OUTLIER`, `AREA_OUTLIER`, `PRICE_AND_AREA_OUTLIER`.

---

### Phần 10: Phân Loại Độ Tin Cậy Của Tọa Độ (Cells 21–22)

- **Cell 21 (Markdown):** Tọa độ địa lý và thuật toán phát hiện điểm nóng (hotspot).
- **Cell 22 (Code):**
  - Gọi hàm `audit_coordinate_trust`:
    - Kiểm tra tọa độ số hữu hạn trong phạm vi TP.HCM: khác 0, vĩ độ -90..90, kinh độ -180..180.
    - Xác nhận nhà cung cấp tin cậy: `map_provider == 'google_maps_embed'`.
    - Phát hiện điểm nóng nghi vấn: làm tròn tọa độ đến 6 chữ số thập phân và đếm số lượng địa chỉ đường phố duy nhất gắn với điểm đó.
    - Nhận diện các điểm mà hàng trăm địa chỉ khác nhau cùng trỏ về (`SHARED_POINT_CONFLICTING_ADDRESSES`).
    - Gán `has_trusted_coordinate = True` chỉ khi tọa độ hợp lệ, nhà cung cấp tin cậy, và địa chỉ nhất quán.
    - Gán nhãn `coordinate_quality_status`: `USABLE`, `INVALID`, `UNTRUSTED`.

---

### Phần 11: Tính Nhất Quán Giữa Các Trường — Giá x Diện Tích (Cells 23–24)

- **Cell 23 (Markdown):** Tính khả dụng và đơn giá phòng thuê.
- **Cell 24 (Code):**
  - Gán `price_area_availability_status`: `AVAILABLE`, `MISSING_PRICE`, `MISSING_AREA`, `MISSING_BOTH`.
  - Tính đơn giá `price_per_area = price / area`.
  - Kiểm tra ngoại lai 1.5 x IQR trên đơn giá.
  - Gán nhãn `price_area_quality_status`: `CHECKED_NO_FLAG`, `PRICE_OUTLIER_REVIEW`, `AREA_OUTLIER_REVIEW`, `BOTH_OUTLIERS_REVIEW`, `EXTREME_PRICE_PER_AREA_REVIEW`, `INSUFFICIENT_DATA`.

---

### Phần 12: Gom Cụm Tin Đăng Lặp Lại / Repost (Cells 25–26)

- **Cell 25 (Markdown):** Kiến trúc gom cụm và chống trùng lặp.
- **Cell 26 (Code):**
  - Hiện thực thuật toán Disjoint-Set Union (Union-Find) dựa trên 3 quy tắc chặn (blocking rules):
    1. Dấu vân tay chính xác (Exact Fingerprint): `title_clean` + `best_address_text_clean` + `price_amount_clean` + `area_value_clean`.
    2. Cùng Địa chỉ + Giá + Diện tích giữa các nguồn: `best_address_text_clean` + `price_amount_clean` + `area_value_clean`.
    3. Cùng Tiêu đề + Giá + Phường giữa các nguồn: `title_clean` + `price_amount_clean` + `ward_current`.
  - Gán định danh thành phần liên thông vào `duplicate_candidate_group` (`CANDIDATE:<sha256_hash>`).
  - Gán lý do trùng lặp `duplicate_match_reason`: `EXACT_FINGERPRINT`, `SAME_ADDRESS_PRICE_AREA`, `SAME_TITLE_PRICE_WARD`, `NO_MATCH`.
  - Gán phạm vi trùng lặp `duplicate_scope`: `SAME_SOURCE`, `CROSS_SOURCE`, `NOT_APPLICABLE`.
  - Gán trạng thái `duplicate_candidate_status`: `UNIQUE_FINGERPRINT`, `POSSIBLE_DUPLICATE`, `INSUFFICIENT_DATA`.

> Debug note: Thuật toán Union-Find sẽ hợp nhất các tin đăng nếu chúng thỏa mãn *bất kỳ* quy tắc nào trong 3 quy tắc trên. Nếu tin A trùng địa chỉ/giá với tin B, và tin B trùng tiêu đề/giá/phường với tin C, thì cả 3 tin A, B, C sẽ được gom chung vào một nhóm `CANDIDATE:<hash>`. Cơ chế này bảo đảm việc cô lập nhóm triệt để khi chia tập huấn luyện mô hình.

---

### Phần 13: Xác Thực Ngữ Nghĩa Thời Gian (Cells 27–28)

- **Cell 27 (Markdown):** Logic kiểm tra tính toàn vẹn thời gian.
- **Cell 28 (Code):**
  - Kiểm toán các mốc thời gian: `first_observed_at`, `latest_observed_at`, `last_observed_at`.
  - Gán `temporal_quality_status`:
    - `VALID`: `first <= latest <= last`.
    - `REQUIRES_REVIEW`: Bất kỳ sự đảo ngược thứ tự thời gian nào.
    - `INSUFFICIENT_DATA`: Khi thiếu một trong các mốc thời gian.

---

### Phần 14: Trạng Thái Chất Lượng Dòng Tổng Hợp (Cells 29–30)

- **Cell 29 (Markdown):** Phân loại sức khỏe bản ghi tổng hợp.
- **Cell 30 (Code):**
  - Gán `row_quality_status`:
    - `REQUIRES_REVIEW`: Nếu tiêu đề không dùng được, chuỗi thời gian không hợp lệ, hoặc ánh xạ phường bị mơ hồ (ambiguous).
    - `READY_WITH_FLAGS`: Nếu dòng có cờ ngoại lai, cờ trùng lặp, tọa độ chưa tin cậy, hai parser giá bất đồng, hoặc dòng dõi chưa đối chiếu xong.
    - `READY`: Dòng dữ liệu hoàn hảo, vượt qua tất cả các bài kiểm tra mà không bị bất kỳ cờ cảnh báo nào.
  - Hiển thị phân bố chất lượng dòng tổng thể.

---

### Phần 15: Hợp Đồng Dataset Silver và Ví Dụ Dòng Dõi (Cells 31–32)

- **Cell 31 (Markdown):** Cấu trúc hợp đồng và phân nhóm các trường.
- **Cell 32 (Code):**
  - Kiểm tra phân nhóm cột (20 trường thô, 5 trường văn bản sạch, 6 trường ngữ nghĩa, 9 trường địa chỉ/vị trí, 14 trường giá, 4 trường diện tích, 6 trường tọa độ, 6 trường trùng lặp, 1 trường thời gian).
  - Trực quan hóa các ví dụ cụ thể về dòng dõi chuyển đổi từ dữ liệu thô sang dữ liệu Silver.

---

### Phần 16: Cổng Kiểm Soát Chất Lượng Tiền Silver (Cells 33–34)

- **Cell 33 (Markdown):** Yêu cầu của cổng kiểm soát chất lượng.
- **Cell 34 (Code):**
  - Gọi hàm `evaluate_pre_silver_quality_gate(bronze_df, silver_df)`.
  - Khẳng định 10 bất biến bắt buộc:
    1. `row_count_preserved`: Chính xác 132.436 dòng.
    2. `rental_post_id_non_null`: Không có khóa chính nào bị null.
    3. `rental_post_id_unique`: Chính xác 132.436 khóa duy nhất.
    4. `source_identity_preserved`: `source_code` khớp hoàn toàn với Bronze.
    5. `raw_source_fields_unchanged`: Sự tương đồng tuyệt đối giữa các cột thô trong Silver và Bronze.
    6. `no_row_multiplication_or_deletion`: Danh sách khóa chính khớp từng phần tử.
    7. `allowed_statuses_documented`: Toàn bộ giá trị trạng thái thuộc về các enum đã định nghĩa.
    8. `no_unhandled_null_in_clean_status`: Các trường trạng thái chất lượng không có giá trị null.
    9. `coordinate_truth_preserved`: Định nghĩa tọa độ hợp lệ được tôn trọng.
    10. `price_target_trust_fields_present`: Các cột tin cậy giá mục tiêu được điền đầy đủ.
  - Hiển thị bảng kết quả kiểm tra 10 điểm của cổng kiểm soát.

---

### Phần 17: Lưu Trữ Dataset Silver Chuẩn Hóa (Cells 35–36)

- **Cell 35 (Markdown):** Hướng dẫn xuất dữ liệu Parquet.
- **Cell 36 (Code):**
  - Chạy lệnh xác thực: `assert quality_gate.passed`.
  - Sử dụng DuckDB memory-registration để xuất trực tiếp `silver_df` ra file `data/silver/rental_listings.parquet`.
  - Ghi file `rental_listings.metadata.json` chứa phiên bản lược đồ 2.1.0, số dòng, danh mục cột, nhãn thời gian và hash snapshot Bronze.

---

### Phần 18: Thẩm Định Cuối Cùng và Báo Cáo Sức Khỏe Silver (Cells 37–38)

- **Cell 37 (Markdown):** Tổng quan kiểm tra sau khi ghi đĩa.
- **Cell 38 (Code):**
  - Thực thi các câu lệnh SQL DuckDB trực tiếp lên file Parquet vừa ghi trên đĩa để kiểm tra khả năng đọc và độ tuân thủ lược đồ.
  - Xác nhận lại số dòng (132.436), số cột (80) và tính duy nhất của khóa chính trực tiếp từ file Parquet.

---

## 4. Giải Thích Chi Tiết Các Module Tiện Ích

- `notebooks/utils/silver_processing.py`:
  - Chứa `build_silver_dataset` và `evaluate_pre_silver_quality_gate`.
  - Hiện thực thuật toán Union-Find (`find`, `union`) để gom cụm tin trùng lặp.
- `notebooks/utils/price_area_validation.py`:
  - Chứa `evaluate_price_target_trust` và `parse_rental_price_evidence`.
  - Hiện thực cây quyết định đa tầng phân biệt giữa giá thuê theo tháng và tiền đặt cọc, phí dịch vụ, voucher giảm giá, hoặc giá thuê theo ngày/giờ.
- `notebooks/utils/listing_semantics.py`:
  - Hiện thực các quy tắc Regex tất định cho `listing_intent` và `rental_scope`.
  - Bảo toàn dấu tiếng Việt để phân biệt "bán" với "ban công", hỗ trợ casefold an toàn.
- `notebooks/utils/location_analysis.py`:
  - Hiện thực `audit_coordinate_trust` và thuật toán phát hiện điểm nóng mặc định.

---

## 5. Cẩm Nang Debug Dành Cho Lập Trình Viên

### Cách Tái Tạo Lại Canonical Silver
1. Mở và chạy toàn bộ Notebook 02:
   - Kernel: Python 3.12 (venv).
   - Thời gian thực thi: ~30–45 giây.
2. Kiểm tra các file đầu ra:
   ```bash
   ls -lh data/silver/rental_listings.parquet data/silver/rental_listings.metadata.json
   ```

### Bảng Kiểm Tra Sự Cố Thường Gặp
- **Nếu `SilverQualityGateError` phát sinh tại Cell 36:**
  - Kiểm tra xem bất biến nào trả về `False` trong `quality_gate.results`.
  - Nếu `raw_source_fields_unchanged` bị `False`, kiểm tra xem có thao tác làm sạch nào vô tình sửa đổi trực tiếp lên cột Bronze thô thay vì tạo cột `_clean` mới hay không.
- **Nếu DuckDB không thể ghi file Parquet:**
  - Kiểm tra dung lượng ổ đĩa và quyền ghi (write permissions) trên thư mục `data/silver/`.
