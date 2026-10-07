# Notebook 04: Benchmark Định Giá Cho Thuê V3 — Hướng Dẫn Kỹ Thuật

Tài liệu này cung cấp hướng dẫn kỹ thuật chi tiết theo từng cell và cẩm nang debug cho `notebooks/04_roombeacon_modeling.ipynb`.

> **Nguồn chân lý hiện tại:** runtime artifact ngày 2026-10-05 khóa
> **LightGBM Regressor / RAW / F4 — AREA + SOURCE + LOCATION** với
> `learning_rate=0.05`, `min_child_samples=30`, `n_estimators=180`,
> `num_leaves=63`, `objective="mae"`. Metadata/artifact runtime là nguồn quyết
> định khi một mô tả lịch sử có sai khác.

---

## 1. Tổng Quan và Vai Trò Kiến Trúc

`04_roombeacon_modeling.ipynb` thực thi **Benchmark Định Giá Cho Thuê V3: Phương Pháp Luận Tăng Cường (Rental Price Benchmark V3: Methodology-Hardened)**. Notebook này giải quyết câu hỏi trọng tâm của học máy:
> *"RoomBeacon có thể dự đoán chính xác giá thuê kỳ vọng của một phòng trọ/căn hộ thông thường chỉ bằng các đặc trưng an toàn, không gây rò rỉ dữ liệu hay không?"*

### Các Nguyên Lý Phương Pháp Luận Cốt Lõi:
1. **Xác Định Rõ Ràng Biến Mục Tiêu Kinh Doanh:**
   - Biến mục tiêu: `price_model_value` (giá thuê hàng tháng tính bằng VNĐ, đã được xác thực và đối chiếu tin cậy).
   - Quần thể không tương thích (tin bán nhà, sang nhượng mặt bằng, cho thuê cả tòa nhà, khu trọ kinh doanh nhiều phòng) được loại bỏ bằng ngữ nghĩa văn bản bảo thủ.
2. **Niêm Phong Tập Kiểm Thử Theo Trình Tự Thời Gian (Sealed Test):**
   - Tập test đại diện cho tương lai (15% nhóm tin đăng được quan sát muộn nhất).
   - Tập test được niêm phong tuyệt đối trong suốt quá trình chọn đặc trưng, so sánh thuật toán, biến đổi mục tiêu và tinh chỉnh siêu tham số. Tập test **chỉ được truy cập đúng 1 lần duy nhất** sau khi đã khóa cố định mô hình chiến thắng.
3. **Cô Lập Nhóm Để Ngăn Ngừa Rò Rỉ Tin Đăng Lặp Lại (Repost Leakage):**
   - Các tin đăng trùng lặp (xác định bởi `duplicate_candidate_group`) được gom thành một nhóm duy nhất. Không có chuyện một tin trong nhóm nằm ở tập train trong khi tin khác cùng nhóm lại nằm ở tập test.
4. **11 Họ Mô Hình Trên 2 Phép Biến Đổi Mục Tiêu:**
   - Đánh giá Linear Regression, Ridge, ElasticNet, Decision Tree, Random Forest, Extra Trees, Gradient Boosting, HistGradientBoosting, XGBoost, LightGBM, và CatBoost.
   - So sánh hai phép biến đổi: `RAW` (giá gốc) và `LOG1P` (logarit tự nhiên của giá + 1).
5. **Khóa Ứng Viên Ưu Tiên Sự Đơn Giản (Parsimony Rule):**
   - Trong số các ứng viên có sai số MAE trên tập phát triển nằm trong phạm vi 1% so với mô hình tốt nhất, mô hình có cấu trúc đơn giản nhất sẽ được chọn.
6. **Lưu Trữ Đầy Đủ Bằng Chứng Thực Nghiệm:**
   - Toàn bộ bảng chỉ số, kết quả từng fold, chẩn đoán phân khúc, dự đoán ngoài mẫu (out-of-sample) và metadata thử nghiệm được lưu trữ tại `data/modeling/roombeacon_price_benchmark_v3/`.

---

## 2. Thông Số Đầu Vào và Đầu Ra

- **Đầu vào:**
  - `data/silver/rental_listings.parquet` (132.436 dòng, 80 cột)
  - `data/silver/rental_listings.metadata.json`
