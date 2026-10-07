# Notebook 06 — Shadow Validation: Giải Thích Kiến Trúc và Vận Hành

## 1. Vì sao Notebook 06 tồn tại

Notebook 04 đã hoàn tất việc chọn và khóa champion: **LightGBM Regressor + RAW target + F4**. Notebook 06 không lặp lại benchmark. Nó kiểm tra xem artifact đã khóa có thể được nạp, nhận đúng schema F4, dự đoán an toàn trên một batch giống inference, và tạo đủ bằng chứng drift/error để theo dõi trước khi dùng trong sản phẩm.

Ranh giới trách nhiệm:

```text
04: train → benchmark → tune giới hạn → select → persist champion
06: load champion → validate schema → predict → monitor → persist shadow evidence
```

Notebook 06 không chứa API/backend serving và không gọi `fit`, cross-validation, search hoặc model selection. Logic dùng lại nằm trong `notebooks/utils/shadow_validation.py`, nên một dịch vụ inference sau này có thể dùng cùng hợp đồng mà không phụ thuộc trạng thái Jupyter.

## 2. Hai chế độ validation

### `HISTORICAL_DRY_RUN`

Batch hiện tại thuộc snapshot đã được quan sát trong giai đoạn phát triển mô hình. Chế độ này xác minh model loading, schema, unknown-category handling, prediction, metrics, biểu đồ và persistence. Nó **không** được tính là bằng chứng production mới, kể cả khi mọi check kỹ thuật đều PASS.

### `FUTURE_SHADOW`

Chỉ một batch mà mọi quan sát đều nằm sau `evidence_cutoff` đã lưu trong champion metadata mới được phân loại là future shadow. Batch bị trộn, thiếu timestamp hoặc không có cutoff đáng tin cậy được hạ bảo thủ về historical dry run. Future evidence không được dùng để tune lại champion.

## 3. Champion artifact contract

Notebook nạp ba artifact từ `data/modeling/roombeacon_price_benchmark_v3/`:

- `champion_model.joblib`: fitted LightGBM đã khóa;
- `champion_metadata.json`: model ID, SHA-256, model family/class, RAW transform, F4, ordered features, hyperparameters, seed, schema, categorical vocabularies và training/reference range;
- `champion_reference_profile.json`: thống kê tổng hợp từ **DEVELOPMENT**, tuyệt đối không từ TEST.

Loader đối chiếu các artifact này với `experiment_metadata.json`. Sai family, transform, feature order, parameters, class, hash, model ID hoặc reference lineage đều làm pipeline fail rõ ràng.

Model ID có dạng:

```text
roombeacon-price-lgbm-f4-raw-<12 ký tự đầu của SHA-256 artifact>
```

Suffix được tính từ binary thật, không phải version tự đặt.

## 4. Hợp đồng inference F4

Thứ tự predictor là bất biến:

1. `area_value_clean`
2. `source_code`
3. `ward_current`
4. `district_text_extracted`

`price_model_value`, giá raw/clean, price-per-area, ID và mọi biến dẫn xuất từ target bị chặn khỏi ma trận inference. `rental_post_id` và timestamp chỉ được giữ để căn hàng output. Actual price chỉ được join theo ID sau khi `predict` đã hoàn tất.

Eligibility được tách làm hai pha để giữ đúng ranh giới chống leakage. Trước prediction, `build_inference_eligibility(..., policy="PERMISSIVE")` chỉ đọc area suitability, diện tích, listing intent và rental scope; nó không đọc bất kỳ trường price/target/trust nào. Sau khi prediction đã tồn tại, `build_modeling_eligibility(...)` của Notebook 04 mới được áp dụng để xác định những dòng có trusted actual đủ điều kiện đánh giá. Vì vậy mọi dòng đủ điều kiện inference vẫn được giữ trong output, còn actual/residual chỉ xuất hiện trên tập đánh giá hợp lệ. Mỗi dòng Silver nhận trạng thái rõ ràng; không có dòng bị mất âm thầm. ID trùng bị từ chối. Diện tích thiếu/không hữu hạn/không dương không được đưa vào model.

Các categorical dùng vocabulary được học từ DEVELOPMENT và hai sentinel:

- `__MISSING__` cho giá trị thiếu;
- `__UNKNOWN__` cho category mới.

Vì vậy category chưa từng thấy được báo cáo drift nhưng không làm LightGBM crash.

## 5. Reference và drift monitoring

Reference profile chỉ lưu thống kê tổng hợp cần thiết:

- area: count, missing %, P05, P25, median, P75, P95;
- source/ward/district: distribution, category count, missing/unknown rate;
- prediction: min, P01, P25, median, P75, P95, P99, max;
- target: median, P95, P99.

Notebook báo median/IQR/P95/missing shift cho area; reference/current share và chênh lệch điểm phần trăm cho nguồn; unseen categories, số dòng ảnh hưởng và missing shift cho source/ward/district. Đây là các chỉ số diễn giải trực tiếp, chưa thêm dependency PSI/JS/KS không cần thiết.

## 6. Error monitoring

Khi trusted actual tồn tại, Notebook tính toàn bộ metric bằng VND gốc:

- MAE, MedianAE, RMSE, RMSLE, R²;
- standardized residual = prediction − actual (residual > 0: overprediction; residual < 0: underprediction);
- signed bias = trung bình của (prediction − actual);
- tỷ lệ underprediction, overprediction và exact match.

