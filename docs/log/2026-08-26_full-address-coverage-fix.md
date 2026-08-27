# BÁO CÁO SỰ CỐ KỸ THUẬT: FIX MISSING FULL ADDRESS & MERGE RULE INVARIANT

**Mã sự cố**: `INC-20260826-FULL-ADDRESS-COVERAGE`  
**Ngày phát hiện**: 2026-08-26  
**Thành phần liên quan**: `roombeacon_crawler.sources.common_html`, `roombeacon_crawler.sources.cafeland.parsers.detail_parser`, `roombeacon_crawler.sources.chothuenha.parsers.detail_parser`, `roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository`, `roombeacon_crawler.application.crawl.deferred_details`  
**Trạng thái**: **RESOLVED**  

---

## 1. Hiện Trạng Trước Khi Sửa (Pre-Fix Status)

- **Tổng số listing trên hệ thống**: 5,162
- **Số listing có `full_address_text`**: 4,273
- **Số listing thiếu `full_address_text`**: 889 (Độ phủ: **82.78%**)
- **Phân bố thiếu địa chỉ theo nguồn dữ liệu**:
  - `cafeland`: 802 thiếu / 918 tổng (12.64% coverage)
  - `phongtro123`: 92 thiếu / 1,049 tổng (91.23% coverage)
  - `nhatot`: 43 thiếu / 423 tổng (89.83% coverage)
  - `chothuenha`: 30 thiếu / 76 tổng (60.53% coverage)
  - `chothuephongtro`, `mogi`, `nhatrovn`, `tromoi`: 0 thiếu (100.00% coverage)

---

## 2. Nguyên Nhân Gốc (Root Cause Analysis)

Qua quá trình kiểm toán toàn bộ 889 bản ghi thiếu địa chỉ, các nguyên nhân gốc được phân lập như sau:

1. **Lỗi Ghi Đè Địa Chỉ Bằng NULL (Address Merge Invariant Violation)**:
   - Khi một tin đăng đã có địa chỉ chi tiết đầy đủ ở phiên bản trước (từ detail crawl), nếu một phiên thu thập lightweight (chỉ quét thẻ tin/discovery) quét lại tin đăng đó với `address_raw = NULL`, `MySQLPostChildrenRepository` không ghi nhận dòng vào bảng `post_addresses` cho phiên bản mới (`rental_post_version_id`).
   - Khung nhìn phân tích `v_latest_posts` kết nối `post_addresses` dựa trên phiên bản mới nhất (`latest_version_id`). Do phiên bản mới không có dòng địa chỉ, địa chỉ của tin đăng bị mất khỏi `v_latest_posts` (`OVERWRITTEN_WITH_NULL`).
   - Tác động: 79 tin đăng (`chothuenha`: 30, `phongtro123`: 39, `nhatot`: 10) bị mất địa chỉ dù trước đó đã từng có địa chỉ hợp lệ.

2. **Lỗi Bóc Tách Trực Tiếp Tại Nguồn `Cafeland`**:
   - Giao diện HTML trang chi tiết CafeLand sử dụng thẻ `<div class="reales-location">` và `<div class="infor">Vị trí: [Địa chỉ] Lưu tin...</div>`.
   - `CafelandDetailParser` trước đây chỉ định nghĩa `ADDRESS_CLASSES=("reals-address", "address")`, bỏ sót selector `reales-location`.
   - Khi không khớp, parser rơi vào `_semantic_address` và vô tình bóc nhầm văn bản thanh lọc điều hướng danh mục ("Lọc theo khu vực Toàn Quốc TP. Hà Nội...").

3. **Lỗi Trích Xuất Sai Địa Chỉ Doanh Nghiệp Trên `ChoThueNha`**:
   - `SourceDetailParser._jsonld_address` duyệt tất cả các script JSON-LD mà không loại trừ kiểu thực thể doanh nghiệp (`RealEstateAgent`, `Organization`), dẫn đến việc lấy nhầm địa chỉ trụ sở công ty (`Lầu 2, Tòa nhà 402 Huỳnh Văn Bánh, Phú Nhuận`) thay vì địa chỉ bất động sản cho thuê (`House`, `Apartment`).

4. **Đồng Nhất Sai Giữa Detail Fetch Success và Address Extract Success**:
   - Trong `deferred_details.py` và `card_processing.py`, khi trang chi tiết được tải thành công (HTTP 200) nhưng parser trích xuất địa chỉ thất bại (`address_raw is None`), hệ thống vẫn đánh dấu xóa khỏi hàng đợi hoãn (`record_success`), ngăn cản việc retry/enrichment theo chu kỳ.

