# Kiến Trúc MinIO Object Storage (Object Storage Architecture)

> **Plane:** Storage
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** PARTIAL
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [STORAGE_OVERVIEW.md](STORAGE_OVERVIEW.md), [ASSET_PIPELINE.md](ASSET_PIPELINE.md)

---

## 1. Vai Trò Kiến Trúc của MinIO Trong RoomBeacon

MinIO Object Storage được tích hợp nhằm giải quyết bài toán:
- **Tách rời dữ liệu nhị phân (Binary Streams) khỏi RDBMS:** Cơ sở dữ liệu MySQL và các tệp Parquet chỉ lưu URL hoặc Object Key trỏ tới hình ảnh; dữ liệu nhị phân nặng được lưu trên MinIO, giúp database duy trì kích thước tối ưu.
- **Tương thích API S3:** Cho phép mã nguồn sử dụng SDK AWS S3 chuẩn hóa, dễ dàng chuyển đổi sang AWS S3, Cloudflare R2 hoặc Google Cloud Storage trong tương lai mà không cần viết lại mã nguồn.

---

## 2. Danh Mục Các Buckets

| Tên Bucket | Trạng thái | Mục đích sử dụng | Định dạng đối tượng lưu trữ |
|---|:---:|---|---|
| **`roombeacon-assets`** | **IMPLEMENTED** | Lưu trữ toàn bộ hình ảnh phòng trọ đã qua kiểm duyệt an toàn bởi Asset Pipeline. Dung lượng hiện tại đạt **~3.5 GB** (theo báo cáo của chủ dự án ngày 2026-10-06). | Tệp hình ảnh nhị phân (`.jpg`, `.png`, `.webp`, `.gif`). |
| **`roombeacon-raw`** | **PLANNED** | Lưu trữ bản sao lưu nén của các trang HTML thô từ Crawler để phục vụ audit và re-crawl mà không cần gọi lại mạng. | Tệp `.html.gz` hoặc `.warc`. |
| **`roombeacon-quarantine`** | **PLANNED** | Lưu trữ các tệp tải về bị nghi ngờ mã độc, tệp vượt kích thước hoặc sai cấu trúc nhị phân để phục vụ điều tra an ninh. | Tệp nhị phân bị cô lập. |
| **`roombeacon-exports`** | **PLANNED** | Lưu trữ các tệp Parquet nén trích xuất từ các bản ghi lịch sử cũ của MySQL theo chính sách lưu trữ dài hạn (Cold Storage). | Tệp `.parquet` nén Snappy / ZSTD. |

---

## 3. Quy Ước Khóa Đối Tượng (Object Key Convention)

Trong bucket `roombeacon-assets`, mọi tệp hình ảnh được đặt tên theo cấu trúc định danh bất biến:

$$\text{Object Key} = \text{source\_code} / \text{platform\_post\_id} / \text{img\_}\langle\text{position}\rangle\text{\_}\langle\text{url\_hash}\rangle.\langle\text{ext}\rangle$$

*Ví dụ:* `phongtro123/651221/img_1_a30cf423.jpg`

Cấu trúc này đảm bảo:
- Dễ dàng tra cứu toàn bộ ảnh thuộc về một bài đăng;
- Khử trùng lặp ảnh (Deduplication) dựa trên mã băm SHA-256 của URL;
- Tính Idempotent: Khi chạy lại, nếu tệp đã tồn tại trên MinIO, Reconciler sẽ bỏ qua và không tải lại.

---

## 4. Cấu Hình Phân Quyền & Tự Động Khởi Tạo (Provisioning & Security)

Hệ thống MinIO được khởi tạo tự động trong quá trình `docker compose up` thông qua:
1. Container dịch vụ: `roombeacon-minio` (Port API: 9000, Web Console: 9001).
2. Script khởi tạo: [`infrastructure/minio/bootstrap.sh`](../../infrastructure/minio/bootstrap.sh).
3. Chính sách phân quyền tối thiểu (Least Privilege):
   - Crawler và Asset Reconciler chỉ được cấp quyền `s3:PutObject` và `s3:GetObject` trên bucket `roombeacon-assets/*`.
   - Client không có quyền `ListBucket`, không có quyền tạo bucket và không có quyền xoá đối tượng (`s3:DeleteObject`).
