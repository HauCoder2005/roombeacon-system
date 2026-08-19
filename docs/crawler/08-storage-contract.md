# 08 — Storage Contract

Tài liệu này quy định hợp đồng lưu trữ (Storage Contract) cho hai lớp dữ liệu **RAW** (Object Storage) và **BRONZE** (Structured Datasets).

---

## 1. RAW Storage Contract (Tương lai với MinIO)

Mục tiêu lưu trữ: Bảo toàn toàn bộ snapshot phản hồi thô (HTML/JSON/Metadata) để có thể re-parse bất cứ lúc nào mà không cần gửi request lại tới nguồn.

### Cấu trúc Key trên Object Storage:

```text
raw/
  <source>/
    listing/
      YYYY-MM-DD/
        <run_id>/
          page-000001.html
          page-000002.html

raw/
  <source>/
    detail/
      YYYY-MM-DD/
        <run_id>/
          <listing_id>.html

assets/
  <source>/
    YYYY-MM-DD/
      <run_id>/
        <listing_id>/
          img-001.jpg
```

---

## 2. BRONZE Storage Contract (Local / Parquet)

Mục tiêu: Lưu trữ các bản ghi đã cấu trúc hóa ở dạng schema thô (`RentalBronzeRecord`), chia theo phiên chạy (`run_id`).

### Cấu trúc thư mục:

```text
data/bronze/
  <source>/
    YYYY-MM-DD/
      <run_id>/
        listings.json       # Danh sách các RentalBronzeRecord
        metadata.json       # Audit trail CrawlMetadata của tất cả requests
        manifest.json       # Tổng kết CrawlRunResult
```

* **Tính độc lập:** Mỗi lần chạy sinh một `run_id` duy nhất (ví dụ `run_20260819_091500`), không ghi đè lên các phiên crawl cũ.
* **Tương thích Downstream:** Cấu trúc JSON / Parquet tại lớp Bronze được thiết kế để DuckDB có thể đọc trực tiếp phục vụ Data Cleaning $\rightarrow$ Silver Layer.
