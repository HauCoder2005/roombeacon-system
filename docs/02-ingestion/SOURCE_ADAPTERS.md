# Ma Trận Bộ Điều Hợp Nguồn (Source Adapters Matrix)

> **Plane:** Ingestion
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [CRAWLER_ARCHITECTURE.md](CRAWLER_ARCHITECTURE.md), [FETCH_ACCESS_AND_ROBOTS.md](FETCH_ACCESS_AND_ROBOTS.md)

---

## 1. Cơ Chế Plugin-Based Source Adapters

Toàn bộ các nguồn thu thập trong RoomBeacon kế thừa lớp cơ sở [`BaseSourceAdapter`](../../crawler/src/roombeacon_crawler/sources/base.py) và được tự động đăng ký qua [`SourceRegistry`](../../crawler/src/roombeacon_crawler/sources/registry.py).

Mỗi adapter sở hữu độc lập:
- `listing_parser`: Bóc tách thẻ bài đăng trên danh mục;
- `detail_parser`: Bóc tách thông tin chi tiết trên trang tin;
- `pagination`: Quy tắc sinh URL trang kế tiếp;
- `date_interpreter`: Quy tắc chuyển đổi ngày đăng dạng văn bản tiếng Việt sang ISO-8601;
- `CAPABILITIES`: Khai báo tính năng hỗ trợ (`preferred_fetch_strategy`, `detail_fetch_supported`, `pagination_supported`).

---

## 2. Ma Trận Chi Tiết 12 Nguồn Dữ Liệu

Dưới đây là ma trận đối chiếu trực tiếp từ mã nguồn adapter và cấu hình seed thực tế:

| Mã nguồn (`source_code`) | Trạng thái Adapter | Phương thức Fetch | Thu thập Detail | Chiến lược Phân trang | Ngân sách Detail (`max_details`) | Chu kỳ Seed (`interval`) | Giới hạn Trang (`max_pages`) | Số tin trong Silver Parquet |
|:---|:---:|:---:|:---:|:---|:---:|:---:|:---:|---:|
| **`phongtro123`** | **Active** | HTTP (HTTPX) | Bật | Phân trang URL chuẩn `/tinh-thanh/...?page=N` | 1500 | 5 phút | 50 | **71,403** (53.9%) |
| **`chothuephongtro`** | **Active** | Browser (Playwright) | Bật | Phân trang query `?page=N` | 1000 | 5 phút | 10 | **35,796** (27.0%) |
| **`cafeland`** | **Active** | HTTP (HTTPX) | Bật | Phân trang đường dẫn `/page-N/` | 1000 | 5 phút | 10 | **9,984** (7.5%) |
| **`mogi`** | **Active** | Browser (Playwright) | Bật | Phân trang query `?cp=N` | 1000 | 5 phút | 10 | **9,782** (7.4%) |
| **`nhatot`** | **Active** | Browser (Playwright) | Bật | Cuộn tiến (Forward-only) danh mục | 20 | 10 phút | 50 | **2,642** (2.0%) |
| **`muaban`** | **Active** | Browser (Playwright) | Bật | Phân trang query | 20 | 60 phút | 50 | **1,621** (1.2%) |
| **`nhatrovn`** | **Active** | HTTP (HTTPX) | Bật | Phân trang query | 40 | 5 phút | 50 | **869** (0.7%) |
| **`tromoi`** | **Active** | HTTP (HTTPX) | Bật | Trang đầu hợp lệ; query bị robots giới hạn | 1000 | 5 phút | 10 | **255** (0.2%) |
| **`chothuenha`** | **Active** | HTTP (HTTPX) | Bật | Phân trang URL | 1000 | 5 phút | 10 | **84** (0.1%) |
| **`batdongsan`** | Controlled | HTTP (HTTPX) | **Tắt** (`detail=False`) | Phân trang trang web | 20 | 120 phút | 50 | 0 (Chỉ cào card) |
| **`guland`** | Challenged | HTTP (HTTPX) | Bật | Vướng phân trang JavaScript động | 1000 | 10 phút | 10 | 0 (Vướng truy cập) |
| **`phongtrotoanquoc`** | **Disabled** | Browser | **Tắt** | Chưa kiểm chứng thẻ danh mục | 1000 | 30 phút | 10 | 0 (Adapter tắt) |

---

## 3. Đặc Điểm Bóc Tách Theo Từng Nhóm Nguồn

### Nhóm 1: Nguồn HTTP Thuần Túy (Tốc Độ Cao)
- **`phongtro123`, `cafeland`, `nhatrovn`, `tromoi`, `chothuenha`:** Sử dụng HTTPX với User-Agent quay vòng, tốc độ tải nhanh, tiêu thụ ít CPU/RAM.
- `phongtro123` là nguồn chủ lực đóng góp hơn một nửa tổng số lượng tin đăng toàn hệ thống.
- `cafeland` và `nhatrovn` có điểm đặc thù: Toạ độ bản đồ gốc trên HTML chứa toạ độ mẫu (template coordinates) và bị lọc bỏ về `NULL` trong tầng xử lý.

### Nhóm 2: Nguồn Headless Browser (Chống Bot & JavaScript Động)
- **`chothuephongtro`, `mogi`, `nhatot`, `muaban`:** Bắt buộc sử dụng Playwright để vượt qua rào cản kiểm tra trình duyệt và kết xuất cây DOM hoàn chỉnh.
- `nhatot` (Nhà Tốt) áp dụng chiến lược cào cuộn tiến (Forward-Only) do cơ chế chống phân trang số truyền thống.

### Nhóm 3: Nguồn Kiểm Soát & Thách Thức
- `batdongsan`: Bị rào cản bảo vệ trang chi tiết nghiêm ngặt, chỉ cho phép bóc tách thông tin cơ bản trên card danh mục (`detail_fetch_supported = False`).
- `guland`: Yêu cầu click tải thêm qua JavaScript chưa được mô hình hóa hoàn toàn.
- `phongtrotoanquoc`: Được tắt có chủ đích (`ENABLED = False`) trong mã nguồn adapter để bảo vệ hàng đợi điều phối.
