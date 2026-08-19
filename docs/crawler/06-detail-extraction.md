# 06 — Detail Extraction

Tài liệu này mô tả cơ chế bóc tách thông tin chuyên sâu từ trang chi tiết tin đăng (Detail Page) nhằm phục vụ bước Data Processing và Analytics phía sau.

---

## 1. Mục tiêu bóc tách Detail

Trang chi tiết chứa nhiều thuộc tính quan trọng mà card tóm tắt không có:

* **Mô tả đầy đủ (`description_raw`):** Toàn văn nội dung người cho thuê đăng tải.
* **Địa chỉ chi tiết (`address_raw`):** Địa chỉ chi tiết tới số nhà / đường / phường.
* **Đặc tính bất động sản (`property_type_raw`, `furnishing_raw`, `deposit_raw`):** Loại phòng, nội thất, tiền cọc.
* **Thông tin người đăng (`seller_name_raw`, `seller_type_raw`):** Tên tài khoản, môi giới hoặc chính chủ.
* **Hình ảnh & Tiện ích (`image_urls_raw`, `amenities_raw`):** Danh sách URL ảnh thực tế và các tiện ích có sẵn (máy lạnh, máy giặt, ban công, gác lửng, v.v.).

---

## 2. Xử lý thiếu dữ liệu & Lỗi

* **Graceful Degradation:** Nếu một tin đăng không có tiện ích hoặc nội thất, parser gán `None` hoặc `[]`. Tuyệt đối không sinh dữ liệu giả hoặc suy đoán.
* **Detail Validator:** Kiểm tra trang chi tiết có thực sự chứa nội dung tin đăng hay là trang lỗi/404/challenge trước khi chuyển tiếp sang mapper.
