# Notebook 05: Tìm Kiếm Phòng Thuê Lân Cận và Thu Hồi Không Gian — Hướng Dẫn Kỹ Thuật

Tài liệu này cung cấp hướng dẫn kỹ thuật chi tiết theo từng cell và cẩm nang debug cho `notebooks/05_roombeacon_nearby_rental_search.ipynb`.

---

## 1. Tổng Quan và Vai Trò Kiến Trúc

`05_roombeacon_nearby_rental_search.ipynb` hiện thực **tầng thu hồi không gian và thẩm định sản phẩm** của RoomBeacon. Notebook này trả lời câu hỏi cốt lõi từ góc nhìn người dùng thực tế:
> *"RoomBeacon có thể giúp người dùng tìm kiếm các phòng cho thuê đáng tin cậy ở gần một địa điểm họ quan tâm hay không?"*

### Các Bất Biến Kiến Trúc Cốt Lõi:
1. **Tiêu Thụ Trực Tiếp Canonical Silver Parquet:**
   - Đọc trực tiếp file `data/silver/rental_listings.parquet` mà không làm thay đổi Silver và không phụ thuộc vào tầng Bronze thô.
2. **Tuyệt Đối Không Làm Giả Khoảng Cách Địa Lý:**
   - Khoảng cách Haversine vector hóa (`distance_km`) được tính **duy nhất khi cả điểm tham chiếu và tin đăng đều có tọa độ hợp lệ và đáng tin cậy** (`has_trusted_coordinate == True`).
   - Nếu tọa độ bị thiếu, bằng 0, không hợp lệ, hoặc nằm tại điểm mặc định chung của cổng thông tin, khoảng cách bắt buộc phải là `NaN` / `None`.
3. **Phân Loại Vị Trí 5 Trạng Thái Nghiêm Ngặt:**
   - Tách biệt rành mạch giữa năng lực tìm kiếm và kết quả thu hồi, phân biệt rõ tin thực sự không xác định được vị trí với tin nằm ngoài khu vực tìm kiếm:
     - `EXACT_DISTANCE_CAPABLE`: Có tọa độ tin cậy để tính khoảng cách chính xác (chiếm 1,72% tin cho thuê, 2.268 dòng).
     - `SAME_WARD`: Tọa độ không tin cậy, nhưng trùng phường tham chiếu (khoảng cách bắt buộc null; 6,88%, 9.083 dòng).
     - `SAME_DISTRICT`: Tọa độ không tin cậy, khác phường nhưng trùng quận tham chiếu (khoảng cách bắt buộc null; 2,56%, 3.382 dòng).
     - `RESOLVED_OUTSIDE_REFERENCE_AREA`: Đã xác định được phường/quận nhưng nằm ngoài khu vực tham chiếu (76,72%, 101.230 dòng).
     - `LOCATION_UNRESOLVED`: Hoàn toàn không thể xác định vị trí (không có tọa độ, không có phường, không có quận; 12,11%, 15.978 dòng).
4. **Hợp Đồng Điểm Tham Chiếu Minh Bạch:**
   - Đánh giá thông tin điểm tham chiếu và gán nhãn trung thực `USER_SUPPLIED_UNVERIFIED` (người dùng cung cấp, chưa kiểm thực GIS) thay vì gọi API geocoding bên ngoài giả tạo.
5. **Xếp Hạng Tìm Kiếm Đa Tầng Tất Định:**
   - Sắp xếp kết quả dựa trên trạng thái chất lượng tọa độ (`TRUSTED_CONSISTENT` $\rightarrow$ `TRUSTED_ADMIN_UNVERIFIED` $\rightarrow$ `TRUSTED_BUT_ADMIN_MISMATCH`), tiếp theo là khoảng cách tăng dần, mức độ tin cậy của giá, giá tăng dần, và độ mới giảm dần.
