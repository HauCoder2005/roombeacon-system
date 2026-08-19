# 07 — Pagination and Date Policy

Tài liệu này mô tả cách thức phân trang và chính sách kiểm soát thời gian đăng tin (Date Cutoff Policy).

---

## 1. Cơ chế Phân trang (`NhatotPagination`)

* **URL Pattern:** Nhà Tốt hỗ trợ phân trang qua tham số `?page=N`.
  * Trang 1: `https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh`
  * Trang 2: `https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2`
* **Điều kiện dừng phân trang:**
  1. Trang hiện tại không còn tin đăng (`len(cards) == 0`).
  2. Đạt giới hạn số trang tối đa (`current_page >= max_pages`).
  3. Đạt giới hạn tổng số bản ghi cần thu thập (`len(records) >= max_total_records`).
  4. DateCutoffPolicy phát hiện tin đã cũ hơn ngưỡng `date_from`.

---

## 2. Date Cutoff Policy & Date Interpreter

* **`NhatotDateInterpreter`:** Chuyển đổi các biểu thức ngôn ngữ tự nhiên (`"Hôm nay"`, `"2 giờ trước"`, `"3 ngày trước"`, `"12/08/2026"`) thành đối tượng `datetime` (UTC) phục vụ điều khiển tiến trình.
* **Quy tắc bảo toàn:** Dữ liệu gốc trong `ListingCardRaw.posted_at_raw` và `RentalBronzeRecord.posted_at_raw` vẫn được bảo lưu nguyên vẹn 100%.
