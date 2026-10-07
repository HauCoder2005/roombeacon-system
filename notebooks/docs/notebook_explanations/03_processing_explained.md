# Notebook 03: Hậu Xử Lý Silver và Hợp Đồng Đặc Trưng — Hướng Dẫn Kỹ Thuật

Tài liệu này cung cấp hướng dẫn kỹ thuật chi tiết theo từng cell và cẩm nang debug cho `notebooks/03_roombeacon_processing.ipynb`.

---

## 1. Tổng Quan và Vai Trò Kiến Trúc

`03_roombeacon_processing.ipynb` đóng vai trò là **ranh giới hợp đồng mã hóa (programmatic contract boundary)** giữa tầng kỹ thuật dữ liệu (Silver) và tầng benchmark học máy (Notebook 04).

### Các Bất Biến Kiến Trúc Cốt Lõi:
1. **Tiêu Thụ Trực Tiếp Silver Chuẩn:**
   - Đọc trực tiếp file `data/silver/rental_listings.parquet` mà không làm thay đổi nội dung file.
2. **Thiết Kế Không Phân Chia Tập (Split-Free Design):**
   - Notebook này **không** phân chia dữ liệu thành các tập train, validation, hoặc test. Quyền phân chia theo nhóm và thời gian hoàn toàn thuộc về Notebook 04.
3. **Không Lưu Trữ Dataset Dư Thừa:**
   - Tuyệt đối không tạo thêm file `model_data.parquet` lưu trên đĩa. Việc lưu trữ nhiều bản dataset trung gian sẽ dẫn đến tình trạng lệch lược đồ và lãng phí dung lượng.
4. **Rào Chắn Chống Rò Rỉ Bằng Mã Lệnh (Anti-Leakage Guard):**
   - Định nghĩa chính thức các tập đặc trưng an toàn (F1 đến F5) và chứng minh bằng lệnh kiểm tra tự động rằng các trường phái sinh từ mục tiêu không thể xâm nhập vào danh mục đặc trưng.

---

## 2. Thông Số Đầu Vào và Đầu Ra

- **Đầu vào:** `data/silver/rental_listings.parquet` (132.436 dòng, 80 cột)
- **Đầu ra:** Hợp đồng đặc trưng trong bộ nhớ, các bảng tổng kết chẩn đoán và các câu lệnh xác nhận tính an toàn. Không tạo thêm file trung gian trên đĩa.

---

## 3. Hướng Dẫn Chi Tiết Từng Cell

### Cell 00: Tổng Quan (Markdown)
Giải thích mục đích của notebook: xây dựng các đặc trưng phân tích hậu Silver, tạo biến chẩn đoán, và thẩm định tính an toàn của hợp đồng đặc trưng mà không chia tập hay lưu dataset dư thừa.

### Cell 01: Khởi Tạo Môi Trường và Import Tiện Ích (Code)
- Xác định đường dẫn thư mục gốc `PROJECT_ROOT` thông qua việc tìm kiếm thư mục chứa `crawler/` và `analytics/`.
- Đưa `PROJECT_ROOT` vào `sys.path`.
- Nạp các biến môi trường từ `.env` bằng `python-dotenv`.
- Import:
  - `resolve_runtime_path` từ `analytics.duckdb.connection`
  - Cấu hình `env` từ `roombeacon_crawler.config.get_env`
  - `haversine_distance_km` từ `notebooks.utils.location_analysis`
  - Các hằng số và hàm hỗ trợ từ `notebooks.utils.modeling_benchmark`:
    - `TARGET = "price_model_value"`
    - `FORBIDDEN_PREDICTORS` (tập hợp các trường gây rò rỉ dữ liệu hoặc tái tạo mục tiêu)
    - `audit_features(features)` (hàm kiểm toán danh sách đặc trưng)
    - `build_feature_sets(columns)` (hàm tạo các tập đặc trưng F1–F5)
- Thiết lập tùy chọn hiển thị của pandas và `SEED = 42`.

### Cell 02: Tiêu Đề Mục 01 (Markdown)
Tiêu đề: `## 01 Load Canonical Silver`

