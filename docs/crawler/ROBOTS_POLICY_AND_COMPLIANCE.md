# Tiêu chuẩn Tuân thủ Robots Exclusion Protocol (RFC 9309) và Kiến trúc RobotsPolicy tại RoomBeacon

> **Tài liệu Kỹ thuật & Chuẩn mực Kiến trúc Phỏng vấn Kỹ sư Cấp cao (Interview-Grade Architecture Document)**  
> **Dự án**: Hệ thống Thu thập Dữ liệu Bất động sản RoomBeacon (RoomBeacon Crawler System)  
> **Phiên bản Tiêu chuẩn**: RFC 9309 (Robots Exclusion Protocol)  
> **Ngày cập nhật**: 21/08/2026

---

## 1. Robots.txt là gì?

`robots.txt` là một tệp văn bản thuần (`text/plain`) được đặt tại gốc của một website nguồn (`/robots.txt` trên scheme và authority tương ứng) nhằm cung cấp các chỉ dẫn cho các tác tử thu thập thông tin tự động (Web Crawlers / Robots) về các phân vùng đường dẫn được phép (`Allow`) hoặc không được phép (`Disallow`) truy cập.

Tiêu chuẩn chính thức hiện đại của giao thức này được định nghĩa tại **RFC 9309 (Robots Exclusion Protocol)** do Internet Engineering Task Force (IETF) ban hành.

---

## 2. Robots.txt KHÔNG PHẢI là Cơ chế Ủy quyền Truy cập (Access Authorization)

Một sai lầm rất phổ biến trong thiết kế Crawler là xem `robots.txt` như một hệ thống phân quyền (Authorization / Firewall).

- **Bản chất của Robots.txt**: Là một **giao thức tự nguyện (Advisory Protocol / Politeness Agreement)** giữa chủ sở hữu website và crawler có đạo đức.
- **Robots.txt KHÔNG**:
  - Không ngăn chặn tấn công mạng hay thay thế cơ chế xác thực/phân quyền (OAuth, Session, Firewall, WAF).
  - Không đảm bảo rằng nếu URL được `Allow` thì máy chủ nội dung chắc chắn sẽ phục vụ `HTTP 200 OK`.
- **Nguyên tắc cốt lõi RoomBeacon**:
  - RoomBeacon tuân thủ 100% chỉ thị của `robots.txt` vì đạo đức kỹ thuật và trách nhiệm bảo vệ tài nguyên nguồn.
  - Tuy nhiên, hệ thống phân định độc lập tuyệt đối giữa **Tầng Thẩm định Robots (Robots Compliance Layer)** và **Tầng Kết nối Mạng Nội dung (Content Transport Layer)**.

---

## 3. Phân định Trạng thái Thẩm định: ALLOWED vs DENIED

Theo chuẩn RFC 9309, khi tài liệu `robots.txt` được tải thành công (`HTTP 200 OK`):

| Trạng thái | Điều kiện Kỹ thuật | Hành vi Hệ thống |
| :--- | :--- | :--- |
| **`ALLOWED`** | Nhóm User-Agent phù hợp cho phép URL (hoặc không có chỉ thị Disallow nào khớp). | URL vượt qua bước thẩm định robots, sẵn sàng chuyển tiếp sang bước cào nội dung. |
| **`DENIED`** | Khớp một chỉ thị `Disallow` cụ thể (và không bị ghi đè bởi chỉ thị `Allow` có độ ưu tiên cao hơn). | **DỪNG NGAY LẬP TỨC**. Tuyệt đối không gửi request mạng (kể cả HTTP hay BrowserFetcher) tới URL này. |

---

## 4. Phân định Trạng thái Hạ tầng: UNAVAILABLE vs UNREACHABLE

Khi tệp `robots.txt` không thể được tải bình thường qua mã `HTTP 200 OK`, RFC 9309 phân chia chính xác thành 2 trường hợp mang ngữ nghĩa hoàn toàn khác nhau:

```
                  +----------------------------------------------+
                  |         GỬI REQUEST /robots.txt              |
                  +----------------------+-----------------------+
                                         |
                +------------------------+------------------------+
                |                                                 |
         HTTP 400 - 499                                    HTTP 500 - 599
     (Client Error / WAF 403)                          (Server Error / Timeout)
                |                                                 |
                v                                                 v
   +--------------------------+                      +--------------------------+
   |   ROBOTS_UNAVAILABLE     |                      |    ROBOTS_UNREACHABLE    |
   | • Explicit Denial: NO    |                      | • Conservative Halt      |
   | • RFC 9309 2.3.1.2:      |                      | • RFC 9309 2.3.1.3:      |
   |   Assume NO restrictions |                      |   Assume COMPLETE DENY   |
   | • Tiến sang Content Fetch|                      | • Không gọi Content      |
   +--------------------------+                      +--------------------------+
```

