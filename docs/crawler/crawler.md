# RoomBeacon Crawler — Fetch / Capture Mechanism

## 1. Tổng quan

Tài liệu này mô tả cơ chế **Fetch / Capture** của RoomBeacon Crawler.

Fetch / Capture Box chịu trách nhiệm:

- nhận URL cần crawl;
- xác định chiến lược fetch phù hợp với từng source;
- thực hiện HTTP request hoặc browser rendering;
- capture response;
- phân loại response;
- quyết định tiếp tục parse, cooldown, retry hoặc stop;
- không để response lỗi hoặc Cloudflare Challenge đi xuống Extract Box.

Kiến trúc tổng quát:

```text
Source Adapter
      ↓
Discovery Box
      ↓
Fetch / Capture Box
      ↓
Extract Box
      ↓
Schema Mapping Box
      ↓
Commit Box
```

Trong đó tài liệu này tập trung vào:

```text
Fetch / Capture Box
```

---

# 2. Vấn đề ban đầu

RoomBeacon ban đầu sử dụng HTTPX để crawl:

```text
RoomBeacon
    ↓
HTTPX
    ↓
Website
```

Source thử nghiệm:

```text
https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh
```

Kết quả:

```text
HTTP Status  : 403
Server       : cloudflare
Crawl Status : cloudflare_challenge
Action       : stop
```

HTML response chứa:

```html
<title>Just a moment...</title>
```

và:

```text
challenges.cloudflare.com
```

Điều này cho thấy response nhận được không phải HTML listing thực tế.

Flow thực tế:

```text
RoomBeacon
    ↓
HTTPX
    ↓
Cloudflare
    ↓
403
    ↓
Cloudflare Challenge
    ↓
STOP
```

Do đó không thể đưa response này xuống Parser.

---

# 3. Vì sao không được Parse ngay sau Fetch?

Crawler không được thiết kế theo kiểu:

```text
URL
 ↓
Fetch
 ↓
Parser
```

Bởi vì Fetch có thể trả:

```text
200 OK
403 Forbidden
404 Not Found
429 Too Many Requests
500 Server Error
Cloudflare Challenge
```

Nếu HTML Cloudflare Challenge được đưa trực tiếp vào Parser:

```text
Cloudflare HTML
      ↓
RentalParser
      ↓
Sai dữ liệu
```

Do đó RoomBeacon sử dụng:

```text
Fetch
 ↓
Capture
 ↓
Response Classifier
 ↓
Decision
 ↓
Parser
```

Parser chỉ được chạy khi response hợp lệ.

---

# 4. Source-Aware Fetch Strategy

RoomBeacon không sử dụng một phương thức fetch duy nhất cho tất cả website.

Mỗi source có thể yêu cầu một strategy riêng.

Hai strategy hiện tại:

```text
HTTP
BROWSER
```

Kiến trúc:

```text
Source
  ↓
Strategy Selector
  ↓
┌──────────────────────────────┐
│                              │
▼                              ▼
HTTP Fetcher              Browser Fetcher
HTTPX                     Playwright
│                              │
└──────────────┬───────────────┘
               ↓
       CapturedResponse
```

---

# 5. HTTP Fetcher

HTTP Fetcher sử dụng:

```text
HTTPX
```

Phù hợp với:

- website server-rendered đơn giản;
- public HTML;
- public endpoint;
- API;
- source không yêu cầu browser runtime;
- source không yêu cầu JavaScript để render nội dung.

Flow:

```text
URL
 ↓
HttpFetcher
 ↓
HTTPX
 ↓
HTTP Response
 ↓
CapturedResponse
```

HTTP Fetcher không chịu trách nhiệm:

```text
Parse HTML
Retry policy
Cloudflare detection
Data cleaning
Database
Storage
```

HTTP Fetcher chỉ chịu trách nhiệm:

```text
Request
+
Response Capture
```

---

# 6. Browser Fetcher

Một số website cần browser thật để render JavaScript.

RoomBeacon sử dụng:

