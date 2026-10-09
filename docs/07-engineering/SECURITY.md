# Chính Sách Bảo Mật Hệ Thống (Security Architecture & Hardening)

> **Plane:** Engineering
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [DEPENDENCY_RULES.md](DEPENDENCY_RULES.md), [CONFIGURATION.md](CONFIGURATION.md)

---

## 1. Phòng Chống Tấn Công Server-Side Request Forgery (SSRF)

Do crawler và asset pipeline thực hiện các yêu cầu HTTP/HTTPS ra ngoài Internet dựa trên các URL trích xuất từ HTML của bên thứ ba, rủi ro SSRF là mối đe dọa hàng đầu.

### Rào chắn [`URLValidator`](../../crawler/src/roombeacon_crawler/validators/url_validator.py):
Mọi URL trước khi gọi mạng đều được phân giải DNS và kiểm tra:
1. **Chặn dải mạng Loopback:** Chặn `localhost`, `127.0.0.0/8`, `::1`.
2. **Chặn dải mạng nội bộ (RFC 1918):** Chặn `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
3. **Chặn Link-Local:** Chặn `169.254.0.0/16`.
4. **Chặn Cloud Metadata Endpoint:** Chặn tuyệt đối địa chỉ `http://169.254.169.254/` (AWS EC2 / Google Cloud / Azure metadata service), ngăn chặn kẻ tấn công lợi dụng crawler để lấy cắp token quyền quản trị đám mây.

---

## 2. Kiểm Thực An Toàn Tệp Nhị Phân (Asset Ingestion Hardening)

Để bảo vệ MinIO và hệ thống nội bộ khỏi các tệp mã độc hoặc tệp giả mạo:
1. **Kiểm tra chữ ký nhị phân (Magic Bytes):** Nhận diện đúng cấu trúc header nhị phân ở cấp độ byte (`JPEG`, `PNG`, `WebP`, `GIF`). Từ chối mọi tệp có đuôi ảnh nhưng nội dung thực tế là script (`.php`, `.exe`, `.html`, `.svg` chứa XSS).
2. **Phát hiện HTML/JSON giả mạo:** Từ chối các phản hồi có `Content-Type: text/html` (chống Cloudflare Captcha Page bị lưu nhầm thành ảnh).
3. **Giới hạn kích thước tệp:** Từ chối tải hoặc hủy kết nối ngay lập tức nếu kích thước vượt quá **15 MiB** (chống tấn công làm tràn bộ nhớ - Memory Exhaustion / Zip Bomb).

---

## 3. Quản Lý Bí Mật & Phân Quyền Tối Thiểu (Secrets & Least Privilege)

1. **Quản trị biến môi trường:** Mọi mật khẩu cơ sở dữ liệu và Access Key của MinIO đều được lưu trữ trong `.env` và nạp vào container, không commit mật khẩu lên Git.
2. **Chính sách MinIO IAM tối thiểu:** Crawler và Reconciler chỉ được gán quyền `s3:PutObject` và `s3:GetObject` trên bucket tài nguyên; không có quyền xóa đối tượng (`s3:DeleteObject`) hay tạo sửa đổi cấu hình bucket.