- **Thư mục lưu trữ đầu ra:** `data/modeling/roombeacon_price_benchmark_v3/`
  - 20 file CSV ghi nhận các chỉ số đánh giá và chẩn đoán
  - `test_predictions.parquet` (1,04 MB): Dự đoán ngoài mẫu trên tập kiểm thử niêm phong
  - `experiment_metadata.json`: Môi trường runtime, thông số phần cứng, siêu tham số và kết luận sẵn sàng
  - `champion_model.joblib`, `champion_metadata.json`, `champion_reference_profile.json`: model binary, inference contract và reference DEVELOPMENT cho Notebook 06

---

## 3. Hướng Dẫn Chi Tiết Từng Cell

### Cell 00: Tổng Quan (Markdown)
Định nghĩa benchmark: dự đoán `price_model_value` từ Silver chuẩn chỉ bằng các fold thời gian phát triển. Tập test được niêm phong.

### Cell 01: Tiêu Đề Mục 01 (Markdown)
Tiêu đề: `## 01 Runtime, canonical input, and reproducibility`

### Cell 02: Khởi Tạo Môi Trường, Thư Viện và Nạp Dữ Liệu (Code)
- Nạp các thư viện: `duckdb`, `numpy`, `pandas`, `matplotlib`, `sklearn`, `xgboost`, `lightgbm`, `catboost`.
- Đọc `rental_listings.parquet` vào `silver_df` bằng DuckDB.
- Kiểm tra tính toàn vẹn:
  ```python
  assert len(silver_df) == silver_df.rental_post_id.nunique() == silver_metadata['row_count']
  ```
- Cố định hạt giống ngẫu nhiên: `SEED = 42`.
- Hiển thị bảng phiên bản các thư viện.

> Debug note: `prepare_lightgbm_categories` hiện là helper chính thức. Không chạy lại benchmark chỉ để làm mới output; chỉ chạy lại khi có dependency artifact thật hoặc một thay đổi benchmark được phê duyệt.

### Cell 03: Tiêu Đề Mục 02 (Markdown)
Tiêu đề: `## 02 Business target, semantic population, and leakage contract`

### Cell 04: Lọc Quần Thể Ngữ Nghĩa và Kiểm Toán Rò Rỉ (Code)
- Gọi hàm `engineer_safe_features(silver_df)` (tạo đặc trưng `title_length`).
- Áp dụng 3 điều kiện sàng lọc mục tiêu:
  1. `numeric_candidate`: `price_amount_clean` tồn tại, $> 0$, và không thuộc `MISSING_OR_REVIEW` (128.051 dòng, 96,69%).
  2. `numeric_trusted`: `price_target_trust_status` nằm trong `{'TRUSTED_EXISTING', 'TRUSTED_REPARSED'}` và `price_model_value` tồn tại, $> 0$ (119.223 dòng, 90,02%).
  3. `semantic_compatible`: Đánh giá bởi `semantic_model_eligibility`. Loại bỏ các tin có `listing_intent` là `SALE` hoặc `TRANSFER`, và `rental_scope` là `WHOLE_BUILDING` hoặc `MULTI_UNIT_BUSINESS` (131.356 dòng, 99,18%). Giữ lại các tin `UNKNOWN` khi không có bằng chứng xung đột.
- Quần thể mô hình hóa cuối cùng (`model_df`): Giao của 3 điều kiện: **117.897 dòng** (chiếm 89,02% Silver).
- Gán khóa nhóm thông qua `build_group_key(model_df)`:
  - Dùng `duplicate_candidate_group` nếu có; dùng `rental_post_id` nếu là tin duy nhất.
- Khởi tạo các tập đặc trưng F1–F5 và xác nhận toàn bộ đều vượt qua bài kiểm tra `audit_features`.
- Hiển thị bảng tóm tắt quần thể, phân loại lý do loại trừ, so sánh phân phối giá trước và sau lọc, cùng các ví dụ giá cao hợp lệ.
- Vẽ đồ thị phân phối giá gốc và giá sau khi log1p.

### Cell 05: Tiêu Đề Mục 03 (Markdown)
Tiêu đề: `## 03 Sealed strict group-chronological split`