6. **Chính Sách Hiển Thị Giá Tùy Biến Được:**
   - Mặc định ở chế độ `TRUSTED_ONLY` (chỉ hiển thị giá số cho các tin có giá đạt chuẩn tin cậy) nhằm bảo đảm giá chưa xác thực không lọt vào kết quả hiển thị cho người dùng.

---

## 2. Thông Số Đầu Vào và Đầu Ra

- **Đầu vào:** `data/silver/rental_listings.parquet` (132.436 dòng, 80 cột)
- **Thư mục lưu trữ đầu ra:** `data/analysis/nearby_search/`
  - `location_quality_summary.csv`: Thống kê chất lượng tọa độ và điểm nóng mặc định
  - `search_coverage_funnel.csv`: Phễu chuyển đổi từ 131k tin thuê sang các vành đai khoảng cách
  - `radius_market_summary.csv`: Chẩn đoán giá thuê và diện tích thị trường theo các vành đai bán kính
  - `nearby_search_exact_results.csv`: Danh sách kết quả khoảng cách chính xác được xếp hạng
  - `same_ward_fallback_results.csv`: Kết quả dự phòng hành chính cùng phường
  - `same_district_fallback_results.csv`: Kết quả dự phòng hành chính cùng quận
  - `search_run_metadata.json`: Tham số thực thi, phân bố các trạng thái vị trí và kết luận sẵn sàng

---

## 3. Hướng Dẫn Chi Tiết Từng Cell

### Cell 00: Tổng Quan (Markdown)
Trình bày mục tiêu của nguyên mẫu tìm kiếm, giải quyết bài toán trải nghiệm người dùng, và định nghĩa 6 bất biến kiến trúc cốt lõi.

### Cell 01: Tiêu Đề Mục 1 (Markdown)
Tiêu đề: `## 1. Environment Setup & Helper Imports`

### Cell 02: Khởi Tạo Môi Trường và Import Tiện Ích (Code)
- Xác định `PROJECT_ROOT` và thêm vào `sys.path`.
- Import các thư viện phân tích: `duckdb`, `pandas`, `numpy`, `matplotlib.pyplot`, `seaborn`.
- Import các hàm chuyên biệt từ `notebooks.utils.nearby_rental_search`:
  - `is_valid_coordinate`, `haversine_distance_km`, `assign_distance_band`
  - `filter_rental_compatible`, `derive_display_price`
  - `create_reference_location_contract`, `classify_coordinate_search_status`
  - `audit_location_coverage`, `execute_nearby_rental_search`
  - `build_search_funnel`, `summarize_radius_market`, `evaluate_product_readiness`
- Cấu hình hiển thị số thực của pandas: hiển thị 2 chữ số thập phân cho số nhỏ và định dạng dấu phẩy hàng nghìn cho số lớn.

### Cell 03: Tiêu Đề Mục 2 (Markdown)
Tiêu đề: `## 2. Search Configuration`

### Cell 04: Cấu Hình Tham Số Tìm Kiếm (Code)
- Thiết lập điểm tìm kiếm tham chiếu:
  ```python
  REFERENCE_NAME = "Đại học Bách Khoa TP.HCM (Campus Lý Thường Kiệt, Q.10)"
  REFERENCE_LATITUDE = 10.7725
  REFERENCE_LONGITUDE = 106.6578
  REFERENCE_WARD = "Phường Tân Bình"
  REFERENCE_DISTRICT = "Quận 10"
  SEARCH_RADIUS_KM = 3.0
  MAX_RESULTS = 20
  PRICE_DISPLAY_POLICY = "TRUSTED_ONLY"
  MIN_PRICE = None
  MAX_PRICE = 10_000_000.0  # Lọc tùy chọn: <= 10 triệu/tháng
  MIN_AREA = 15.0           # Lọc tùy chọn: >= 15 m²
  MAX_AREA = None
  ```
- Hiển thị bảng tóm tắt cấu hình `config_summary`.

