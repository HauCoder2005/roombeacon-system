# Hợp Đồng Dữ Liệu Tầng Silver (Silver Contract)

> **Plane:** Processing
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [PROCESSING_ARCHITECTURE.md](PROCESSING_ARCHITECTURE.md), [../adr/ADR-003.md](../adr/ADR-003.md)

---

## 1. Thông Số Tổng Thể Tập Dữ Liệu Silver Canonical

- **Tệp dữ liệu:** `data/silver/rental_listings.parquet` (~32 MB).
- **Tệp siêu dữ liệu:** `data/silver/rental_listings.metadata.json`.
- **Tổng số dòng:** **132,436 dòng**.
- **Cấp độ chi tiết (Grain):** Đúng 1 dòng cho mỗi `rental_post_id` duy nhất.
- **Tổng số cột:** **80 cột**.
- **Khoảng thời gian quan sát:** `2026-09-20 12:48:44` đến `2026-09-30 10:42:53`.

---

## 2. Phân Nhóm 80 Cột Dữ Liệu Silver Theo Chức Năng

80 cột dữ liệu của Silver được chia thành 10 nhóm trường rõ ràng:

### Nhóm 1: Định Danh & Nguồn Gốc Bronze (20 cột gốc)
`source_code`, `rental_post_id`, `source_listing_id`, `title_raw`, `url`, `price_amount`, `area_value`, `full_address_text`, `location_raw`, `full_address_inherited`, `map_provider`, `map_latitude`, `map_longitude`, `map_query_raw`, `best_address_text`, `best_address_source`, `latest_observed_at`, `first_observed_at`, `last_observed_at`, `active_days`.

### Nhóm 2: Chuẩn Hóa Văn Bản (4 cột)
`full_address_text_clean`, `location_raw_clean`, `best_address_text_clean`, `title_clean`.

### Nhóm 3: Ý Định & Phạm Vi Cho Thuê (7 cột)
`title_quality_status`, `listing_intent`, `listing_intent_reason`, `listing_intent_evidence`, `rental_scope`, `rental_scope_reason`, `rental_scope_evidence`.

### Nhóm 4: Bóc Tách Phân Cấp Địa Chỉ (5 cột)
`street_text_extracted`, `ward_text_extracted`, `district_text_extracted`, `province_text_extracted`, `parse_status`.

### Nhóm 5: Chuẩn Hóa Phường & Nhất Quán Hành Chính (7 cột)
`ward_normalized`, `ward_current`, `ward_mapping_status`, `ward_mapping_candidates`, `admin_consistency_status`, `admin_consistency_reason`, `admin_consistency_candidates`.

### Nhóm 6: Làm Sạch & Thẩm Định Giá (10 cột)
`price_amount_clean`, `price_quality_status`, `price_lineage_aligned`, `price_regression_status`, `price_parser_comparison_status`, `price_target_trust_status`, `price_target_trust_reason`, `price_target_trust_evidence`, `price_model_value`, `price_target_model_value`.

### Nhóm 7: Làm Sạch & Thẩm Định Diện Tích (7 cột)
`area_value_clean`, `area_quality_status`, `area_lineage_aligned`, `area_regression_status`, `area_semantic_status`, `area_model_suitability`, `area_semantic_evidence`.

### Nhóm 8: Phát Hiện Ngoại Lai Số Học & Phù Hợp Mô Hình (7 cột)
`price_outlier_flag`, `area_outlier_flag`, `numeric_outlier_status`, `price_semantic_status`, `price_model_suitability`, `price_semantic_evidence`, `price_area_availability_status`, `price_area_quality_status`.

### Nhóm 9: Kiểm Định Toạ Độ Không Gian (6 cột)
`coordinate_pair_valid`, `coordinate_pair_listing_count`, `coordinate_pair_address_count`, `coordinate_trust_reason`, `has_trusted_coordinate`, `coordinate_quality_status`.

### Nhóm 10: Nhận Diện Trùng Lặp & Chất Lượng Bản Ghi (7 cột)
`duplicate_candidate_group`, `duplicate_match_reason`, `duplicate_scope`, `duplicate_candidate_status`, `temporal_quality_status`, `row_quality_status`.

---

## 3. Các Hệ Thức Bất Biến Cốt Lõi (Critical Invariants)

1. **Bảo toàn số dòng 100%:** Số dòng đầu vào từ snapshot Bronze bằng đúng số dòng đầu ra Silver (132,436 dòng). Không có bản ghi nào bị xóa âm thầm.
2. **Khóa chính duy nhất:** `rental_post_id` không null và không trùng lặp.
3. **Bảo toàn trường gốc:** 20 trường Bronze ban đầu được giữ nguyên giá trị gốc để làm bằng chứng kiểm toán (audit trail).
4. **Không nội suy toạ độ giả:** Nếu toạ độ thiếu hoặc không tin cậy, `has_trusted_coordinate = FALSE`, tuyệt đối không lấy tâm phường gán vào.
5. **Giữ nguyên ngoại lai:** Các bản ghi ngoại lai (Outliers) và trùng lặp (Duplicates) không bị xóa khỏi Silver mà được gắn cờ phân loại để các tác vụ downstream tự quyết định bộ lọc.

---

## 4. Từ Điển Trạng Thái Chất Lượng Bản Ghi (`row_quality_status`)

Mỗi bản ghi trong Silver được phân loại thành một trong ba trạng thái tổng hợp:

| Trạng thái (`row_quality_status`) | Số lượng tin | Tỷ lệ (%) | Ý nghĩa kỹ thuật & Khuyến nghị sử dụng |
|---|---:|---:|---|
| **`READY_WITH_FLAGS`** | 125,249 | 94.57% | Dữ liệu hợp lệ, đầy đủ giá và diện tích để phân tích, nhưng có gắn cờ cảnh báo (ví dụ thiếu toạ độ GPS tin cậy, địa chỉ kế thừa, hoặc giá/diện tích nằm ở biên ngoại lai). |
| **`REQUIRES_REVIEW`** | 5,956 | 4.50% | Bản ghi thiếu giá hoặc diện tích, hoặc có sự mâu thuẫn lớn giữa các trường thông tin cần xem xét kỹ trước khi đưa vào mô hình. |
| **`READY`** | 1,231 | 0.93% | Bản ghi hoàn hảo: đầy đủ giá, diện tích, toạ độ GPS chính xác và địa chỉ chuẩn hóa cấp số nhà. |