---

## 3. Các Thay Đổi & Giải Pháp Kỹ Thuật (Remediation)

1. **Hoàn thiện Bộ Khung Trích Xuất Địa Chỉ (`SourceDetailParser` trong `common_html.py`)**:
   - Thêm danh sách đen `DISALLOWED_JSONLD_TYPES` (`RealEstateAgent`, `Organization`, `LocalBusiness`, `WebSite`, `Person`, `BreadcrumbList`) để không bao giờ bóc địa chỉ công ty/sàn môi giới.
   - Thêm bộ lọc `_is_garbage_address` loại bỏ triệt để các chuỗi điều hướng danh mục ("Lọc theo khu vực", "Toàn Quốc TP...").
   - Hỗ trợ phương thức `_extract_address` ưu tiên: JSON-LD BĐS -> Nhãn ngữ nghĩa -> DOM Scoped.

2. **Cập nhật Bộ Bóc Tách CafeLand (`CafelandDetailParser`)**:
   - Bóc tách chuẩn xác địa chỉ từ `<div class="reales-location">` và `<div class="infor">` kèm tiền tố `Vị trí:`.

3. **Cập nhật Bộ Bóc Tách ChoThueNha (`ChothuenhaDetailParser`)**:
   - Định phạm vi trích xuất vào `<p class="pd-map">`, `<p class="p-map">`, `<div class="dv-bds-bd">`, loại trừ hoàn toàn địa chỉ trụ sở công ty.

4. **Thực Thi Quy Tắc Merge Địa Chỉ Bất Biến (`MySQLPostChildrenRepository`)**:
   - Khi lưu trữ thông tin cho một phiên bản tin đăng mới, nếu quan sát mới không có địa chỉ (`address_raw is None`), hệ thống tự động truy vấn và kế thừa địa chỉ hợp lệ gần nhất của cùng `rental_post_id` từ `post_addresses`, đảm bảo không bao giờ bị ghi đè thành NULL.

5. **Phục Hồi Dữ Liệu Mục Tiêu (Targeted Re-enrichment)**:
   - Áp dụng quy tắc kế thừa địa chỉ cho 79 tin đăng bị ghi đè NULL trước đó.
   - Chạy bổ sung thông tin địa chỉ tuân thủ tải (polite rate limit) cho các tin bài CafeLand và PhongTro123 còn thiếu.

---

## 4. Kết Quả Sau Khi Khắc Phục (Post-Fix Status)

### Thống Kê Theo Từng Nguồn Dữ Liệu (Latest Version Per Post):

| Nguồn Dữ Liệu (Source) | Tổng Số Tin (Total Posts) | Có Địa Chỉ (Has Address) | Thiếu Địa Chỉ (Missing) | Độ Phủ (Coverage %) | Trạng Thái (Status) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **chothuenha** | 76 | 76 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **chothuephongtro** | 697 | 697 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **mogi** | 305 | 305 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **nhatrovn** | 861 | 861 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **phongtro123** | 1,049 | 1,049 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **tromoi** | 833 | 833 | 0 | **100.00%** | **HOÀN TOÀN ĐẦY ĐỦ** |
| **cafeland** | 918 | 910 | 8 | **99.13%** | 8 tin còn lại là URL trang hồ sơ môi giới (`moi-gioi/`), không có địa chỉ BĐS |
| **nhatot** | 445 | 406 | 39 | **91.24%** | 39 tin là bản ghi discovery lightweight chờ quét chi tiết / hạn chế Cloudflare |
| **TỔNG TOÀN HỆ THỐNG** | **5,184** | **5,137** | **47** | **99.09%** | **VƯỢT TRỘI (TĂNG TỪ 82.78% LÊN 99.09%)** |

---

## 5. Xác Minh & Kiểm Thử (Verification)

- **Unit Tests**: 13/13 tests trích xuất địa chỉ độc lập vượt qua (`test_full_address_extraction.py`).
- **Toàn Bộ Test Suite**: 373/373 tests pass không có lỗi.
- **Airflow DAGs**: 0 import errors (`docker compose exec -T airflow-api-server airflow dags list-import-errors`).
- **Toàn Vẹn Dữ Liệu**: Khung nhìn `v_latest_posts` trong DuckDB đồng bộ hoàn toàn với MySQL Bronze, không phát sinh trùng lặp bản ghi hay ô nhiễm dữ liệu.