---

## 5. Ngữ nghĩa HTTP 4xx (RFC 9309 Section 2.3.1.2)

> *"A 4xx client error indicates that the resource does not exist or the crawler does not have permission to access it. If a status code indicating a 4xx client error is received, the crawler MUST assume that there are no restrictions."* (RFC 9309, Mục 2.3.1.2)

- **HTTP 404 Not Found**: Tệp `robots.txt` không tồn tại $\rightarrow$ Website không đặt bất kỳ giới hạn robots nào $\rightarrow$ `Robots State = UNAVAILABLE`, `Explicit Denial = NO` $\rightarrow$ Cho phép cào.
- **HTTP 403 Forbidden trên `/robots.txt`**: Endpoint `/robots.txt` bị chặn bởi WAF hoặc cấu hình máy chủ $\rightarrow$ Không có tệp robots hợp lệ nào để phân tích $\rightarrow$ `Robots State = UNAVAILABLE`, `Explicit Denial = NO`.
- **Quy tắc Vàng**: **HTTP 403 từ `/robots.txt` KHÔNG PHẢI là `ROBOTS_DENIED`**. Không được tuyên bố "website cấm crawler qua robots.txt" khi chưa từng đọc được chỉ thị `Disallow` nào.

---

## 6. Ngữ nghĩa HTTP 5xx & Sự cố Mạng (RFC 9309 Section 2.3.1.3)

> *"A 5xx server error indicates an internal error on the server... crawler MUST assume complete disallow."* (RFC 9309, Mục 2.3.1.3)

- Khi gặp `HTTP 500/502/503/504`, hoặc `TimeoutError`, `ConnectionRefusedError`, `DNS Resolution Failure`:
  - Trạng thái được phân loại là **`ROBOTS_UNREACHABLE`**.
  - Hệ thống áp dụng nguyên tắc **bảo thủ hoàn toàn (Conservative Complete Disallow)**: Tạm dừng và không cào bất kỳ URL nội dung nào của domain đó trong chu kỳ này.
  - Tích hợp trực tiếp vào **SourceHealth Adaptive Backoff** để kích hoạt thời gian nghỉ (Cooldown) cho hạ tầng mạng.

---

## 7. Nhận diện User-Agent và Product Token Matching

RoomBeacon sử dụng danh tính crawler tiêu chuẩn:
```http
User-Agent: RoomBeaconCrawler/0.1
```

Theo RFC 9309 Section 2.2.1, quy trình khớp nhóm User-Agent diễn ra như sau:
1. **Trích xuất Product Token**: Token được tách từ chuỗi danh tính: `RoomBeaconCrawler` (không chứa phiên bản `/0.1`).
2. **Khớp Không Phân biệt Hoa/Thường (Case-Insensitive Match)**:
   - Tìm kiếm nhóm có dòng `User-agent: RoomBeaconCrawler` (hoặc `roombeaconcrawler`).
   - Nếu tìm thấy nhóm khớp cụ thể, **chỉ áp dụng các quy tắc trong nhóm đó**.
3. **Fallback Nhóm Toàn cục (`User-agent: *`)**:
   - Nếu không có nhóm riêng cho `RoomBeaconCrawler`, hệ thống áp dụng các quy tắc thuộc nhóm `User-agent: *`.
4. **Trường hợp Không có Nhóm Nào Khớp**:
   - Nếu robots.txt chỉ định nghĩa nhóm cho các bot khác (ví dụ `User-agent: Googlebot`) mà không có `*` hay `RoomBeaconCrawler`, mặc định xem như không có giới hạn nào áp dụng cho RoomBeacon (`DEFAULT_ALLOW`).
5. **Chính sách Danh tính**: Tuyệt đối không giả mạo danh tính `Googlebot`, `Chrome`, hay các search engine khác.

---

## 8. Thuật toán Khớp Mẫu Dài Nhất (Longest-Match Specificity)

Theo RFC 9309 Section 2.2.2:
- Khi nhiều quy tắc `Allow` và `Disallow` cùng khớp với một URL mục tiêu, **quy tắc có độ dài chuỗi mẫu (pattern length) lớn nhất (cụ thể nhất) sẽ chiến thắng**.
- **Giải quyết Trùng độ dài (Tie-Breaking)**: Nếu một quy tắc `Allow` và một quy tắc `Disallow` khớp cùng một URL và có **độ dài bằng nhau**, thì **quy tắc `Allow` sẽ chiến thắng**.

