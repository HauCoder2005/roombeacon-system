# RoomBeacon — Generic Multi-Source Crawler Architecture

## 1. Tổng quan Kiến trúc Đa nguồn (Architecture Overview)

RoomBeacon Crawler được thiết kế theo mô hình **Generic Plugin-based Source Adapters**, tách biệt hoàn toàn giữa lõi điều phối chung và các quy tắc bóc tách đặc thù từng website.

```text
Airflow UI
    │
    │ runtime URL
    ▼
roombeacon_crawler DAG
    │
    ▼
URLValidator (Generic Syntax & SSRF Protection)
    │
    ▼
SourceRegistry (Central Registry & Resolver)
    ├── 5 adapters hiện hữu
    └── 7 adapters mới (3 active Batch 1, 4 controlled-disabled)
    │
    ▼
Generic RobotsPolicy (Evaluates robots.txt directly from URL/domain)
    ├── DENIED   ──► Controlled Stop (Airflow Task SKIPPED)
    └── ALLOWED  ──► Proceed
          │
          ▼
StrategySelector (HTTP / Playwright Browser)
          │
          ▼
Site-specific Listing & Detail Parsers
          │
          ▼
Common Raw Models (ListingCardRaw, ListingDetailRaw)
          │
          ▼
CrawlRunResult & Bronze Dataset (`data/bronze/<source>/...`)
```

---

## 2. Các thành phần chính

1. **`URLValidator` ([validators/url_validator.py](../../crawler/src/roombeacon_crawler/validators/url_validator.py)):**
   Chịu trách nhiệm kiểm tra an toàn kỹ thuật (HTTP/HTTPS, cú pháp, chặn loopback, chặn RFC 1918 private IPs, chặn cloud metadata). Hoàn toàn độc lập với domain website nguồn.

2. **`BaseSourceAdapter` ([sources/base.py](../../crawler/src/roombeacon_crawler/sources/base.py)):**
   Hợp đồng (base abstraction) chuẩn hóa cho mọi adapter nguồn: `SOURCE_NAME`, `DOMAINS`, `supports(url)`, `listing_parser`, `detail_parser`, `metadata_parser`, `pagination`, `date_interpreter`.

3. **`SourceRegistry` ([sources/registry.py](../../crawler/src/roombeacon_crawler/sources/registry.py)):**
   Nơi đăng ký tập trung và phân giải adapter (`resolve(url) -> BaseSourceAdapter`). Ném ra `UnsupportedSourceError` nếu domain chưa được hỗ trợ.

4. **`CrawlRunner` ([pipeline/crawl_runner.py](../../crawler/src/roombeacon_crawler/pipeline/crawl_runner.py)):**
   Orchestrator độc lập, không hardcode bất kỳ logic nguồn nào.

5. **`RobotsPolicy` ([policies/robots_policy.py](../../crawler/src/roombeacon_crawler/policies/robots_policy.py)):**
   Đánh giá quyền truy cập từ `robots.txt` tự động theo hostname của URL mục tiêu.

---

## 3. Quy trình thêm Nguồn Mới (How to Add a New Source in 5 Steps)

1. **Tạo thư mục nguồn mới:** Tạo `crawler/src/roombeacon_crawler/sources/<new_source>/`.
2. **Xây dựng parsers và discovery:** Triển khai `listing_parser.py`, `detail_parser.py`, `pagination.py`, `date_interpreter.py` bóc tách dữ liệu vào `ListingCardRaw` & `ListingDetailRaw`.
3. **Kế thừa `BaseSourceAdapter`:** Tạo `adapter.py` khai báo `SOURCE_NAME`, `DOMAINS`, `DEFAULT_BASE_URL` và khởi tạo các thành phần ở Bước 2.
4. **Đăng ký:** đặt package có `adapter.py`; `SourceDiscovery` auto-discover
   adapter class được định nghĩa trong module đó. Không sửa registry thủ công.
5. **Thêm unit tests:** Tạo `tests/test_new_source.py` kiểm thử parser và integration.

*(Không cần sửa Airflow DAG, CrawlRunner, URLValidator, RobotsPolicy hay Fetchers)*.

## 4. Source index hiện tại

| Source key | Activation | Listing/detail status |
|---|---|---|
| `nhatot`, `nhatrovn`, `phongtro123`, `batdongsan`, `muaban` | existing policy | regression preserved |
| `chothuenha`, `tromoi` | Batch 1 active | normal-run PASS; robots-compatible query pagination enabled |
| `guland` | Batch 1 active | access challenge/cooldown; JS pagination remains unmodeled |
| `chothuephongtro`, `mogi` | Batch 2 active | page 1/2 acquisition and non-overlap verified |
| `cafeland` | Batch 3 active | audited `/page-N/` route and acquisition verified |
| `phongtrotoanquoc` | blocked/disabled | no valid text robots policy or verified server cards |