### Cell 06: Phân Chia Tập Dữ Liệu Theo Nhóm và Thời Gian (Code)
- Gọi hàm `group_aware_split(model_df, model_df.group_key, seed=SEED)`:
  - Sắp xếp toàn bộ các nhóm theo mốc thời gian quan sát lớn nhất đại diện (`latest_observed_at`).
  - Chia nhóm theo tỷ lệ 70% Train, 15% Validation, 15% Test.
  - Các mốc thời gian bị trùng nhau tại ranh giới được đẩy sang phân vùng sau để tránh xé lẻ (`_move_cut_past_ties`).
- Kiểm tra tính cô lập nhóm (`assert_group_isolation`): 0 nhóm nào bị phân tách qua nhiều tập.
- Kiểm tra tính thứ tự thời gian (`assert_split_chronology`): `max(Train) < min(Validation) < min(Test)`.
- Tách thành `development_df` (Train + Validation, 95.731 dòng, 85,30%) và `test_df` (Test, 16.495 dòng, 14,70%).
- Xây dựng 3 fold thời gian mở rộng trên `development_df` bằng `build_expanding_group_time_folds`:
  - Fold 1: Train 51.901 dòng (51.262 nhóm) $\rightarrow$ Val 14.017 dòng (13.981 nhóm)
  - Fold 2: Train 65.918 dòng (65.243 nhóm) $\rightarrow$ Val 14.073 dòng (13.981 nhóm)
  - Fold 3: Train 79.991 dòng (79.224 nhóm) $\rightarrow$ Val 15.740 dòng (13.981 nhóm)
- Gán cờ bảo vệ: `TEST_ACCESSED_FOR_SELECTION = False`.
- *Xem tài liệu kiến trúc chuyên sâu:* [Kiến trúc phân vùng tập huấn luyện (TRAIN Partition Architecture)](../train_partition_architecture.md).

### Cell 07: Tiêu Đề Mục 04 (Markdown)
Tiêu đề: `## 04 Fair preprocessing and model registry`

### Cell 08: Pipeline Tiền Xử Lý và Đăng Ký Mô Hình (Code)
- Định nghĩa danh sách cột phân loại: `CATS = ['source_code', 'ward_current', 'district_text_extracted', 'province_text_extracted']`.
- Đăng ký bộ siêu tham số cơ sở cho 11 mô hình hồi quy (`BASE_PARAMS`).
- Định nghĩa `sklearn_pipeline(name, params, features)`:
  - Biến số: `SimpleImputer(strategy='median')` + tùy chọn `StandardScaler`.
  - Biến phân loại: `SimpleImputer(fill_value='__MISSING__')` + `OneHotEncoder(handle_unknown='ignore')` (hoặc `OrdinalEncoder` cho HistGradientBoosting).
- Định nghĩa `fit_predict(name, params, features, fit, score, transform)`:
  - Biến đổi mục tiêu qua `transform_target(fit[TARGET], transform)`.
  - Với CatBoost: Dùng chuỗi nguyên bản và khai báo `cat_features`.
  - Với LightGBM: Dùng `prepare_lightgbm_categories` để đồng bộ danh mục pandas với các mức nhãn `__MISSING__` và `__UNKNOWN__`.
  - Nghịch đảo dự đoán bằng `inverse_target(pred, transform)` trước khi tính toán sai số.
- Định nghĩa các mô hình cơ sở không tham số (`baseline_predict`):
  - `Global Median`: Trung vị toàn cục của fold huấn luyện.
  - `Hierarchical Location Median`: Trung vị theo phường $\rightarrow$ quận $\rightarrow$ toàn cục.
  - `Hierarchical Segment Median`: Trung vị theo phân khúc (phường + nhóm diện tích + nguồn) $\rightarrow$ (quận + diện tích) $\rightarrow$ diện tích $\rightarrow$ toàn cục.
- Định nghĩa `evaluate_config`: Đánh giá bất kỳ cấu hình nào trên cả 3 fold phát triển.

### Cell 09: Tiêu Đề Mục 05 (Markdown)
Tiêu đề: `## 05 F1–F5 development comparison and F4 vs F5 decision`