> Debug note: `REFERENCE_WARD = "Phường Tân Bình"` tương ứng với quy chuẩn ánh xạ phường của Silver cho khu vực campus Bách Khoa giáp ranh Quận 10 và Tân Bình. Việc thay đổi `REFERENCE_WARD` hoặc `REFERENCE_DISTRICT` chỉ ảnh hưởng đến tập kết quả dự phòng hành chính (Tier 2, Tier 3), hoàn toàn không làm thay đổi kết quả tính khoảng cách theo bán kính (Tier 1).

### Cell 05: Tiêu Đề Mục 3 (Markdown)
Tiêu đề: `## 3. Load Canonical Silver Parquet`

### Cell 06: Nạp và Kiểm Thẩm Định File Parquet (Code)
- Xác định đường dẫn: `SILVER_PATH = resolve_runtime_path(env.processing.silver_dir) / 'rental_listings.parquet'`.
- Đọc file Parquet vào `silver_df` bằng DuckDB.
- Kiểm tra các bất biến dữ liệu động:
  ```python
  assert len(silver_df) > 0
  assert 'rental_post_id' in silver_df.columns
  assert silver_df['rental_post_id'].notna().all()
  assert silver_df['rental_post_id'].is_unique
  ```
- Hiển thị đường dẫn, tổng số dòng (132.436) và số cột (80).

### Cell 07: Tiêu Đề Mục 4 (Markdown)
Tiêu đề: `## 4. Rental Search Population Eligibility & Price Policy`

### Cell 08: Sàng Lọc Quần Thể Cho Thuê và Áp Dụng Chính Sách Giá (Code)
- Gọi hàm `filter_rental_compatible(silver_df)`:
  - Loại bỏ các tin đăng có ý định bán (`SALE`) hoặc sang nhượng (`TRANSFER`).
  - Loại bỏ các tin cho thuê cả tòa nhà (`WHOLE_BUILDING`, `MULTI_UNIT_BUSINESS`).
  - Giữ lại các tin `UNKNOWN` khi không có bằng chứng trái ngược.
  - Thu được **131.941 tin đăng phù hợp cho thuê** (chiếm 99,63% Silver).
- Gọi hàm `derive_display_price(rental_df, price_display_policy="TRUSTED_ONLY")`:
  - Gán giá hiển thị `display_price` bằng `price_model_value` cho các tin có giá đạt chuẩn tin cậy.
  - Gán `display_price = np.nan` cho các tin có giá đang chờ kiểm duyệt hoặc không tin cậy.
- Hiển thị bảng phân bố chính sách giá:
  - `TRUSTED`: 118.520 tin (89,83%)
  - `REVIEW_EXCLUDED`: 8.368 tin (6,34%)
  - `MISSING`: 4.409 tin (3,34%)
  - `SUSPECT_UNIT_SCALE`: 644 tin (0,49%)

### Cell 09: Tiêu Đề Mục 5 (Markdown)
Tiêu đề: `## 5. Location Quality & Coordinate Coverage Audit`

### Cell 10: Kiểm Toán Độ Phủ Tọa Độ và Chất Lượng Vị Trí (Code)
- Gọi hàm `audit_location_coverage(rental_df)`.
- Các kết quả thực nghiệm quan trọng:
  - Cặp tọa độ hợp lệ: 12.801 tin (9,70%)
  - **Tọa độ tin cậy để tính khoảng cách (`has_trusted_coordinate`): 2.268 tin (1,72%)**
  - **Điểm nóng mặc định nghi vấn (`SHARED_POINT_CONFLICT`): 10.533 tin (7,98%)**
  - Thiếu hoàn toàn tọa độ: 119.140 tin (90,30%)
  - **Đã bóc tách thành công phường (`ward_current`): 110.481 tin (83,74%)**
  - Đã bóc tách thành công quận: 115.963 tin (87,89%)
  - Hoàn toàn không xác định được vị trí: 15.978 tin (12,11%)
