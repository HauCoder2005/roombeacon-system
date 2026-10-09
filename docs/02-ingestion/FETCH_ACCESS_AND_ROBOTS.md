# Chính Sách Truy Cập, Robots & Bảo Vệ SSRF (Fetch, Access & Robots Policy)

> **Plane:** Ingestion
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [CRAWLER_ARCHITECTURE.md](CRAWLER_ARCHITECTURE.md), [../07-engineering/SECURITY.md](../07-engineering/SECURITY.md)

---

## 1. Bảo Vệ An Toàn Mạng & Chống SSRF (`URLValidator`)

Mọi URL trước khi được hệ thống fetch (cho cả listing page, detail page và ảnh asset) đều phải vượt qua bộ kiểm tra an toàn [`URLValidator`](../../crawler/src/roombeacon_crawler/validators/url_validator.py):

- **Giao thức:** Chỉ chấp nhận `http://` hoặc `https://`.
- **Chặn Loopback:** Từ chối `localhost`, `127.0.0.1`, `::1`.
- **Chặn Mạng Nội Bộ (RFC 1918 Private IPs):** Từ chối toàn bộ các dải IP `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- **Chặn Dải Link-Local & Multicast:** Từ chối `169.254.0.0/16`, `224.0.0.0/4`.
- **Chặn Cloud Metadata Service:** Chặn tuyệt đối địa chỉ metadata của AWS / GCP / Azure (`169.254.169.254`), ngăn chặn triệt để tấn công đánh cắp IAM credentials qua SSRF.

---

## 2. Chính Sách Tuân Thủ Đạo Đức Cào Web (`RobotsPolicy`)

RoomBeacon thực thi nghiêm ngặt tiêu chuẩn **RFC 9309 (Robots Exclusion Protocol)** thông qua [`RobotsPolicy`](../../crawler/src/roombeacon_crawler/policies/robots_policy.py):

- Trước khi cào một nguồn, hệ thống tải tệp `robots.txt` của domain tương ứng và phân tích cú pháp.
- Áp dụng kiểm tra quyền truy cập cho User-Agent cụ thể của RoomBeacon hoặc User-Agent wildcard `*`.
- **Xử lý khi bị từ chối (DENIED):** Nếu đường dẫn bị cấm trong `robots.txt`, crawler lập tức dừng an toàn phiên cào cho target đó, ghi log kiểm toán và trả trạng thái `SKIPPED_ROBOTS_DENIED` về Airflow mà không cố tình vượt rào.
- **Tuân thủ Crawl-Delay:** Nếu `robots.txt` chỉ định `Crawl-delay`, crawler tự động điều chỉnh khoảng nghỉ giữa các request (`request_delay_seconds`) bằng hoặc lớn hơn giá trị quy định.

---

## 3. Quản Lý Sức Khỏe Nguồn & Circuit Breaker (`SourceHealthPolicy`)

Để tránh gửi dồn dập request khi website nguồn đang gặp sự cố hoặc chặn IP, hệ thống duy trì mô hình **Circuit Breaker** theo dõi sức khỏe từng nguồn:

- **Bộ đếm lỗi liên tiếp (Consecutive Failures):**
  - Nếu một nguồn gặp lỗi mạng liên tiếp (Timeout, 502/503 Bad Gateway, 429 Too Many Requests, hoặc Cloudflare Captcha Challenge), bộ đếm lỗi của nguồn sẽ tăng lên.
  - Khi vượt ngưỡng cấu hình (mặc định 3 lần), trạng thái nguồn chuyển sang `DEGRADED` hoặc `COOLDOWN`.
- **Thời gian hồi phục (Cooldown Period):**
  - Khi rơi vào trạng thái `COOLDOWN`, nguồn sẽ bị đóng băng tạm thời (ví dụ 30 đến 60 phút). Task kiểm tra điều kiện của Airflow (`03_crawl_check_eligibility`) sẽ tự động bỏ qua (Skip) nguồn này cho đến khi hết thời gian chờ, cho phép website nguồn hồi phục và tránh làm IP của crawler bị đưa vào danh sách đen vĩnh viễn.
- **Tự phục hồi (Half-Open Recovery):** Sau thời gian cooldown, crawler cho phép 1 phiên cào thăm dò (probe run) với số trang tối thiểu (`max_pages = 1`). Nếu thành công, nguồn được khôi phục về trạng thái `HEALTHY`.

---

## 4. Chính Sách Thử Lại & Khoảng Nghỉ (`RetryPolicy` & `RateLimitPolicy`)

- **Exponential Backoff:** Khi gặp lỗi tạm thời (Transient Errors: ngắt kết nối socket, DNS tạm thời lỗi), hệ thống thử lại tối đa 3 lần với thời gian chờ tăng theo hàm mũ kèm jitter ngẫu nhiên:
  $$t_{\text{wait}} = \text{base\_delay} \times 2^{\text{attempt}} + \text{random\_jitter}$$
- **Phân định lỗi vĩnh viễn (Terminal Errors):** Lỗi HTTP 404 (Not Found), 410 (Gone), 403 (Forbidden do IP block) được đánh dấu là lỗi vĩnh viễn và không thử lại vô ích.