Các lát cắt gồm:
- Actual-price bucket (chỉ dùng chẩn đoán sau inference, sắp xếp theo thứ tự số học tự nhiên: `< 2.5M`, `2.5M–<4.0M`, `4.0M–<6.0M`, `6.0M–10.0M`, `> 10.0M`);
- Area bucket (sắp xếp theo thứ tự vật lý: `Small <15m²`, `Compact 15–<25m²`, `Standard 25–<40m²`, `Large 40–80m²`, `Very large >80m²`);
- Source đủ support (hiển thị kèm `Inference Share %` và `Evaluation Rows`);
- Location phân tách độc lập: High-support Wards và High-support Districts riêng biệt, loại trừ `__MISSING__` khỏi bảng xếp hạng;
- RENT so với UNKNOWN;
- Daily error: chẩn đoán tích hợp dry-run, không coi là out-of-sample temporal evidence.

Prediction-compression monitor so P01/median/P99 và độ rộng P01–P99 giữa actual và prediction để phát hiện xu hướng dự đoán co cụm ở trung tâm dải giá.

## 7. Production readiness gate và Quản trị ngưỡng

Scorecard theo dõi artifact loading, contract/leakage, unknown safety, prediction sanity, drift, sample size, temporal coverage, core-market stability, budget calibration, upper-tail calibration, source stability và location stability.

Các ngưỡng kiểm tra (source shift, unseen categories, bias ratios) được định nghĩa dưới dạng **PROVISIONAL MONITORING THRESHOLDS** (hằng số cấu hình mang tính chất heuristic kỹ thuật, không phải SLA kinh doanh đã qua kiểm chứng production).

Tách bạch rõ hai trạng thái:
- **MODEL READINESS**: `CANDIDATE` (mô hình champion đạt chuẩn kỹ thuật nhưng chưa có bằng chứng tương lai)
- **DEPLOYMENT LIFECYCLE**: `SHADOW` (hạ tầng shadow validation đã sẵn sàng nhận batch tương lai)
- **PRODUCTION EVIDENCE**: `INSUFFICIENT` (`HISTORICAL_DRY_RUN` không bao giờ tự động promote production).

Bằng chứng tối thiểu tiếp theo là khoảng 30–60 ngày dữ liệu multi-crawl sau model lock (`FUTURE_SHADOW`), không dùng để tuning, ổn định theo nguồn/vị trí.

## 8. Artifact shadow append-only

Mỗi lần chạy tạo thư mục mới:

```text
data/modeling/shadow_validation/
├── runs/<unique_run_id>/
│   ├── run_metadata.json
│   ├── predictions.parquet
│   ├── manifest.json
│   └── *.csv
└── summary/run_index.csv
```

Thư mục run đã tồn tại không được ghi đè. Metadata giữ model ID/hash, mode, thời gian dữ liệu, counts, prediction distribution, metrics và kết luận evidence. Manifest hash từng file để phục vụ audit.

## 9. Giải thích từng visualization

1. **Population context and serving funnel** — hiển thị phễu phục vụ: Silver ($132.436$) → Inference-ready ($129.066$) → Evaluation-ready ($112.438$); ngữ cảnh quy mô dữ liệu, không phải metric drift.
2. **Reference vs shadow area distribution profile** — so P25/median/P75/P95 theo m²; phát hiện dịch chuyển loại hình phòng.
3. **Source share: reference vs shadow** — so tỷ trọng từng nguồn theo %; phát hiện crawl/source-mix shift.
4. **Champion prediction distribution** — histogram giá dự đoán, kèm median/P99 reference; kiểm tra hình dạng và tail prediction.
5. **Actual vs predicted** — scatter theo triệu VND với đường lý tưởng; lấy mẫu $n=5.000$ từ $n=112.438$ với giới hạn hiển thị P99 để dễ đọc; toàn bộ dòng đều được giữ trong metrics.
6. **Residual distribution** — residual = prediction − actual (overprediction > 0) hiển thị dải trung tâm P01–P99; toàn bộ dòng đều được giữ trong metrics.
7. **MAE by actual-price bucket** — chẩn đoán budget/core/upper-tail theo thứ tự số học tự nhiên; bucket không route inference.
8. **MAE by area bucket** — sắp xếp theo thứ tự diện tích vật lý tăng dần (Small → Very large).
9. **MAE by source** — chỉ hiển thị nguồn đủ support, phân tách rõ nhãn inference share và evaluation rows.
10. **MAE for high-support locations** — hai biểu đồ riêng biệt cho Top Wards và Top Districts theo support, loại trừ `__MISSING__`.
11. **RENT vs UNKNOWN monitoring** — so lỗi theo canonical intent mà không đổi policy.
12. **Historical dry-run daily error** — chẩn đoán tích hợp nội bộ; không phải bằng chứng temporal ngoài mẫu.
13. **Actual vs prediction compression** — so P01/median/P99 để nhìn nhận mức độ co cụm phân phối dự đoán trên batch quan sát.
14. **Production readiness scorecard** — PASS/NOT MET theo từng chiều với ngưỡng provisional; historical mode không thể promote production.

Mọi biểu đồ ghi rõ đơn vị, population/mode và sample size hoặc ngưỡng support liên quan.

## 10. Debug nhanh

- `Benchmark metadata does not contain a serialized champion pointer`: cần chạy đường persist champion đã khóa từ Notebook 04; không tạo model tùy ý trong Notebook 06.
- `Champion ... disagreement`: kiểm tra metadata/hash/model file; không bỏ qua assertion.
- `Duplicate rental_post_id`: sửa batch upstream, không deduplicate âm thầm.
- `F4 feature contract mismatch`: metadata hoặc feature order không thuộc champion đã khóa.
- `FileExistsError` khi persist: run ID đã tồn tại; dùng một execution timestamp mới, không ghi đè lịch sử.