- Hiển thị bảng kiểm toán độ phủ vị trí.

### Cell 11: Tiêu Đề Mục 6 (Markdown)
Tiêu đề: `## 6. Reference Location Contract Validation`

### Cell 12: Thiết Lập Hợp Đồng Vị Trí Tham Chiếu (Code)
- Gọi hàm `create_reference_location_contract`:
  - Trạng thái trả về: `USER_SUPPLIED_UNVERIFIED`.
  - Giải thích: Vì dự án không nhúng sẵn các file đa giác GIS (shapefiles) để chứng minh tọa độ nằm trong ranh giới phường, hệ thống ghi nhận trung thực trạng thái này thay vì tạo cuộc gọi mạng ra bên ngoài.
- Hiển thị các trường của hợp đồng tham chiếu.

### Cell 13: Tiêu Đề Mục 7 (Markdown)
Tiêu đề: `## 7. Multi-Tier Nearby Rental Retrieval & Location Taxonomy`

### Cell 14: Thực Thi Động Cơ Tìm Kiếm Đa Tầng (Code)
- Gọi hàm `execute_nearby_rental_search(...)`:
  - Trả về `(exact_results, same_ward_results, same_district_results, search_df)`.
- Hiển thị phân bố 5 trạng thái phân loại vị trí tìm kiếm:
  1. `RESOLVED_OUTSIDE_REFERENCE_AREA`: 101.230 tin (76,72%)
  2. `LOCATION_UNRESOLVED`: 15.978 tin (12,11%)
  3. `SAME_WARD`: 9.083 tin (6,88%)
  4. `SAME_DISTRICT`: 3.382 tin (2,56%)
  5. `EXACT_DISTANCE_CAPABLE`: 2.268 tin (1,72%)
- Hiển thị phân bố chất lượng tìm kiếm tọa độ:
  - `MISSING`: 119.140 (90,30%)
  - `SHARED_POINT_CONFLICT`: 10.533 (7,98%)
  - `TRUSTED_ADMIN_UNVERIFIED`: 1.041 (0,79%)
  - `TRUSTED_BUT_ADMIN_MISMATCH`: 997 (0,76%)
  - `TRUSTED_CONSISTENT`: 230 (0,17%)

### Cell 15: Tiêu Đề Mục 8 (Markdown)
Tiêu đề: `## 8. Search Coverage Funnel`

### Cell 16: Xây Dựng Phễu Thu Hồi Tìm Kiếm (Code)
- Gọi hàm `build_search_funnel(search_df, radius_km=3.0)`.
- Đo lường số lượng tin theo các vành đai khoảng cách chính xác:
  - Bán kính $\le 10$ km: 1.877 tin (82,76% số tin có tọa độ tin cậy)
  - Bán kính $\le 5$ km: 839 tin (36,99%)
  - Bán kính $\le 3$ km: 290 tin (12,79%)
  - Bán kính $\le 1$ km: 32 tin (1,41%)
- Trong phạm vi bán kính 3 km:
  - 80 tin đạt chuẩn `TRUSTED_CONSISTENT` (27,59% số tin trong bán kính)
  - 179 tin là `TRUSTED_ADMIN_UNVERIFIED` (61,72%)
  - 31 tin bị `TRUSTED_BUT_ADMIN_MISMATCH` (10,69%)

### Cell 17: Tiêu Đề Mục 9 (Markdown)
Tiêu đề: `## 9. Ranked Search Results Presentation`