### Cell 10: Đánh Giá Các Tập Đặc Trưng và Quyết Định F4 so với F5 (Code)
- Đánh giá LightGBM trên toàn bộ các tập đặc trưng từ F1 đến F5 với biến đổi `LOG1P`.
- Đánh giá CatBoost trên F4 so với F5.
- Tính toán bảng quyết định chọn đặc trưng (`f45_decision`):
  - CatBoost: F4 MAE 968.421 VNĐ vs F5 MAE 958.637 VNĐ (F5 cải thiện 1,01%).
  - LightGBM: F4 MAE 941.954 VNĐ vs F5 MAE 942.554 VNĐ (F5 bị kém đi 600 VNĐ / -0,06%).
- **Quy tắc quyết định:**
  ```python
  consistent = bool(f45_decision['F5 better'].all())
  aggregate_gain = f45_decision['F5 absolute improvement'].sum() / f45_decision['F4 MAE'].sum() * 100
  SELECTED_FEATURE_SET = 'F5 — FULL SAFE TABULAR' if consistent and aggregate_gain >= 1.0 else 'F4 — AREA + SOURCE + LOCATION'
  ```
- Vì LightGBM không cải thiện trên F5, `consistent` là `False`. Quy tắc tất định chọn **`SELECTED_FEATURE_SET = 'F4 — AREA + SOURCE + LOCATION'`**.

### Cell 11: Tiêu Đề Mục 06 (Markdown)
Tiêu đề: `## 06 Development-only broad RAW vs LOG1P comparison`

### Cell 12: So Sánh Toàn Diện Thuật Toán và Biến Đổi Mục Tiêu (Code)
- Đánh giá 3 baseline và toàn bộ 11 mô hình hồi quy dưới cả hai dạng `RAW` và `LOG1P` trên các fold phát triển.
- Xác nhận các phát hiện:
  - Cả `RAW` và `LOG1P` được so sánh trên cùng DEVELOPMENT folds. Artifact hiện tại khóa `RAW`; không suy diễn rằng một transform luôn tốt hơn cho mọi model/dataset.
  - Các mô hình ensemble dạng cây (HistGradientBoosting, LightGBM, CatBoost, XGBoost, Random Forest) áp đảo các mô hình tuyến tính.
- Vẽ biểu đồ cột ngang so sánh MAE trên các fold phát triển.
- Kiểm tra tính nguyên vẹn: `assert not TEST_ACCESSED_FOR_SELECTION`.

### Cell 13: Tiêu Đề Mục 07 (Markdown)
Tiêu đề: `## 07 Small bounded tuning and candidate lock`

### Cell 14: Tinh Chỉnh Siêu Tham Số Giới Hạn và Khóa Ứng Viên (Code)
- Lọc top 3 mô hình tốt nhất từ Mục 06 (CatBoost, LightGBM, HistGradientBoosting).
- Chạy lưới tham số tinh chỉnh hẹp (`TUNING`).
- Thiết lập thứ tự độ phức tạp mô hình (`COMPLEXITY`):
  - Segment Median: 2, Linear: 3, HistGradientBoosting: 7, LightGBM: 11, XGBoost: 12, CatBoost: 13.
- Gọi hàm khóa ứng viên `lock_candidate(candidate_pool, COMPLEXITY, tolerance=0.01)`.
- Artifact hiện tại khóa **`LightGBM Regressor` / `RAW` / `F4`**, MAE DEVELOPMENT trung bình **883.025 VNĐ**, median **885.277 VNĐ**, độ lệch chuẩn **20.952 VNĐ**.
- Các tham số được khóa: `learning_rate=0.05`, `min_child_samples=30`, `n_estimators=180`, `num_leaves=63`, `objective='mae'`.

### Cell 15: Tiêu Đề Mục 08 (Markdown)
Tiêu đề: `## 08 Source ablation and leave-one-source-out diagnostics (development only)`

### Cell 16: Phân Tích Cắt Bỏ Nguồn và Tính Khái Quát Hóa (Code)
- **Cắt bỏ nguồn (Source Ablation):** Chạy lại mô hình đã khóa khi loại bỏ cột `source_code` khỏi tập đặc trưng.
  - Artifact hiện tại ghi nhận bỏ `source_code` làm MAE tăng khoảng **7,48%**.
  - Chứng minh danh tính cổng thông tin mang giá trị dự đoán quan trọng do sự phân khúc đối tượng khách hàng của từng trang.