### Cú pháp Wildcard & Ký tự Neo:
- `*`: Khớp với chuỗi bất kỳ gồm 0 hoặc nhiều ký tự (ví dụ `/*page=` khớp với mọi URL chứa tham số phân trang `page=`).
- `$`: Neo kết thúc chuỗi (ví dụ `/exact$` chỉ khớp chính xác `/exact` chứ không khớp `/exact/sub`).

---

## 9. Case Study 1: Nhà Tốt (`nhatot.com`) — Phân quyền theo Thao tác

`robots.txt` thực tế của Nhà Tốt chứa:
```http
User-agent: *
Disallow: /*page=
Allow: /
```

- **Khi thẩm định Landing Seed URL** (`https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh`):
  - Khớp `Allow: /` (độ dài 1). Không khớp `/*page=`.
  - Kết quả: **`ALLOWED`** $\rightarrow$ Hệ thống cho phép cào trang hạt giống để trích xuất 25 tin mới.
- **Khi thẩm định URL phân trang** (`https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2`):
  - Khớp `/*page=` (độ dài 7) và `Allow: /` (độ dài 1).
  - Vì $7 > 1$, quy tắc `Disallow: /*page=` chiến thắng!
  - Kết quả: **`ROBOTS_DENIED`** $\rightarrow$ **Hệ thống dừng ngay lập tức, không gửi bất kỳ request mạng nào tới trang 2**.

---

## 10. Case Study 2: Mua Bán (`muaban.net`) — 403 /robots.txt vs Content WAF

- **Thẩm định Robots**:
  - Gửi request `GET https://muaban.net/robots.txt` $\rightarrow$ Nhận `HTTP 403 Forbidden`.
  - Phân loại RFC 9309: **`ROBOTS_UNAVAILABLE`** (HTTP 403 Client Error). `Explicit Denial = NO`.
  - Không có luật cấm robots nào được xác lập. Bước thẩm định Robots cho phép chuyển tiếp.
- **Thẩm định Nội dung (Content Transport)**:
  - Gửi request nội dung $\rightarrow$ Gặp `HTTP 403 Cloudflare Challenge` (hoặc Browser Timeout 408).
  - Kết quả cuối cùng: **`ACCESS_CHALLENGE`** / **`ACCESS_BLOCKED`**.
- **Ý nghĩa Kiến trúc**: **Tầng Robots không cấm crawler, nhưng Tầng Hạ tầng Mạng/WAF của nguồn đã áp đặt rào cản truy cập**.

---

## 11. Case Study 3: Bất Động Sản (`batdongsan.com.vn`) — Tuân thủ Robots != Có Quyền Truy cập

- **Thẩm định Robots**:
  - Gửi request `GET https://batdongsan.com.vn/robots.txt` $\rightarrow$ Nhận `HTTP 200 OK`.
  - Phân tích cú pháp: URL danh mục cho thuê phòng trọ được phép theo nhóm `User-agent: *`.
  - Kết quả: **`ROBOTS_ALLOWED`**.
- **Thẩm định Nội dung**:
  - Direct HTTP Client gửi request tới trang danh mục $\rightarrow$ Nhận `HTTP 403 Cloudflare Challenge`.
  - Kết quả: **`ACCESS_CHALLENGE`** ở tầng HTTP.
- **Bài học Sâu sắc**: *"robots.txt cho phép URL cũng không đảm bảo HTTP content sẽ được máy chủ cho phép truy cập mà không gặp WAF/Challenge."*

---

## 12. So sánh Toàn diện: Robots.txt vs Cloudflare/WAF

| Tiêu chí | Robots.txt Layer | Cloudflare / WAF Layer |
| :--- | :--- | :--- |
| **Vị trí** | Giao thức ứng dụng cấp cao (`/robots.txt`) | Cổng kiểm soát biên mạng (Edge Reverse Proxy / WAF) |
| **Bản chất** | Tự nguyện, tuân thủ đạo đức lập trình | Ép buộc kỹ thuật (IP rate limit, TLS fingerprinting, CAPTCHA) |
| **Mục đích** | Chỉ dẫn crawler những vùng nên/không nên lập chỉ mục | Bảo vệ máy chủ khỏi DDoS, scraping hàng loạt và bot độc hại |
| **Xử lý khi chặn** | `ROBOTS_DENIED` $\rightarrow$ Dừng vĩnh viễn với đường dẫn đó | `ACCESS_CHALLENGE` $\rightarrow$ Báo cáo trung thực, giãn cách Backoff |
| **Chính sách RoomBeacon** | **TUÂN THỦ 100%, KHÔNG BAO GIỜ BYPASS** | **KHÔNG BYPASS, KHÔNG CAPTCHA/PROXY ROTATION** |