### Cell 03: Nạp Silver Parquet Chuẩn (Code)
- Xác định đường dẫn: `SILVER_PATH = resolve_runtime_path(env.processing.silver_dir) / 'rental_listings.parquet'`.
- Kiểm tra file tồn tại: `assert SILVER_PATH.exists()`.
- Đọc dữ liệu Parquet vào `silver_df` bằng DuckDB kết nối trong bộ nhớ:
  ```python
  with duckdb.connect(':memory:') as con:
      silver_df = con.execute('select * from read_parquet(?)', [str(SILVER_PATH)]).df()
  ```
- Kiểm tra các bất biến khóa chính:
  ```python
  assert len(silver_df) > 0
  assert silver_df.rental_post_id.notna().all()
  assert silver_df.rental_post_id.is_unique
  ```
- Hiển thị bảng tóm tắt: đường dẫn, số dòng (132.436) và số cột (80).

### Cell 04: Tiêu Đề Mục 02 (Markdown)
Tiêu đề: `## 02 Analytical eligibility and diagnostic-only variables`

### Cell 05: Tính Đủ Điều Kiện Phân Tích và Biến Chẩn Đoán (Code)
- Tạo bản sao: `processed_df = silver_df.copy()`.
- Thiết lập các mặt nạ boolean điều kiện cơ bản:
  - `analytical_price_eligible`: `processed_df[TARGET].notna()`.
  - `analytical_area_eligible`: `processed_df.area_value_clean.notna()`.
  - `model_base_eligible`: `analytical_price_eligible & analytical_area_eligible & (row_quality_status != 'REQUIRES_REVIEW')`.
- Tạo chỉ số chẩn đoán nội bộ `price_per_area_analysis`:
  ```python
  price = pd.to_numeric(processed_df[TARGET], errors='coerce')
  area = pd.to_numeric(processed_df.area_value_clean, errors='coerce')
  processed_df['price_per_area_analysis'] = price / area.where(area.gt(0))
  processed_df.loc[~np.isfinite(processed_df.price_per_area_analysis), 'price_per_area_analysis'] = np.nan
  ```
- Hiển thị số dòng thỏa mãn các điều kiện lọc và thống kê mô tả (`describe()`) của `price_per_area_analysis`.
- Cảnh báo rõ ràng rằng `price_per_area_analysis` là **BIẾN PHÁI SINH TỪ MỤC TIÊU / CHỈ DÙNG CHO PHÂN TÍCH** và tuyệt đối bị cấm đưa vào các tập đặc trưng huấn luyện mô hình.

### Cell 06: Tiêu Đề Mục 03 (Markdown)
Tiêu đề: `## 03 Optional trusted spatial diagnostic`

### Cell 07: Tính Toán Khoảng Cách Không Gian Tùy Chọn (Code)
- Khởi tạo `REFERENCE_LOCATION = None`.
- Khởi tạo cột `processed_df['distance_km_analysis'] = np.nan`.
- Nếu cấu hình tọa độ tham chiếu `REFERENCE_LOCATION`:
  - Kiểm tra các khóa bắt buộc `latitude` và `longitude`.
  - Tính `haversine_distance_km` **chỉ trên các dòng có `has_trusted_coordinate == True`**.
- Hiển thị số dòng có tọa độ tin cậy so với số dòng tính được khoảng cách (mặc định là 0 khi `REFERENCE_LOCATION` là `None`).

> Debug note: `REFERENCE_LOCATION` được thiết kế mặc định bằng `None` trong file mẫu. Đây là điểm móc nối (hook) cho lập trình viên thử nghiệm tính khoảng cách khi phân tích cục bộ. Biến này không ảnh hưởng đến pipeline huấn luyện mô hình.

### Cell 08: Tiêu Đề Mục 04 (Markdown)
Tiêu đề: `## 04 Safe feature contract`

### Cell 09: Định Nghĩa Hợp Đồng Đặc Trưng và Kiểm Tra Rò Rỉ (Code)
- Tạo `contract_frame` bổ sung đặc trưng độ dài tiêu đề:
  ```python
  contract_frame = processed_df.assign(
      title_length=processed_df.title_clean.astype('string').str.len().astype('Float64')
  )
  ```
- Khởi tạo các tập đặc trưng qua hàm `SAFE_FEATURE_SETS = build_feature_sets(contract_frame.columns)`:
  - `F1 — AREA ONLY`: `['area_value_clean']`
  - `F2 — AREA + SOURCE`: `['area_value_clean', 'source_code']`
  - `F3 — AREA + LOCATION`: `['area_value_clean', 'ward_current', 'district_text_extracted']`
  - `F4 — AREA + SOURCE + LOCATION`: `['area_value_clean', 'source_code', 'ward_current', 'district_text_extracted']`
  - `F5 — FULL SAFE TABULAR`: `['area_value_clean', 'source_code', 'ward_current', 'district_text_extracted', 'province_text_extracted', 'title_length']`
