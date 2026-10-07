# Tổng Quan Dự Án RoomBeacon (Project Overview)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md), [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

---

## 1. Bài Toán Kinh Doanh (Business Problem)

Thị trường cho thuê bất động sản (phòng trọ, căn hộ mini, nhà nguyên căn) tại Việt Nam hiện đang đối mặt với các vấn đề nhức nhối:

1. **Thông tin cực kỳ phân tán:** Tin đăng bị rải rác trên hàng chục website bất động sản và nhóm mạng xã hội độc lập. Người đi thuê phải duyệt qua nhiều trang web khác nhau với giao diện và định dạng hoàn toàn khác biệt.
2. **Tin rác, tin ảo và môi giới trùng lặp (Cross-Listing Spam):** Một căn phòng thực tế thường được nhiều môi giới sao chép và đăng lại trên nhiều sàn với mức giá chênh lệch, diện tích phóng đại hoặc tiêu đề giật gân để câu khách.
3. **Thiếu chuẩn hóa dữ liệu trầm trọng:**
   - *Giá thuê:* Không đồng nhất đơn vị (triệu/tháng, tr/th, nghìn/tháng, thỏa thuận, bao gồm/chưa bao gồm điện nước).
   - *Diện tích:* Bị lẫn lộn giữa kích thước phòng thực tế, diện tích sử dụng chung, hoặc kích thước tuyến tính ($4\times 5$ m).
   - *Địa chỉ:* Phần lớn chỉ ghi tên đường hoặc khu vực chung chung (Quận 7, gần trường ĐH), không có số nhà cụ thể.
4. **Thiếu định vị không gian chính xác:** Đa số các sàn cào giấu toạ độ thật của căn nhà, chỉ ghim toạ độ mặc định ở trung tâm quận hoặc toạ độ mẫu của website.
5. **Dữ liệu lỗi thời:** Tin đăng đã cho thuê từ lâu nhưng không được gỡ bỏ trên các website nguồn.

---

## 2. Tầm Nhìn Nền Tảng (Platform Vision)

RoomBeacon được xây dựng như một **Nền tảng Thu thập Dữ liệu & Trí tuệ Cho thuê Không gian (Location-Aware Rental Discovery & Data Intelligence Platform)**.

> **Tuyên ngôn sản phẩm:** *Thay vì chỉ trả về một danh sách kết quả tìm kiếm thô sơ, RoomBeacon cung cấp **Rental Intelligence** giúp người thuê nhà và chuyên gia phân tích trả lời câu hỏi: "Nên thuê ở đâu, mức giá nào là hợp lý và tại sao?"*

Hệ thống quản lý toàn bộ vòng đời dữ liệu khép kín:
$$\text{Thu thập đa nguồn} \longrightarrow \text{Lưu trữ lịch sử SCD2} \longrightarrow \text{Chuẩn hóa & Kiểm định} \longrightarrow \text{Khai phá & Mô hình hoá} \longrightarrow \text{Phục vụ thông minh}$$

---

## 3. Dữ Liệu Nguồn Thực Tế (Source Landscape)

Trong tập dữ liệu chuẩn hóa Silver ([`data/silver/rental_listings.parquet`](../../data/silver/rental_listings.parquet)), hệ thống ghi nhận **132,436 bài đăng duy nhất** từ **9 nguồn website thực tế** tại thị trường Việt Nam (dữ liệu thu thập trong khoảng 20/09/2026 – 30/09/2026):

| Mã nguồn (`source_code`) | Tên website | Số lượng tin | Tỷ trọng | Phương thức thu thập |
|:---|:---|---:|---:|:---:|
| `phongtro123` | PhongTrọ123 | 71,403 | 53.91% | HTTP Requests |
| `chothuephongtro` | ChoThuêPhòngTrọ | 35,796 | 27.03% | Headless Browser (Playwright) |
| `cafeland` | CafeLand | 9,984 | 7.54% | HTTP Requests |
| `mogi` | Mogi | 9,782 | 7.39% | Headless Browser (Playwright) |
| `nhatot` | Nhà Tốt (Chợ Tốt) | 2,642 | 2.00% | Headless Browser (Playwright) |
| `muaban` | MuaBán | 1,621 | 1.22% | Headless Browser (Playwright) |
| `nhatrovn` | NhàTrọVN | 869 | 0.66% | HTTP Requests |
| `tromoi` | TrọMới | 255 | 0.19% | HTTP Requests |
| `chothuenha` | ChoThuêNhà | 84 | 0.06% | HTTP Requests |
| **Tổng cộng** | **9 nguồn** | **132,436** | **100.0%** | — |

*(Ghi chú: Ngoài 9 nguồn trên, mã nguồn còn có adapter của `batdongsan` (thu thập card nhưng detail bị tắt), `guland` (bị vướng phân trang JS), và `phongtrotoanquoc` (đang tắt).)*

---

## 4. Từ Điển Thuật Ngữ (Glossary)

- **Listing Card:** Thẻ tóm tắt của tin đăng hiển thị trên trang danh mục (`listing_page`), chứa thông tin sơ bộ (tiêu đề, giá tóm tắt, diện tích, vị trí tổng quát).
- **Listing Detail:** Trang chi tiết của tin đăng (`detail_page`), chứa địa chỉ cụ thể, mô tả đầy đủ, tiện ích, toạ độ bản đồ nhúng và danh sách hình ảnh gốc.
- **SCD Type 2 (Slowly Changing Dimensions Type 2):** Kỹ thuật lưu trữ lịch sử trong kho dữ liệu, mỗi lần cào bài đăng sẽ tạo một phiên bản quan sát mới để theo dõi biến động theo thời gian thay vì ghi đè.
- **Observation:** Một bản ghi quan sát bất biến ghi lại trạng thái của bài đăng tại một thời điểm cào (`observed_at`) thuộc một phiên chạy (`crawl_run_id`).
- **Deferred Detail Backlog:** Hàng đợi lưu các URL trang chi tiết cần bóc tách bổ sung theo hạn ngạch và độ trễ hợp lý, tránh làm sập website nguồn.
- **Gazetteer (Danh mục Hành chính):** Cơ sở dữ liệu danh mục phân cấp Tỉnh/Thành phố $\rightarrow$ Quận/Huyện $\rightarrow$ Phường/Xã chuẩn của Việt Nam, dùng để ánh xạ và sửa đổi các tên phường cũ bị sáp nhập.
- **Template Hotspot (Toạ độ Mẫu):** Toạ độ GPS mặc định mà website nguồn gán cố định cho nhiều tin đăng khác nhau (ví dụ tâm quận hoặc toạ độ của tòa soạn). Bắt buộc phải bị lọc bỏ.
- **Fair Asset Scheduling:** Thuật toán điều phối tải tài nguyên ảnh có hạn ngạch công bằng giữa các nguồn, tránh việc nguồn có nhiều ảnh chiếm dụng toàn bộ băng thông tải.
- **Airflow Asset:** Đối tượng dữ liệu đại diện cho một dataset trong Apache Airflow 3, dùng để kích hoạt các DAG phụ thuộc khi dữ liệu được sản sinh mà không cần ghép chung DAG.