---

## 13. Bộ nhớ Đệm Robots (Robots Cache & TTL)

Để tránh gửi request `GET /robots.txt` lặp đi lặp lại trước mỗi trang chi tiết hoặc phân trang:
1. **Khóa Đệm (Cache Key)**: Scheme + Domain / Authority (ví dụ `https://phongtro123.com`).
2. **Cấu trúc Bản ghi Đệm**:
   - `document`: `RobotsDocument` đã phân tích cú pháp (nếu HTTP 200).
   - `robots_state`: `OK` | `UNAVAILABLE` | `UNREACHABLE`.
   - `http_status`: Mã trạng thái phản hồi HTTP.
   - `final_robots_url`: URL sau khi xử lý chuyển hướng (Redirects up to 5 hops).
   - `cached_at`: Timestamp lưu trữ.
   - `ttl_seconds`: Thời gian sống của cache (mặc định: 3600s = 1 giờ).
3. **Hiệu năng**: Giảm hơn 99% lượng request phụ trợ tới website nguồn, bảo đảm tính lịch sự (Politeness).

---

## 14. Tích hợp Quản lý Sức khỏe & Giãn cách Thích ứng (SourceHealth Integration)

| Kết quả Thẩm định Robots | Phân loại Sức khỏe (`SourceHealthOutcome`) | Ảnh hưởng Checkpoint & Retry |
| :--- | :--- | :--- |
| `ALLOWED` | `HEALTHY` (sau khi cào nội dung thành công) | Cập nhật watermark, duy trì chu kỳ chạy chuẩn. |
| `DENIED` | `ROBOTS_DENIED` | Quyết định chính sách. **Không tăng biến đếm lỗi mạng, không kích hoạt retry kỹ thuật**. |
| `UNAVAILABLE` (4xx) | Cho phép tiếp tục sang Content Fetch | Không tính là lỗi hạ tầng robots. Trạng thái phụ thuộc tầng nội dung. |
| `UNREACHABLE` (5xx / Timeout) | `ROBOTS_UNAVAILABLE` | Ghi nhận sự cố mạng, **tăng consecutive failures, kích hoạt Cooldown Backoff (15m - 24h)**. |

---

## 15. Hướng dẫn Trình bày khi Phỏng vấn Kiến trúc (Interview Key Points)

Khi được hỏi: *"Hệ thống Crawler của bạn xử lý robots.txt như thế nào khi website trả về 403 Forbidden hoặc Cloudflare Challenge?"*, bạn có thể trả lời chuẩn mực như sau:

> *"Tại RoomBeacon, chúng tôi xây dựng cơ chế thẩm định tuân thủ nghiêm ngặt tiêu chuẩn RFC 9309 Robots Exclusion Protocol và phân định rạch ròi 3 tầng độc lập:*
>
> 1. *Thứ nhất là **Ngữ nghĩa mã phản hồi**: Theo RFC 9309 Section 2.3.1.2, **HTTP 403 từ `/robots.txt` không đồng nghĩa với Disallow**. Nó chỉ có nghĩa là tài nguyên robots không khả dụng (UNAVAILABLE) và theo chuẩn thì crawler không bị ràng buộc bởi luật cấm robots cụ thể nào. Chúng tôi không bao giờ tuyên bố sai lệch là 'bị robots cấm' khi chưa có luật Disallow.*
>
> 2. *Thứ hai là **Bảo toàn tính toàn vẹn của Disallow**: Đối với các website như Nhà Tốt có chỉ thị rõ ràng `Disallow: /*page=`, hệ thống lập tức ra quyết định `ROBOTS_DENIED` và tuyệt đối không gửi bất kỳ request mạng nào (kể cả HTTP lẫn Browser Playwright) tới các trang phân trang bị cấm.*
>
> 3. *Thứ ba là **Phân tách giữa Robots Compliance và Content Availability**: **Robots.txt cho phép một URL cũng không đồng nghĩa với việc máy chủ nội dung sẽ mở cửa phục vụ**. Một website có thể ALLOW robots nhưng lại áp dụng Cloudflare Challenge ở tầng HTML nội dung. Việc tách bạch 2 tầng này giúp hệ thống RoomBeacon có khả năng quan sát trung thực (Observability), báo cáo số liệu chính xác và kích hoạt giãn cách thích ứng (Adaptive Backoff) đúng nguyên nhân gốc rễ."*
