# Hợp Đồng Bóc Tách Dữ Liệu Thô (Extraction Contract)

> **Plane:** Ingestion
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [CRAWLER_ARCHITECTURE.md](CRAWLER_ARCHITECTURE.md), [../03-storage/BRONZE_MYSQL.md](../03-storage/BRONZE_MYSQL.md)

---

## 1. Cấu Trúc Mô Hình Dữ Liệu Miền (Domain Data Models)

Lớp Ingestion định nghĩa các mô hình dữ liệu chuẩn hóa tại [`crawler/src/roombeacon_crawler/models/`](../../crawler/src/roombeacon_crawler/models):

1. **`ListingCardRaw`:**
   - Dữ liệu trích xuất từ thẻ bài đăng trên trang danh mục.
   - Các trường chính: `listing_id`, `url`, `title_raw`, `price_raw`, `area_raw`, `location_raw`, `posted_at_raw`, `image_urls_raw`.
2. **`ListingDetailRaw`:**
   - Dữ liệu trích xuất từ trang chi tiết bài đăng.
   - Các trường chính: `description_raw`, `address_raw`, `property_type_raw`, `furnishing_raw`, `deposit_raw`, `seller_name_raw`, `seller_phone_raw`, `amenities_raw`, `map_location` (toạ độ lat/lng nhúng và query chuỗi), `image_urls_raw`.
3. **`RentalBronzeRecord`:**
   - Bản ghi quan sát hợp nhất đại diện cho trạng thái của bài đăng tại phiên cào hiện tại.
   - Chứa toàn bộ thông tin Card + Detail + Metadata phiên cào (`crawl_run_id`, `crawled_at`, `source_name`).

---

## 2. Thông Dịch Ngày Đăng Tiếng Việt (`VietnameseDateInterpreter`)

Các trang web bất động sản Việt Nam thường hiển thị thời gian đăng tin dưới nhiều hình thức văn bản tự do:
- Tương đối: *"Vừa xong"*, *"5 phút trước"*, *"2 giờ trước"*, *"Hôm qua"*, *"3 ngày trước"*.
- Tuyệt đối: *"23:15, 13/07/2026"*, *"Đăng ngày: 15/08/2026"*.

Bộ thông dịch [`VietnameseDateInterpreter`](../../crawler/src/roombeacon_crawler/sources/common_html.py) chuẩn hóa các chuỗi này về thời gian tuyệt đối định dạng ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`), lấy mốc thời gian cào làm mốc quy đổi cho các thời điểm tương đối.

---

## 3. Cơ Chế Ánh Xạ Sang Bản Ghi Bronze (`BronzeMapper`)

Lớp [`BronzeMapper`](../../crawler/src/roombeacon_crawler/mappers/bronze_mapper.py) chịu trách nhiệm kết hợp dữ liệu giữa Card và Detail:

### Nguyên tắc ưu tiên địa chỉ:
- `location_raw` trên Card thường chỉ là cấp Quận/Thành phố (ví dụ: *"Quận 7, Hồ Chí Minh"*).
- `address_raw` từ Detail Page chứa địa chỉ cụ thể chi tiết hơn (ví dụ: *"Số 12 đường Lý Phục Man, Phường Bình Thuận, Quận 7"*).
- `BronzeMapper` ưu tiên `address_raw` khi có dữ liệu từ Detail Page. `location_raw` vẫn được bảo toàn trong payload thô nhưng không bị giả định là địa chỉ số nhà chi tiết.

### Bảo toàn nguyên trạng giá trị thô:
- Mọi trường đều giữ nguyên chuỗi văn bản gốc (`price_raw`, `area_raw`, `title_raw`).
- Trích xuất kỹ thuật sơ bộ (`price_amount`, `area_value`) chỉ phục vụ hỗ trợ lưu trữ kiểu dữ liệu cột trong MySQL; **tuyệt đối không coi đây là dữ liệu đã làm sạch nghiệp vụ**. Toàn bộ logic làm sạch ngữ nghĩa thuộc về tầng Silver.