```text
Playwright
+
Chromium
```

Flow:

```text
URL
 ↓
BrowserFetcher
 ↓
Playwright
 ↓
Chromium
 ↓
Website
 ↓
Rendered HTML
 ↓
CapturedResponse
```

BrowserFetcher phù hợp với:

- website render bằng JavaScript;
- SPA;
- dynamic content;
- website cần browser runtime;
- source mà HTTP client thông thường không lấy được nội dung thực tế.

---

# 7. Thử nghiệm với Nhà Tốt

Source:

```text
nhatot.com
```

được thử nghiệm với nhiều strategy.

## 7.1 HTTPX

```text
HTTPX
 ↓
Cloudflare
 ↓
403
```

Kết quả:

```text
Fetch Strategy : http
HTTP Status    : 403
Crawl Status   : cloudflare_challenge
Action         : stop
```

---

## 7.2 Playwright với Headless Mode

Cấu hình:

```python
headless=True
```

Flow:

```text
RoomBeacon
    ↓
Playwright
    ↓
Chromium Headless
    ↓
Cloudflare
```

Kết quả thử nghiệm:

```text
HTTP Status    : 403
Crawl Status   : cloudflare_challenge
Action         : stop
```

Browser đã chạy nhưng response vẫn là Cloudflare Challenge.

---

## 7.3 Playwright với Headed Mode

Cấu hình:

```python
headless=False
```

Chromium được mở với giao diện browser.

Flow:

```text
RoomBeacon
    ↓
Playwright
    ↓
Chromium Headed
    ↓
nhatot.com
```

Kết quả thử nghiệm:

```text
Fetch Strategy : browser
HTTP Status    : 200
Crawl Status   : success
Action         : parse
HTML Size      : ~1.2 MB
Server         : cloudflare
```

RoomBeacon đã nhận được HTML thực tế.

Flow lúc này:

```text
BrowserFetcher
      ↓
CapturedResponse
      ↓
ResponseClassifier
      ↓
SUCCESS
      ↓
FetchPolicy
      ↓
PARSE
```

---

# 8. Headless và Headed

## Headless Mode

```python
headless=True
```

Browser chạy không có cửa sổ giao diện.

Phù hợp với:

```text
Server
CI/CD
Container
Automation
Background processing
```

Ví dụ:

```text
Python
 ↓
Playwright
 ↓
Chromium Headless
 ↓
Website
```

---

## Headed Mode

```python
headless=False
```

Browser mở cửa sổ Chromium thực tế.

Phù hợp trong giai đoạn:

```text
Development
Debug
Testing
Observe browser behavior
```

Flow:

```text
Python
 ↓
Playwright
 ↓
Chromium GUI
 ↓
Website
```

---

# 9. Kết quả thực nghiệm hiện tại

Với Nhà Tốt:

```text
HTTPX
    ↓
403 Cloudflare Challenge
```

```text
Playwright
headless=True
    ↓
403 Cloudflare Challenge
```

```text
Playwright
headless=False
    ↓
200 SUCCESS
```

Do đó Source Policy hiện tại của Nhà Tốt:

```text
nhatot.com
→ BROWSER
```

Trong môi trường development:

```python
headless=False
```

---

# 10. Lưu ý quan trọng về Headed Mode

Không được hiểu:

```text
headless=False
=
Cloudflare bypass
```

Đây chỉ là kết quả thử nghiệm thực tế của source tại thời điểm hiện tại.

Website hoặc lớp bảo vệ phía trước source có thể thay đổi hành vi trong tương lai.

Vì vậy dù BrowserFetcher trả HTML, response vẫn phải đi qua:

```text
ResponseClassifier
```

Không được bỏ bước classify.

---

# 11. Source Policy

Mỗi source có thể khai báo strategy riêng.

Ví dụ:

```python
SOURCE_STRATEGIES = {
    "nhatot.com": FetchStrategy.BROWSER,
}
```

Source không được cấu hình:

```text
default
→ HTTP
```

