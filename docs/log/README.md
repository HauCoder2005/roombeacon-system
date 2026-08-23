# NHẬT KÝ SỰ CỐ KỸ THUẬT (ROOMBEACON ENGINEERING INCIDENT LOG)

Thư mục này được sử dụng để lưu trữ lịch sử, tài liệu hóa và quản lý các sự cố kỹ thuật, lỗi phát sinh trong quá trình vận hành hệ thống **RoomBeacon**.

---

## 1. Mục Đích & Ý Nghĩa

- **Lưu trữ tri thức kỹ thuật**: Ghi lại chi tiết bối cảnh, triệu chứng và nguyên nhân gốc của các sự cố đã xảy ra.
- **Minh bạch quy trình xử lý**: Mô tả rõ ràng cách thức điều tra, phương án khắc phục, kết quả kiểm thử và xác minh trên môi trường vận hành.
- **Phòng ngừa tái diễn (Post-mortem & Prevention)**: Đưa ra các giải pháp phòng vệ kiến trúc và kiểm thử hồi quy để ngăn chặn sự cố lặp lại.
- **Truy vết lịch sử gỡ lỗi (Debugging History)**: Giúp các kỹ sư và nhà phát triển dễ dàng nắm bắt các bài học kinh nghiệm trong quá khứ.

---

## 2. Quy Ước Đặt Tên Tệp & Định Dạng

Mỗi sự cố kỹ thuật được ghi nhận thành **một tệp tin Markdown độc lập** theo quy tắc:

```
YYYY-MM-DD_<short-issue-name>.md
```

*Ví dụ*: `2026-08-23_area-value-overflow.md`

> [!IMPORTANT]
> **Phân biệt rõ ràng giữa Incident Log và Runtime Application Log**:
> - Thư mục `docs/log/` **CHỈ CHỨA** các tài liệu báo cáo sự cố kỹ thuật (Markdown reports) phục vụ con người đọc và tra cứu.
> - **KHÔNG ĐƯỢC** ghi các nhật ký chạy ứng dụng (runtime logs, raw container logs, streaming logs) vào thư mục này. Nhật ký runtime được quản lý độc lập qua Airflow, Docker logs và `structlog`.
> - **BẢO MẬT**: Tuyệt đối không lưu trữ thông tin nhạy cảm (mật khẩu, tokens, credentials, DSNs, số điện thoại cá nhân) trong các báo cáo sự cố.

---

## 3. Danh Mục Sự Cố Kỹ Thuật (Incident Index)

| Ngày (Date) | Tên Sự Cố (Incident) | Thành Phần (Component) | Trạng Thái (Status) | Báo Cáo Chi Tiết (Report Link) |
| :--- | :--- | :--- | :--- | :--- |
| 2026-08-23 | area_value overflow (DataError 1264) | Bronze Persistence / Airflow | **RESOLVED** | [2026-08-23_area-value-overflow.md](2026-08-23_area-value-overflow.md) |
| 2026-08-23 | PhongTro123 Field Extraction Contamination | Crawler / PhongTro123 Parser | **RESOLVED** | [2026-08-23_phongtro123-field-extraction-contamination.md](2026-08-23_phongtro123-field-extraction-contamination.md) |

*(Khi phát sinh sự cố mới, hãy tạo tệp báo cáo theo mẫu và bổ sung vào bảng danh mục trên).*
