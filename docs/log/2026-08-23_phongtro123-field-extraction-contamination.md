# Báo Cáo Sự Cố: Lỗi Nhiễm Chéo Trường Dữ Liệu Trong Adapter PhongTro123 (Field Extraction Contamination)

## 1. Thông Tin Sự Cố

- **Ngày ghi nhận (Date)**: 2026-08-23
- **Thành phần ảnh hưởng (Component)**: PhongTro123 Adapter & HTML Listing Parser
- **Mô-đun**: `crawler/src/roombeacon_crawler/sources/phongtro123/parsers/listing_parser.py`
- **Trạng thái (Status)**: **Đã xử lý & Kiểm thử hồi quy (RESOLVED)**

---

## 2. Triệu Chứng

Trong quá trình điều tra lỗi tràn số `area_value`, khi kiểm tra chi tiết bản ghi lỗi từ nguồn `phongtro123`:
- `area_raw = '120202748m'`
- `seller_name_raw = '4.3 triệu/tháng 28 m 2'`

Trường `seller_name_raw` (tên người đăng) lại chứa chuỗi giá tiền và diện tích (`"4.3 triệu/tháng 28 m 2"`), còn trường `area_raw` lại chứa chuỗi mã ID bài đăng kèm chữ `m` (`"120202748m"`). Đây là hiện tượng **nhiễm chéo nội dung giữa các trường (cross-field contamination)** do parser bóc tách sai vị trí DOM.

---

## 3. Phạm Vi Ảnh Hưởng

- **Nguồn ảnh hưởng**: Chỉ xuất hiện tại nguồn `phongtro123` trên các trang danh sách (listing cards).
- **Mức độ nghiêm trọng**: Trung bình (không gây crash crawler, nhưng làm giảm chất lượng dữ liệu thô đối với trường tên người đăng và diện tích).

---

## 4. Nguyên Nhân Gốc (Root Cause)

1. **Sử dụng class tiện ích generic `line-clamp-1` để tìm tác giả**:
   - Trong `listing_parser.py`, đoạn mã trích xuất tác giả:
     ```python
     author_node = item.find(class_contains="post-author") or item.find(class_contains="author") or item.find(class_contains="user-name") or item.find(class_contains="line-clamp-1")
     ```
   - Class `line-clamp-1` là một class tiện ích CSS rút gọn văn bản trên 1 dòng của Tailwind, được PhongTro123 áp dụng cho thẻ chứa dòng tóm tắt giá và diện tích. Khi bài đăng không có class tác giả cụ thể, parser fallback sang `line-clamp-1` và nhầm dòng giá/diện tích thành tên người bán.
2. **Biểu thức chính quy `AREA_REGEX` quá tham lam**:
   - Biểu thức cũ: `re.compile(r"(\d+(?:[.,]\d+)?\s*m\s*(?:²|2)?)", re.IGNORECASE)`.
   - Phần `\s*m\s*(?:²|2)?` cho phép khớp với chữ `m` đứng độc lập ngay sau chuỗi số dài mà không bắt buộc có chữ số 2 hay ký tự biên từ (word boundary). Khi trong HTML xuất hiện ID bài đăng kết thúc bằng chữ `m` (hoặc trong URL), regex đã trích xuất nhầm cả chuỗi 9 chữ số `120202748m`.

---

## 5. Dữ Liệu Ví Dụ

| Trường Dữ Liệu | Trước Khi Sửa (Bị Nhiễm Chéo) | Sau Khi Sửa (Chính Xác) |
| :--- | :--- | :--- |
| `listing_id` | `120202748` | `120202748` |
| `price_raw` | `4.3 triệu/tháng` | `4.3 triệu/tháng` |
| `area_raw` | `'120202748m'` *(Sai)* | `'28 m2'` *(Chính xác)* |
| `seller_name_raw` | `'4.3 triệu/tháng 28 m 2'` *(Nhiễm chéo)* | `'Anh Nam Chủ Nhà'` / `None` *(Chính xác)* |

---

## 6. Giải Pháp Khắc Phục (Code Fix)

1. **Loại bỏ selector `line-clamp-1`**:
   Chỉ chấp nhận các class định danh tác giả rõ ràng: `post-author`, `author-name`, `author`, `user-name`, `post__author`.
2. **Siết chặt biểu thức chính quy `AREA_REGEX`**:
   Giới hạn số chữ số diện tích trong khoảng 1 đến 4 chữ số và bắt buộc có đơn vị rõ ràng:
   ```python
   AREA_REGEX = re.compile(r"\b(\d{1,4}(?:[.,]\d+)?)\s*(?:m²|m2|mét vuông|m\b)", re.IGNORECASE)
   ```

---

## 7. Phân Biệt Khái Niệm Trong Bronze

- **Source-Dirty Data (Dữ liệu Thô Gốc Bị Bẩn)**: Dữ liệu do chính website người dùng đăng tải bị lỗi (ví dụ chủ nhà nhập giá "Thỏa thuận", diện tích "0 m2").
- **Extraction Defect (Lỗi Bóc Tách Của Parser)**: Dữ liệu trên website hoàn toàn đúng, nhưng do lỗi logic bộ bóc tách nên hệ thống trích xuất nhầm trường này sang trường khác.
- **Quy tắc**: Lỗi bóc tách cần được sửa ngay tại tầng Adapter/Parser, không được coi là dữ liệu thô tự nhiên của nguồn.

---

## 8. Kiểm Thử Hồi Quy (Regression Testing)

- Đã bổ sung test case `test_phongtro123_parser_no_cross_field_contamination` trong `tests/test_area_normalization_and_persistence.py`.
- Kết quả: `price_raw='4.3 triệu/tháng'`, `area_raw='28 m2'`, `seller_name_raw='Anh Nam Chủ Nhà'`, không còn hiện tượng nhiễm chéo.
- Toàn bộ 235 tests chạy thành công (100% PASS).

---

## 9. Danh Sách Tệp Đã Sửa (Files Modified)

- `crawler/src/roombeacon_crawler/sources/phongtro123/parsers/listing_parser.py`
- `tests/test_area_normalization_and_persistence.py`
- `docs/log/README.md`
- `docs/log/2026-08-23_phongtro123-field-extraction-contamination.md`