- Kiểm toán từng tập đặc trưng bằng hàm `audit_features(features)`.
- **Kiểm tra rò rỉ chủ động (Negative Test):** Xác nhận rằng việc cố tình thêm các trường bị cấm sẽ kích hoạt ngoại lệ `ValueError`:
  ```python
  for forbidden in ['price_per_area_analysis', TARGET, 'price_amount', 'rental_post_id', 'duplicate_candidate_group']:
      try:
          audit_features(['area_value_clean', forbidden])
      except ValueError:
          pass
      else:
          raise AssertionError(f'Leakage guard failed for {forbidden}')
  ```
- Hiển thị bảng hợp đồng đặc trưng và tóm tắt hợp đồng.
- Khẳng định không có cột phân chia tập dữ liệu trong DataFrame:
  ```python
  assert 'dataset_split' not in processed_df.columns
  ```

### Cell 10: Tiêu Đề Mục 05 (Markdown)
Tiêu đề: `## 05 Processing Summary`

### Cell 11: Tổng Kết Quá Trình Hậu Xử Lý (Code)
- Tạo series báo cáo tóm tắt:
  - `silver_input_rows`: 132.436
  - `analytical_rows`: 132.436
  - `model_base_eligible_rows`: ~117k–118k
  - `safe_feature_sets`: 5
  - `legacy_split_columns`: 0
  - `persisted_redundant_model_dataset`: False
- Xác nhận số dòng được bảo toàn: `assert len(processed_df) == len(silver_df)`.
- Hiển thị thông báo xác nhận rằng các công việc chia tập, lựa chọn thuật toán, tinh chỉnh siêu tham số và đánh giá tập TEST hoàn toàn thuộc về Notebook 04.

---

## 4. Chi Tiết Kỹ Thuật: Triển Khai Hợp Đồng Đặc Trưng

Trong file `notebooks/utils/modeling_benchmark.py`:
- Danh sách `FORBIDDEN_PREDICTORS` bao gồm:
  - `price_model_value`, `price_target_model_value`, `price_target_trust_status`, `price_target_trust_reason`, `price_target_trust_evidence`
  - `price_amount_clean`, `price_amount`, `price_raw`, `price_reparsed`, `reparsed_price`, `target`, `target_price`
  - `price_per_area`, `price_per_area_analysis`, `price_per_area_audit`
  - `rental_post_id`, `source_listing_id`, `duplicate_candidate_group`, `group_key`
- Hàm `audit_features(features)`:
  - So khớp xem có đặc trưng nào thuộc `FORBIDDEN_PREDICTORS` không.
  - Tự động kiểm tra xem có trường nào bắt đầu bằng `price_` hoặc kết thúc bằng `_price` không.
  - Báo lỗi `ValueError("Forbidden/leaking predictors: ...")` nếu phát hiện vi phạm.

---

## 5. Cẩm Nang Debug Dành Cho Lập Trình Viên

### Cách Chạy Notebook 03
1. Đảm bảo file `data/silver/rental_listings.parquet` đã tồn tại (được sinh ra từ Notebook 02).
2. Chạy notebook tuần tự từ đầu đến cuối. Thời gian thực thi thường $< 5$ giây.

### Xử Lý Sự Cố Thường Gặp
- **Nếu `SILVER_PATH.exists()` báo lỗi:**
  - Chạy Notebook 02 để tạo Canonical Silver Parquet.
- **Nếu assertion `Leakage guard failed` kích hoạt:**
  - Kiểm tra xem file `notebooks/utils/modeling_benchmark.py` có bị ai chỉnh sửa xóa nhầm các trường trong `FORBIDDEN_PREDICTORS` hay không.
- **Nếu `build_feature_sets` báo `ValueError: Canonical Silver is missing benchmark fields`:**
  - Kiểm tra các cột trong `silver_df`. Đảm bảo các cột `area_value_clean`, `source_code`, `ward_current`, `district_text_extracted`, và `province_text_extracted` đều tồn tại đầy đủ.