### Cell 18: Hiển Thị Kết Quả Tìm Kiếm Đã Xếp Hạng (Code)
- Lọc các cột cần hiển thị: `rental_post_id`, `source_code`, `title_clean`, `display_price`, `price_display_status`, `area_value_clean`, `ward_current`, `district_text_extracted`, `coordinate_search_status`, `distance_km`, `latest_observed_at`.
- Hiển thị top 20 kết quả Tier 1 (khoảng cách chính xác trong bán kính 3 km, xếp hạng theo độ tin cậy tọa độ rồi đến khoảng cách).
- Hiển thị top 10 kết quả Tier 2 (Dự phòng cùng Phường, xếp theo độ mới và giá).
- Hiển thị top 10 kết quả Tier 3 (Dự phòng cùng Quận, xếp theo độ mới và giá).

### Cell 19: Tiêu Đề Mục 10 (Markdown)
Tiêu đề: `## 10. Concentric Radius Market Analysis (Trusted-Coordinate Subset Only)`

### Cell 20: Chẩn Đoán Thị Trường Theo Vành Đai Bán Kính (Code)
- Gọi hàm `summarize_radius_market(search_df, radii=[1.0, 3.0, 5.0, 10.0])`:
  - $\le 1$ km: 32 tin, Giá trung vị = 4.000.000 VNĐ, Diện tích trung vị = 20 m², Đơn giá trung vị = 193.333 VNĐ/m².
  - $\le 3$ km: 290 tin, Giá trung vị = 4.000.000 VNĐ, Diện tích trung vị = 28 m², Đơn giá trung vị = 166.667 VNĐ/m².
  - $\le 5$ km: 839 tin, Giá trung vị = 4.300.000 VNĐ, Diện tích trung vị = 27,5 m², Đơn giá trung vị = 166.667 VNĐ/m².
  - $\le 10$ km: 1.877 tin, Giá trung vị = 4.000.000 VNĐ, Diện tích trung vị = 28 m², Đơn giá trung vị = 160.000 VNĐ/m².
- Ghi nhận thiên lệch độ sẵn sàng của tọa độ: Mogi và Cafeland chiếm ưu thế áp đảo trong tập có tọa độ tin cậy.

### Cell 21: Tiêu Đề Mục 11 (Markdown)
Tiêu đề: `## 11. Visualizations`

### Cell 22: Biểu Đồ Chẩn Đoán Không Gian (Code)
- Vẽ đồ thị 4 ô (2x2):
  1. Biểu đồ cột: Số lượng tin theo các dải khoảng cách ($\le 1$ km, 1–3 km, 3–5 km, 5–10 km, $> 10$ km).
  2. Biểu đồ đường: Giá thuê trung vị theo các vành đai bán kính xung quanh điểm tham chiếu.
  3. Biểu đồ cột ngang: Các phường có nhiều tin nhất trong bán kính 3 km (Phường Bảy Hiền, Phường Tân Bình).
  4. Biểu đồ phân tán: Kinh độ so với Vĩ độ của các tin lân cận được tô màu theo khoảng cách, điểm tham chiếu được đánh dấu bằng ngôi sao đỏ. Được dán nhãn rõ: *"Biểu đồ phân tán chẩn đoán tọa độ (Không phải bản đồ dẫn đường)"*.

### Cell 23: Mục 12 (Markdown)
Tiêu đề: `## 12. Data Quality Findings & Forensic Limitations`
Tổng kết 4 phát hiện dữ liệu cốt lõi:
1. Rào cản độ phủ tọa độ thực tế (~1,72%).
2. Hiện tượng ghim điểm giả tại tâm quận (>10.500 tin dùng chung tọa độ mặc định).
3. Sai lệch metadata của cổng thông tin (ví dụ tin 69388 ghi đường Lê Thánh Tôn, Quận 1 nhưng tọa độ lại rơi vào Quận 10).
4. Tính vượt trội của phương pháp thu hồi theo đơn vị hành chính (83,74% độ phủ theo phường).

### Cell 24: Tiêu Đề Mục 13 (Markdown)
Tiêu đề: `## 13. Product Readiness & Analytical Artifacts`