- **Kiểm thử loại trừ từng nguồn (Leave-One-Source-Out - LOSO):** Huấn luyện trên tất cả các cổng trừ một cổng, sau đó đánh giá trên cổng bị giữ lại.
  - Đo lường khả năng mô hình khái quát hóa sang các cổng thông tin bất động sản mới.

### Cell 17: Tiêu Đề Mục 09 (Markdown)
Tiêu đề: `## 09 FINAL TEST — ONE-TIME EVALUATION`

### Cell 18: Đánh Giá Duy Nhất Một Lần Trên Tập TEST Niêm Phong (Code)
- Kiểm tra các rào chắn niêm phong:
  ```python
  assert LOCKED_MODEL and not TEST_ACCESSED_FOR_SELECTION
  TEST_ACCESSED_FOR_SELECTION = True
  ```
- Huấn luyện lại mô hình đã khóa (`LightGBM Regressor`) trên toàn bộ dữ liệu phát triển (`development_df`, 95.907 dòng).
- Dự đoán trên tập kiểm thử niêm phong (`test_df`, 16.531 dòng).
- Đánh giá cả 3 mô hình baseline trên cùng tập test đó.
- **Kết Quả Trên Tập Kiểm Thử (Test Set):**
  - `LightGBM Regressor`: **MAE = 900.669 VNĐ**, Median AE = 618.505 VNĐ, RMSE = 1.329.448 VNĐ, R² = 0,234.
  - `Hierarchical Segment Median`: MAE = 957.973 VNĐ (mô hình ML tốt hơn 5,98%).
  - `Hierarchical Location Median`: MAE = 1.125.936 VNĐ (mô hình ML tốt hơn 20,01%).
  - `Global Median`: MAE = 1.170.734 VNĐ (mô hình ML tốt hơn 23,07%).
- Lưu kết quả dự đoán vào DataFrame `test_predictions`.

### Cell 19: Tiêu Đề Mục 10 (Markdown)
Tiêu đề: `## 10 Tail, segment, prediction-sanity, and largest-error diagnostics`

### Cell 20: Các Chẩn Đoán Sai Số Chuyên Sâu (Code)
- **Phân tích đuôi phân phối (Tail Analysis):**
  - Đánh giá sai số trên 3 vùng giá: Vùng trung tâm ($\le$ P95), Vùng trên (P95–P99), Vùng cực đoan ($>$ P99).
  - Artifact hiện tại ghi nhận vùng cực đoan đóng góp **12,83% tổng bình phương sai số**; đây vẫn là vùng cần theo dõi riêng.
- **Chẩn đoán theo phân khúc (Segment Diagnostics):**
  - Đo lường sai số MAE theo nhóm diện tích, nhóm giá, quận huyện, và mức độ bóc tách địa chỉ (`WARD_RESOLVED` so với `DISTRICT_ONLY`).
- **Kiểm tra tính hợp lý của dự đoán (Prediction Sanity):**
  - Xác nhận: 0 dự đoán âm, 0 dự đoán bằng 0, 0 dự đoán vượt ngoài ngưỡng hợp lý 100k–100 triệu VNĐ.
- **Phân tích các trường hợp sai lệch lớn nhất:**
  - Liệt kê top 25 tin đăng có sai số tuyệt đối lớn nhất (chủ yếu là căn hộ penthouse hạng sang và biệt thự thương mại).
- Biểu đồ phân tán so sánh giá thực tế và giá dự đoán trên mẫu tập test.

### Cell 21: Tiêu Đề Mục 11 (Markdown)
Tiêu đề: `## 11 Locked-model feature importance and final verdict`