Ví dụ:

```text
source-a.com
→ HTTP

source-b.com
→ HTTP

nhatot.com
→ BROWSER
```

---

# 12. Strategy Selector

Strategy Selector chịu trách nhiệm:

```text
URL
 ↓
Detect Domain
 ↓
Source Policy
 ↓
FetchStrategy
```

Ví dụ:

```text
https://www.nhatot.com/...
        ↓
hostname = www.nhatot.com
        ↓
normalize
        ↓
nhatot.com
        ↓
Source Policy
        ↓
BROWSER
```

Main không được tự hard-code:

```python
if "nhatot.com" in url:
    ...
```

Logic này thuộc:

```text
StrategySelector
```

---

# 13. CapturedResponse

Fetcher không trả dữ liệu rời rạc.

RoomBeacon sử dụng object:

```text
CapturedResponse
```

Các field cơ bản:

```text
url
final_url
status_code
html
headers
strategy
```

Ví dụ:

```python
CapturedResponse(
    url=url,
    final_url=page.url,
    status_code=200,
    html=html,
    headers=headers,
    strategy=FetchStrategy.BROWSER,
)
```

CapturedResponse chỉ là data object.

Không chứa:

```text
Parser logic
Retry logic
Cloudflare logic
Storage logic
Data cleaning
```

---

# 14. Response Classifier

Sau khi fetch:

```text
CapturedResponse
        ↓
ResponseClassifier
```

ResponseClassifier chuyển response thành:

```text
CrawlStatus
```

Mapping:

```text
2xx
→ SUCCESS

400
→ BAD_REQUEST

401
→ UNAUTHORIZED

403
→ ACCESS_DENIED

403 + Cloudflare Challenge
→ CLOUDFLARE_CHALLENGE

404
→ NOT_FOUND

429
→ RATE_LIMITED

5xx
→ SERVER_ERROR

Other
→ UNKNOWN
```

---

# 15. Cloudflare Challenge Detection

Cloudflare Challenge phải được detect trước khi xử lý `403` thông thường.

Một số indicator hiện tại:

```text
just a moment
challenges.cloudflare.com
cf-chl-
```

Flow:

```text
HTTP 403
    ↓
Inspect HTML
    ↓
Cloudflare indicators?
    │
    ├── YES
    │     ↓
    │ CLOUDFLARE_CHALLENGE
    │
    └── NO
          ↓
      ACCESS_DENIED
```

Ví dụ:

```text
403
+
<title>Just a moment...</title>
+
challenges.cloudflare.com
```

trở thành:

```text
CrawlStatus.CLOUDFLARE_CHALLENGE
```

---

# 16. Fetch Policy

ResponseClassifier chỉ trả trạng thái.

Quyết định tiếp theo thuộc:

```text
FetchPolicy
```

Mapping hiện tại:

```text
SUCCESS
→ PARSE

RATE_LIMITED
→ COOLDOWN

SERVER_ERROR
→ RETRY_LATER

ACCESS_DENIED
→ STOP

CLOUDFLARE_CHALLENGE
→ STOP

NOT_FOUND
→ STOP

BAD_REQUEST
→ STOP

UNAUTHORIZED
→ STOP

UNKNOWN
→ STOP
```

---

# 17. Cooldown Policy

Khi gặp:

```text
429 RATE_LIMITED
```

crawler không retry ngay.

Ví dụ cooldown:

```text
Attempt 1
→ 60 seconds

Attempt 2
→ 300 seconds

Attempt 3
→ 900 seconds

Attempt > 3
→ 1800 seconds
```

Server Error:

```text
min(30 * attempt, 120)
```

Policy chỉ tính cooldown.

Không tự:

```python
sleep(...)
```

bên trong policy.

---

# 18. Khi gặp Cloudflare Challenge

Flow:

```text
Cloudflare Challenge
        ↓
CLOUDFLARE_CHALLENGE
        ↓
FetchPolicy
        ↓
STOP
```

Crawler không thực hiện:

```text
403
 ↓
retry
 ↓
retry
 ↓
retry
 ↓
retry
```

Điều này giúp tránh gửi request không cần thiết.

---

# 19. Fetch / Capture Box Level 2

Kiến trúc chi tiết:

```text
                    Crawl Target
                         ↓
                    Source Policy
                         ↓
                 Strategy Selector
                         ↓
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
       HttpFetcher              BrowserFetcher
         HTTPX                  Playwright
            │                         │
            └────────────┬────────────┘
                         ↓
                  CapturedResponse
                         ↓
                 ResponseClassifier
                         ↓
                    CrawlStatus
                         ↓
                    FetchPolicy
                         ↓
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
      PARSE          COOLDOWN            STOP
        │                │
        ▼                ▼
     Extract         Retry Later
```

---

# 20. Tách Fetch và Extract

Fetch Box không extract dữ liệu.

Sai:

```text
BrowserFetcher
 ↓
Find title
Find price
Find area
Save database
```

Đúng:

```text
BrowserFetcher
      ↓
CapturedResponse
      ↓
SUCCESS
      ↓
Extract Box
```

Extract Box mới chịu trách nhiệm:

```text
HTML
 ↓
Parser
 ↓
CrawlRecord[]
```

---

# 21. Rental Parser

Parser chỉ được gọi nếu:

```text
CrawlStatus = SUCCESS
```

và:

```text
FetchAction = PARSE
```

Flow:

```text
Captured HTML
      ↓
RentalParser
      ↓
CrawlRecord[]
```

Một CrawlRecord có thể gồm:

```text
title
price
area
location
url
```

Parser không biết:

```text
HTTP 403
Cloudflare
Retry
Cooldown
Browser
HTTPX
```

---

# 22. RAW Capture

HTML lấy được từ website không nên bị bỏ sau khi Parser chạy.

Kiến trúc tương lai:

```text
BrowserFetcher
      ↓
CapturedResponse
      ├────────────────→ RAW Storage
      │
      ↓
Extract Box
      ↓
Schema Mapping
      ↓
BRONZE
```

RAW có thể chứa:

```text
HTML
JSON
Images
Metadata
Response information
```

---

# 23. Vì sao cần lưu RAW?

Nếu crawler:

```text
Fetch website
 ↓
Parse
 ↓
Discard HTML
```

và sau đó Parser có bug, crawler phải request website lại.

Không tối ưu.

RoomBeacon hướng tới:

```text
Fetch một lần
 ↓
Save RAW
 ↓
Parse nhiều lần khi cần
```

Ví dụ:

```text
RAW HTML
   ↓
Parser V1
   ↓
Sai

RAW HTML
   ↓
Parser V2
   ↓
Đúng
```

Không cần crawl source lại.

---

# 24. RAW và BRONZE

Trong kiến trúc RoomBeacon:

```text
RAW
```

là dữ liệu gần với source nhất.

Ví dụ:

```text
HTML
JSON
Images
```

Có thể lưu vào:

```text
MinIO Object Storage
```

Sau Extract và Schema Mapping:

```text
BRONZE
```

là dữ liệu đã được cấu trúc.

Ví dụ:

```text
JSON
CSV
Parquet
```

Flow:

```text
Website
 ↓
Fetch
 ↓
RAW
 ↓
Extract
 ↓
Schema Mapping
 ↓
BRONZE
```

---

# 25. Quan hệ với kiến trúc RoomBeacon tổng thể

```text
Crawler Execution Plane
│
├── Source Adapter
│
├── Discovery Box
│
├── Fetch / Capture Box
│       │
│       ├── Source Policy
│       ├── Strategy Selector
│       ├── HttpFetcher
│       ├── BrowserFetcher
│       ├── CapturedResponse
│       ├── ResponseClassifier
│       └── FetchPolicy
│
├── Extract Box
│
├── Schema Mapping Box
│
└── Commit Box
```

---

# 26. Current Development Flow

Trạng thái hiện tại:

```text
Source Adapter
      ↓
Discovery
      ↓
Strategy Selector
      ↓
BrowserFetcher
      ↓
Playwright Chromium
      ↓
CapturedResponse
      ↓
ResponseClassifier
      ↓
SUCCESS
      ↓
PARSE
```

Kết quả thực nghiệm:

```text
Fetch Strategy : browser
HTTP Status    : 200
Crawl Status   : success
Action         : parse
HTML Size      : ~1.2 MB
```

Fetch / Capture Box đã có thể chuyển response hợp lệ cho Extract Box.

---

# 27. Development Configuration

Trong môi trường local development hiện tại:

```text
Ubuntu Desktop
```

BrowserFetcher có thể sử dụng:

```python
headless=False
```

Mục đích:

- debug trực quan;
- quan sát Chromium;
- kiểm tra navigation;
- kiểm tra response;
- phát triển Extract Box;
- phát triển Parser.

---

# 28. Production Consideration

Production không nên mặc định dựa vào desktop GUI.

Ví dụ môi trường:

```text
Docker
Linux Server
Cloud VM
```

có thể không có graphical display.

Do đó:

```text
headless=False
```

hiện tại được xem là development strategy.

Production Browser Runtime cần được đánh giá riêng.

Đây thuộc:

```text
Infrastructure / Runtime Layer
```

không thuộc:

```text
Parser
```

---

# 29. Nguyên tắc thiết kế

RoomBeacon tuân theo nguyên tắc:

```text
Fetch
≠
Extract
```

```text
Extract
≠
Schema Mapping
```

```text
Schema Mapping
≠
Storage
```

Mỗi Box có trách nhiệm riêng.

---

# 30. Final Fetch Flow

```text
                    Source
                      ↓
                Source Adapter
                      ↓
                 Discovery
                      ↓
                 Crawl Target
                      ↓
                 Source Policy
                      ↓
               Strategy Selector
                      ↓
           ┌──────────┴──────────┐
           │                     │
           ▼                     ▼
       HTTP Fetcher         Browser Fetcher
         HTTPX               Playwright
           │                     │
           └──────────┬──────────┘
                      ↓
              CapturedResponse
                      ↓
              ResponseClassifier
                      ↓
                 CrawlStatus
                      ↓
                 FetchPolicy
                      ↓
          ┌───────────┼────────────┐
          │           │            │
          ▼           ▼            ▼
        PARSE      COOLDOWN        STOP
          │
          ▼
       Extract
          │
          ▼
    Schema Mapping
          │
          ▼
        Commit
          │
      ┌───┴────┐
      ▼        ▼
     RAW     BRONZE
```

---

# 31. Kết luận

RoomBeacon không xây crawler theo mô hình đơn giản:

```text
URL
→ GET
→ Parse
```

Mà sử dụng:

```text
URL
 ↓
Source Policy
 ↓
Strategy Selector
 ↓
Fetch
 ↓
Capture
 ↓
Classify
 ↓
Decision
 ↓
Extract
 ↓
Schema Mapping
 ↓
Commit
```

Điều này giúp:

- hỗ trợ nhiều loại source;
- HTTPX vẫn được sử dụng cho source đơn giản;
- Playwright được sử dụng cho source cần browser;
- Cloudflare Challenge được detect trước Parser;
- response lỗi không làm bẩn dữ liệu;
- một source bị lỗi không làm toàn bộ crawler dừng;
- RAW HTML có thể được lưu để parse lại;
- Fetch và Extract độc lập;
- dễ mở rộng thêm source mới;
- phù hợp với kiến trúc RoomBeacon hiện tại.

Kết quả demo hiện tại:

```text
BrowserFetcher
      ↓
HTTP 200
      ↓
CrawlStatus.SUCCESS
      ↓
FetchAction.PARSE
```

Do đó bước phát triển tiếp theo là:

```text
Extract Box
    ↓
RentalParser
    ↓
CrawlRecord[]
    ↓
Parse thử khoảng 50 rental records
```