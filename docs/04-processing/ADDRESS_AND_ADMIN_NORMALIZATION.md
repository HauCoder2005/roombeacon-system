# Chuẩn Hóa Địa Chỉ & Bản Đồ Hành Chính (Address & Admin Normalization)

> **Plane:** Processing
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [PROCESSING_ARCHITECTURE.md](PROCESSING_ARCHITECTURE.md), [GEOCODING_ENRICHMENT.md](GEOCODING_ENRICHMENT.md)

---

## 1. Bóc Tách Địa Chỉ Phân Cấp (`AddressParser`)

Địa chỉ phòng trọ tại Việt Nam thường được người đăng tin viết tự do, thiếu đồng nhất hoặc viết tắt (ví dụ: *"Đường D2, P.25, Q. Bình Thạnh, TP.HCM"*).

Module [`notebooks/utils/address_parser.py`](../../notebooks/utils/address_parser.py) phân tích chuỗi `full_address_text_clean` và `best_address_text_clean` thành 4 cấp hành chính:
1. `street_text_extracted`: Tên đường / số nhà.
2. `ward_text_extracted`: Tên phường / xã trích xuất.
3. `district_text_extracted`: Tên quận / huyện trích xuất.
4. `province_text_extracted`: Tên tỉnh / thành phố trích xuất.

---

## 2. Đối Chiếu Danh Mục Hành Chính (Gazetteer) & Xử Lý Sáp Nhập

Một thách thức lớn tại TP. Hồ Chí Minh và các đô thị lớn là **các đợt sắp xếp, sáp nhập đơn vị hành chính** (ví dụ thành lập TP. Thủ Đức, sáp nhập các phường tại Quận 2, Quận 9, Quận Thủ Đức, Quận 3, Quận 10...).

Module [`notebooks/utils/ward_normalization.py`](../../notebooks/utils/ward_normalization.py) đối chiếu địa chỉ trích xuất với cơ sở dữ liệu **Bản đồ Hành chính Việt Nam (Gazetteer)**:
- **`ward_normalized`:** Tên phường sau khi loại bỏ tiền tố thừa, chuẩn hóa dấu tiếng Việt và chữ hoa/thường.
- **`ward_current`:** Tên đơn vị hành chính hiện hành sau khi ánh xạ. Nếu tin đăng dùng tên phường cũ (ví dụ *"Phường An Khánh, Quận 2"*), hệ thống tự động ánh xạ về phường mới tương ứng.
- **`ward_mapping_status`:** Trạng thái ánh xạ:
  - `EXACT_MATCH`: Khớp chính xác 100% với danh mục hiện hành;
  - `HISTORICAL_MAPPED`: Ánh xạ thành công từ tên cũ sang tên mới;
  - `AMBIGUOUS`: Tên phường xuất hiện ở nhiều quận khác nhau mà tin đăng không ghi rõ quận;
  - `UNRESOLVED`: Không tìm thấy trong danh mục.

---

## 3. Kiểm Định Tính Nhất Quán Hành Chính (`admin_consistency_status`)

Hệ thống kiểm tra chéo giữa thông tin quận/huyện và phường/xã để phát hiện các tin đăng ghi mâu thuẫn (ví dụ: ghi *"Phường Bến Nghé"* nhưng lại chọn *"Quận 7"*):

| Trạng thái | Ý nghĩa kỹ thuật | Cách xử lý trong mô hình & serving |
|---|---|---|
| **`CONSISTENT`** | Phường trích xuất thuộc đúng về quận trích xuất theo danh mục hành chính. | Đủ điều kiện sử dụng làm đặc trưng không gian đáng tin cậy. |
| **`INCONSISTENT`** | Phường và quận mâu thuẫn nhau (phường không nằm trong quận ghi trên tin). | Gắn cờ cảnh báo; loại trừ khỏi các fold huấn luyện đòi hỏi vị trí nghiêm ngặt. |
| **`AMBIGUOUS`** | Tên phường tồn tại nhưng trùng tên ở nhiều nơi và không đủ căn cứ phân giải. | Giữ nguyên văn bản, không gán tên phường chuẩn hóa. |
| **`UNVERIFIABLE`** | Tin đăng chỉ có tên đường hoặc tên khu dân cư, không có tên phường. | Dùng làm tin tìm kiếm dự phòng cấp Quận. |