### Cell 25: Đánh Giá Tính Sẵn Sàng và Xuất Artifacts (Code)
- Gọi hàm `evaluate_product_readiness(coverage_audit)`:
  - **Kết luận (Verdict):** `ADMIN_FALLBACK_READY` (Sẵn sàng cho mô hình tìm kiếm dự phòng hành chính).
  - **Diễn giải:** Độ phủ tọa độ tin cậy hiện còn hạn chế (1,72%), trong khi độ phủ theo phường hành chính đạt mức cao (83,74%). Nền tảng RoomBeacon hỗ trợ tin cậy việc khám phá theo phân cấp hành chính (Cùng Phường / Cùng Quận), trong khi tính năng tìm kiếm theo bán kính đóng vai trò là một tầng nguyên mẫu có độ chính xác cao nhưng độ bao phủ thấp.
- Tạo thư mục: `data/analysis/nearby_search/`.
- Xuất 6 file CSV và `search_run_metadata.json`.
- Hiển thị thông báo hoàn tất.

---

## 4. Chi Tiết Kỹ Thuật: Động Cơ Tìm Kiếm Không Gian

Trong file `notebooks/utils/nearby_rental_search.py`:
- `is_valid_coordinate(lat, lon)`:
  - Loại bỏ các giá trị null, vô hạn, vượt ngoài dải -90..90 / -180..180 và cặp tọa độ mặc định `(0, 0)`.
- `haversine_distance_km(lat1, lon1, lat2, lon2)`:
  - Tính khoảng cách cung lớn vector hóa với bán kính Trái Đất $R = 6371,0088$ km.
- `classify_coordinate_search_status`:
  - Đối chiếu vị trí tọa độ với tên quận/phường dạng văn bản.
  - Sử dụng đồ thị `HCM_ADJACENT_DISTRICTS` để phân biệt các trường hợp giáp ranh hợp lý so với các mâu thuẫn địa lý rõ rệt (như địa chỉ Quận 1 nhưng tọa độ nằm ở Quận 10).
- `execute_nearby_rental_search`:
  - Chỉ tính khoảng cách cho tin có `has_trusted_coordinate`.
  - Phân tách dữ liệu vào 5 trạng thái phân loại vị trí không gian loại trừ lẫn nhau.
  - Hiện thực thuật toán sắp xếp đa tiêu chí tất định để hiển thị kết quả.

---

## 5. Cẩm Nang Debug Dành Cho Lập Trình Viên

### Cách Chạy Notebook 05
1. Đảm bảo file Canonical Silver Parquet đã tồn tại tại `data/silver/rental_listings.parquet`.
2. Chạy notebook tuần tự từ đầu đến cuối. Thời gian thực thi thường $< 10$ giây.

### Bảng Kiểm Tra Sự Cố Thường Gặp
- **Nếu file `nearby_search_exact_results.csv` rỗng (0 dòng):**
  - Kiểm tra `SEARCH_RADIUS_KM`: Thử tăng bán kính từ 1.0 lên 3.0 hoặc 5.0 km.
  - Kiểm tra bộ lọc giá và diện tích: Đặt `MAX_PRICE = None` và `MIN_AREA = None` để kiểm tra xem bộ lọc có loại bỏ hết ứng viên hay không.
  - Kiểm tra tọa độ tham chiếu: Đảm bảo `REFERENCE_LATITUDE` và `REFERENCE_LONGITUDE` khác 0 và nằm trong địa phận TP.HCM.
- **Nếu tin đăng xuất hiện trong kết quả chính xác với tên phường lạ:**
  - Kiểm tra cột `coordinate_search_status`. Một tin mang trạng thái `TRUSTED_BUT_ADMIN_MISMATCH` có tọa độ thực sự nằm gần điểm tham chiếu, nhưng phần văn bản của người đăng tin lại ghi một quận ở xa. Các tin này tự động bị hạ độ ưu tiên trong thuật toán xếp hạng.