### Cell 22: Tầm Quan Trọng Của Đặc Trưng và Kết Luận Chính Thức (Code)
- Kiểm tra mức đóng góp của các đặc trưng (Diện tích là đặc trưng phân tách quan trọng nhất, tiếp theo là Cổng thông tin và Phường).
- Xây dựng bảng kết luận thẩm định chính thức (`final_verdict`):
  - Báo cáo Test MAE, Median AE, mức cải thiện so với các baseline, độ ổn định trên tập phát triển và tỷ trọng sai số vùng đuôi.
  - **Kết luận sẵn sàng sản phẩm (Readiness):** `experimental/prototype-ready; not production-ready` (Mức độ nguyên mẫu/thử nghiệm; chưa sẵn sàng đưa vào sản xuất vận hành).
  - **Lý do hạn chế:** Dù phương pháp luận hoàn toàn chặt chẽ và không bị rò rỉ dữ liệu, tập dữ liệu chỉ bao quát khoảng 10 ngày thu thập. Một mô hình huấn luyện trên 10 ngày không thể nắm bắt được tính chu kỳ theo mùa, lạm phát hoặc biến động thị trường dài hạn.

### Cell 23: Tiêu Đề Mục 12 (Markdown)
Tiêu đề: `## 12 Persist auditable benchmark evidence`

### Cell 24: Lưu Trữ Bằng Chứng Thực Nghiệm Lên Đĩa (Code)
- Tạo thư mục đích: `data/modeling/roombeacon_price_benchmark_v3/`.
- Xuất 20 bảng CSV kiểm toán.
- Xuất `test_predictions.parquet` (1,04 MB) qua DuckDB.
- Ghi file `experiment_metadata.json` ghi lại môi trường máy chủ, cấu hình phần cứng, siêu tham số và các cảnh báo giới hạn.
- Hiển thị danh mục các artifact đã lưu.

---

## 4. Bảng Tổng Hợp Kết Quả Benchmark

| Tiêu chí / Bước đánh giá | Baseline (Global Median) | Baseline (Segment Median) | Mô hình khóa (LightGBM / RAW / F4) |
| :--- | :--- | :--- | :--- |
| **TEST MAE** | 1.170.734 VNĐ | 957.973 VNĐ | **900.669 VNĐ** |
| **TEST Median AE** | 1.000.000 VNĐ | 700.000 VNĐ | **618.505 VNĐ** |
| **TEST RMSE** | 1.543.374 VNĐ | 1.391.715 VNĐ | **1.329.448 VNĐ** |
| **TEST R²** | -0,033 | 0,160 | **0,234** |
| **Mức cải thiện so với Global Median** | 0,00% | 18,17% | **+23,07%** |
| **Mức cải thiện so với Segment Median**| - | 0,00% | **+5,98%** |
| **Trung bình MAE tập phát triển** | - | - | 883.025 VNĐ |
| **Độ lệch chuẩn MAE phát triển** | - | - | 20.952 VNĐ |
| **Mức phạt khi cắt bỏ nguồn (Ablation)** | - | - | Tăng +7,48% sai số khi bỏ `source_code` |
| **Tỷ trọng sai số vùng đuôi cực đoan** | - | - | 12,83% tổng bình phương sai số từ vùng cực đoan |

---

## 5. Cẩm Nang Debug Dành Cho Lập Trình Viên

### Cách Kiểm Tra Bằng Chứng Mô Hình Mà Không Cần Chạy Lại
Để thẩm tra kết quả mà không phải chạy lại toàn bộ quá trình huấn luyện tốn kém:
```bash
ls -lh data/modeling/roombeacon_price_benchmark_v3/
head -n 25 data/modeling/roombeacon_price_benchmark_v3/final_verdict.csv
```

### Bảng Kiểm Tra Sự Cố Thường Gặp
- **Nếu gặp lỗi `ImportError: cannot import name 'prepare_lightgbm_categories'`:**
  - Kiểm tra xem `notebooks/utils/modeling_benchmark.py` đã có hàm này chưa.
  - Khởi động lại Jupyter kernel và import lại.
- **Nếu assertion `assert_group_isolation` thất bại ở Cell 06:**
  - Báo hiệu có tin đăng mang cùng giá trị `duplicate_candidate_group` bị phân bố sang các tập khác nhau.
  - Kiểm tra hàm `group_aware_split` trong `notebooks/utils/modeling_benchmark.py`.
- **Nếu assertion `assert not TEST_ACCESSED_FOR_SELECTION` bị kích hoạt:**
  - Báo hiệu có mã lệnh đã cố tình truy cập vào `test_df` trước khi quá trình khóa ứng viên hoàn tất.
