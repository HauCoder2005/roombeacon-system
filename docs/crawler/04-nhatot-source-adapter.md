# 04 — Nhà Tốt Source Adapter

Tài liệu này mô tả chi tiết kiến trúc Source Adapter dành cho website **Nhà Tốt** (`nhatot.com`).

---

## 1. Vai trò của Source Adapter

Source Adapter (`NhatotSourceAdapter`) đóng vai trò trung tâm đóng gói các đặc thù công nghệ của nguồn Nhà Tốt:

* **Tên nguồn & Domain:** `source_name = "nhatot"`, `domain = "nhatot.com"`.
* **Chiến lược Fetch mặc định:** `FetchStrategy.BROWSER` (sử dụng Playwright Chromium để render client-side JavaScript).
* **Kết nối Modules:**
  * `NhatotListingParser`: Bóc tách trang danh sách tin phòng trọ TP.HCM.
  * `NhatotDetailParser`: Bóc tách trang chi tiết tin đăng.
  * `NhatotMetadataParser`: Bóc tách meta tags và schema.org JSON-LD.
  * `NhatotPagination`: Xây dựng và điều hướng URL phân trang (`?page=N`).
  * `NhatotDateInterpreter`: Diễn giải mốc thời gian phục vụ DateCutoffPolicy.

---

## 2. Cấu trúc Source Package

```text
sources/nhatot/
├── __init__.py
├── adapter.py              # NhatotSourceAdapter
│
├── selectors/              # Tập trung hóa CSS / TestID Selectors
│   ├── __init__.py
│   ├── listing_selectors.py
│   └── detail_selectors.py
│
├── parsers/                # Bộ xử lý bóc tách HTML
│   ├── __init__.py
│   ├── listing_parser.py
│   ├── detail_parser.py
│   └── metadata_parser.py
│
└── discovery/              # Cơ chế tìm kiếm & phân trang
    ├── __init__.py
    ├── pagination.py
    └── date_interpreter.py
```
