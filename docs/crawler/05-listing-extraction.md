# 05 — Listing Extraction

Tài liệu này mô tả chi tiết cơ chế bóc tách dữ liệu từ trang danh sách (Listing Page) của Nhà Tốt.

---

## 1. Nguyên tắc bóc tách

1. **Phạm vi Main Container:** Parser định vị vùng `MAIN_CONTAINER` trước (`ListAds_ListAds`, `list-view`, `data-testid="list-ads"`) để loại trừ sidebar, tin quảng cáo gợi ý và footer.
2. **Nguyên tắc Card nguyên tử:** Toàn bộ các trường của một `ListingCardRaw` (`title_raw`, `price_raw`, `area_raw`, `location_raw`, `detail_url`) bắt buộc phải xuất phát từ **cùng một node card**. Tuyệt đối không quét mảng rời rạc rồi zip/index.
3. **Bảo toàn dữ liệu thô:**
   * `price_raw`: Chuỗi gốc (ví dụ: `"3,2 triệu/tháng"`, `"950.000 đ/tháng"`).
   * `area_raw`: Chuỗi gốc (ví dụ: `"30 m²"`).
   * `location_raw`: Chuỗi gốc (ví dụ: `"Quận 12"`).
   * `posted_at_raw`: Chuỗi gốc (ví dụ: `"2 giờ trước"`).

---

## 2. Validation & Filter quy tắc

* **Price Validation:** Áp dụng `PRICE_REGEX` với word boundary `\b`, loại bỏ lỗi nhận diện sai như `"6 K"`, `"10 K"`.
* **Area Validation:** Chỉ chấp nhận định dạng diện tích thực tế `\b\d+(?:[.,]\d+)?\s*m(?:²|2)\b`.
* **Title Cleaning:** Tự động cắt bỏ các tiền tố badge ưu tiên như `"Tin ưu tiên 6"`, `"Tin ưu tiên 10"`, `"Đã xác thực"` nhưng giữ nguyên nội dung tiêu đề và emoji.
* **Location Cleaning:** Tách bỏ các mốc thời gian và diện tích dính kèm nếu có.
