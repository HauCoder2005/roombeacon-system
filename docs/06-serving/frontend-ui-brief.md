# RoomBeacon Web UI — Brief cho Antigravity

> Tài liệu này mô tả **API thật đang chạy** và **giao diện cần dựng**. Đọc hết trước khi sinh code.
> Mọi ví dụ JSON bên dưới được lấy từ API thật (snapshot `db804eae`, dữ liệu 20/09 → 03/10/2026).

---

## 1. Mục tiêu

Dựng web app tìm phòng trọ / nhà thuê tại **TP.HCM**, bố cục kiểu chợ rao vặt (tham khảo cách sắp xếp
của các trang rao vặt bất động sản quen thuộc), nhưng **thương hiệu riêng "RoomBeacon"**:

- Không dùng logo, tên, màu nhận diện hay ảnh của bất kỳ trang nào khác.
- **Trang chủ mới**: trung tâm là **một thanh tìm kiếm to, dài**, có **nút chọn khu vực (Location)** ngay
  trong thanh để lọc nhanh.

## 2. ⚠ API hiện có và chưa có — đọc kỹ

| Nhóm | Trạng thái | Dùng thế nào |
|---|---|---|
| Khu vực: quận, phường, tìm phường | ✅ **Có thật** (`/api/v1/locations/...`) | Gọi API thật |
| Thống kê giá theo quận/phường (thẻ) | ✅ **Có thật** (nằm trong thẻ quận/phường) | Gọi API thật |
| **Danh sách tin đăng / tìm kiếm tin** | ❌ **Chưa có** | Dùng **mock adapter** theo hợp đồng dự kiến ở mục 6. **Không gọi** endpoint chưa tồn tại |
| Chi tiết 1 tin, ảnh, bản đồ | ❌ Chưa có | Mock; **không vẽ bản đồ/ghim toạ độ** (dữ liệu toạ độ tin cậy < 2%) |

Code gọi dữ liệu phải đi qua **một lớp adapter** (`src/api/`) để sau này thay mock bằng API thật mà không
sửa component.

## 3. Kết nối & bảo mật

- Base URL API (dev): `http://127.0.0.1:8000`. Tài liệu Swagger: `http://127.0.0.1:8000/docs`.
- Mọi endpoint `/api/v1/*` bắt buộc header **`X-API-Key`**.
- **Tuyệt đối không đưa API key vào code frontend / bundle** (không dùng biến `VITE_*` cho key).
  Dùng **Vite dev-server proxy**: trình duyệt gọi `/api/...` cùng origin, proxy chèn header phía server.

```ts
// vite.config.ts
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ""); // đọc ROOMBEACON_API_KEY từ .env.local của frontend (git-ignored)
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          headers: { "X-API-Key": env.ROOMBEACON_API_KEY },
        },
      },
    },
  };
});
```

- Giới hạn **60 request/phút/key** → ô gõ tìm kiếm phải **debounce 300 ms**, cache bằng TanStack Query
  (`staleTime: 5 phút`). Gặp `429` thì đọc header `Retry-After` và hiển thị "Thử lại sau N giây".
- Tiếng Việt có dấu gửi thẳng (UTF-8, URL-encode bình thường); server tự chuẩn hoá NFC.
- API **không trả thông tin người đăng / số điện thoại**. UI không được hiển thị hay suy đoán thông tin liên hệ.

## 4. Định dạng response chung ("thẻ căn cước")

Mọi response (trừ `304`) có **đúng** các khoá sau:

```ts
export type ApiEnvelope<T> = {
  success: boolean;            // true khi 2xx
  code: number;                // = HTTP status
  status: "OK" | "MULTIPLE_CHOICES" | "MOVED_PERMANENTLY" | "UNAUTHORIZED" | "NOT_FOUND"
        | "VALIDATION_ERROR" | "RATE_LIMITED" | "INTERNAL_ERROR" | "SERVICE_UNAVAILABLE" | string;
  message: string;
  data: T | null;
  errors: { field: string | null; code: string; message: string }[] | null;
  meta: {
    request_id: string;
    timestamp: string;          // ISO UTC
    api_version: "v1";
    method: string;
    path: string;
    duration_ms: number;
    resource: string | null;
    data_snapshot: { snapshot_id: string; loaded_at: string } | null;
    cache: { etag: string; expires_at: string } | null;
    pagination: {
      page: number; per_page: number; total_items: number; total_pages: number;
      has_next: boolean; has_prev: boolean;
    } | null;
    sort: string[] | null;
    filters: Record<string, string> | null;
  };
  links: Record<string, string | null> | null;   // self/first/prev/next/last khi có phân trang
};

export type Price = {
  currency: "VND";
  median: number | null;        // giá thuê/tháng (VND, số nguyên)
  p25: number | null;
  p75: number | null;
  median_per_m2: number | null; // VND/m²
  median_area_m2: number | null;
};

export type DistrictCard = {
  id: string;                   // 16 ký tự hex, ổn định — LUÔN là string
  type: "district";
  name: string;                 // "Quận 7"
  stats: { listing_count: number; priced_listing_count: number; ward_count: number };
  price: Price;
  links: { self: string; wards: string };
};

export type WardCard = {
  id: string;
  type: "ward";
  name: string;                 // tên phường sau sáp nhập 2025, vd "Phường Tân Hưng"
  district: { id: string; name: string };
  stats: { listing_count: number; priced_listing_count: number };
  price: Price;
  links: { district: string; district_wards: string };
};
```

`null` nghĩa là **chưa đủ dữ liệu** — hiển thị "Chưa đủ dữ liệu", **không** hiển thị 0.

## 5. Endpoints có thật

### 5.1 `GET /api/v1/locations/districts` — danh sách thẻ quận

| Query | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|
| `q` | string ≤ 100 | "" | tìm theo tên, không phân biệt hoa thường/dấu kiểu gõ |
| `sort` | `name` \| `listing_count` \| `median_price`, thêm `-` để giảm dần | `-listing_count` | trường khác → 422 |
| `page` | int ≥ 1 | 1 | |
| `per_page` | 1–100 | 20 | `page × per_page ≤ 10 000` |

Ví dụ thật (`?per_page=2`, rút gọn meta):

```json
{
  "success": true, "code": 200, "status": "OK", "message": "District cards retrieved",
  "data": [
    {"id": "e2ed9f251d8cc334", "type": "district", "name": "Quận 7",
     "stats": {"listing_count": 16088, "priced_listing_count": 10320, "ward_count": 4},
     "price": {"currency": "VND", "median": 5000000, "p25": 4000000, "p75": 6500000,
               "median_per_m2": 155556, "median_area_m2": 30.0},
     "links": {"self": "/api/v1/locations/districts/e2ed9f251d8cc334",
               "wards": "/api/v1/locations/districts/e2ed9f251d8cc334/wards"}},
    {"id": "5d5d326d171d8c59", "type": "district", "name": "Quận Tân Bình",
     "stats": {"listing_count": 13080, "priced_listing_count": 6868, "ward_count": 9},
     "price": {"currency": "VND", "median": 4500000, "p25": 3300000, "p75": 6000000,
               "median_per_m2": 156667, "median_area_m2": 28.0},
     "links": {"self": "/api/v1/locations/districts/5d5d326d171d8c59",
               "wards": "/api/v1/locations/districts/5d5d326d171d8c59/wards"}}
  ],
  "errors": null,
  "meta": {"request_id": "req_b94ed86a25084642aeac", "resource": "district",
           "data_snapshot": {"snapshot_id": "db804eae-1774-4659-aa9a-255830997f5d", "loaded_at": "2026-10-09T09:52:26Z"},
           "pagination": {"page": 1, "per_page": 2, "total_items": 55, "total_pages": 28, "has_next": true, "has_prev": false},
           "sort": ["-listing_count"], "filters": {}, "...": "..."},
  "links": {"self": "/api/v1/locations/districts?page=1&per_page=2&sort=-listing_count",
            "next": "/api/v1/locations/districts?page=2&per_page=2&sort=-listing_count", "prev": null, "...": "..."}
}
```

### 5.2 `GET /api/v1/locations/districts/{district_id}` — 1 thẻ quận

`district_id` = 16 ký tự hex. Không tồn tại → `404`; sai định dạng → `422`. `data` là một `DistrictCard`.

### 5.3 `GET /api/v1/locations/districts/{district_id}/wards` — thẻ phường của quận

Query giống 5.1 (`q`, `sort`, `page`, `per_page`). Ví dụ phần tử `data`:

```json
{"id": "2482f9f85888cdc4", "type": "ward", "name": "Phường Tân Hưng",
 "district": {"id": "e2ed9f251d8cc334", "name": "Quận 7"},
 "stats": {"listing_count": 8839, "priced_listing_count": 5867},
 "price": {"currency": "VND", "median": 5000000, "p25": 4200000, "p75": 6500000,
           "median_per_m2": 157143, "median_area_m2": 30.0},
 "links": {"district": "/api/v1/locations/districts/e2ed9f251d8cc334",
           "district_wards": "/api/v1/locations/districts/e2ed9f251d8cc334/wards"}}
```

### 5.4 `GET /api/v1/locations/resolve?ward=...&district_id=...` — tìm phường theo tên gõ tự do

| Kết quả | `data` | UI phải làm |
|---|---|---|
| `200` | 1 `WardCard` | chọn luôn phường đó |
| `300 MULTIPLE_CHOICES` | `{ "choices": WardCard[] }` (≤ 20) | hiện danh sách "Phường X — thuộc Quận Y" để người dùng chọn |
| `404` | null | "Không tìm thấy phường này" + gợi ý chọn từ danh sách |

Ví dụ thật `ward=Phường Tân Hưng` → **300** (tên này có ở 6 quận cũ; rút gọn còn 2):

```json
{"success": false, "code": 300, "status": "MULTIPLE_CHOICES",
 "message": "The ward name matches several places; pick one",
 "data": {"choices": [
   {"id": "2482f9f85888cdc4", "name": "Phường Tân Hưng", "district": {"id": "e2ed9f251d8cc334", "name": "Quận 7"},
    "stats": {"listing_count": 8839, "priced_listing_count": 5867}, "...": "..."},
   {"id": "5307a9730d4e56a1", "name": "Phường Tân Hưng", "district": {"id": "660a2a6c226ea738", "name": "Quận 12"},
    "stats": {"listing_count": 66, "priced_listing_count": 18}, "...": "..."}]},
 "errors": null, "meta": {"...": "..."}, "links": null}
```

**Lưu ý:** `fetch` coi `300` là không lỗi (`response.ok === false` nhưng có body JSON) — adapter phải đọc
body cho mọi mã, rồi rẽ nhánh theo `code`.

### 5.5 Hệ thống

- `GET /health` → 200 khi API sống. `GET /ready` → 200 khi đọc được kho dữ liệu, 503 khi không.

### 5.6 Mã lỗi & cách hiển thị

| code | Ý nghĩa | UI |
|---|---|---|
| 304 | Không đổi (khi gửi `If-None-Match`) | dùng cache |
| 401 | Thiếu/sai key | "Phiên kết nối không hợp lệ" (lỗi cấu hình proxy, không phải lỗi người dùng) |
| 404 | Không tìm thấy | trạng thái rỗng thân thiện |
| 422 | Tham số sai — `errors[].field` cho biết ô nào | báo lỗi tại ô tương ứng |
| 429 | Gọi quá nhanh | "Thử lại sau {Retry-After} giây" |
| 500 | Lỗi hệ thống | "Có lỗi xảy ra" + hiển thị `meta.request_id` nhỏ để báo lỗi |
| 503 | Kho dữ liệu tạm không sẵn sàng | banner "Dữ liệu tạm thời không khả dụng", tự thử lại sau 30 s |

## 6. Hợp đồng DỰ KIẾN cho tin đăng (CHƯA CÓ — chỉ dùng cho mock)

Mock adapter phải trả đúng envelope ở mục 4 với dữ liệu giả hợp lý (giá 1,5–15 triệu, diện tích 12–60 m²,
quận/phường lấy từ API thật). Khi backend làm xong, chỉ đổi adapter.

`GET /api/v1/listings` — query: `district_id`, `ward_id`, `q`, `price_min`, `price_max`, `area_min`,
`area_max`, `sort` (`-last_observed_at` mặc định, `price`, `-price`, `area`), `page`, `per_page`.

```ts
export type ListingCard = {
  id: string;
  title: string;                      // đã che số điện thoại phía server
  price_vnd: number | null;
  area_m2: number | null;
  price_per_m2_vnd: number | null;
  location: { district_id: string | null; district: string | null;
              ward_id: string | null; ward: string | null; level: "WARD" | "DISTRICT" | "UNKNOWN" };
  source: string;                      // tên nguồn crawl, vd "phongtro123"
  first_observed_at: string;
  last_observed_at: string;
  active_days: number;
};
```

## 7. Giao diện cần dựng

Ngôn ngữ UI: **tiếng Việt**. Responsive (mobile trước, ≥ 360 px). Sáng/tối theo hệ thống.

### 7.1 Trang chủ `/`

```
┌──────────────────────────────────────────────────────────────────────┐
│ RoomBeacon        [Tìm phòng] [Khu vực] [Giá thị trường]              │  header gọn, sticky
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│            Tìm phòng trọ tại TP.HCM — giá thật, cập nhật mỗi ngày      │  tiêu đề hero
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ [📍 Quận 7 ▾] │ 🔍 Tìm theo tên đường, phường...  │ [Giá ▾] [m² ▾] │ [ Tìm ] │  ← THANH TÌM KIẾM TO
│  └────────────────────────────────────────────────────────────────┘  │     (cao ~64 px, rộng ~min(960px, 92vw))
│   Gợi ý nhanh: [Dưới 3 triệu] [3–5 triệu] [Có gác] [Gần ĐH]          │  chip lọc nhanh (mock tạm)
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│ Khu vực nhiều tin nhất                         [Xem tất cả →]         │  /locations/districts?per_page=8
│ ┌────────┐┌────────┐┌────────┐┌────────┐                              │
│ │Quận 7  ││Tân Bình││Bình    ││Gò Vấp  │  thẻ quận: tên, số tin,      │
│ │16.088  ││13.080  ││Thạnh   ││...     │  giá trung vị, p25–p75       │
│ │5 tr/th ││4,5 tr  ││4,8 tr  ││        │                              │
│ └────────┘└────────┘└────────┘└────────┘                              │
├──────────────────────────────────────────────────────────────────────┤
│ Giá thuê theo khu vực   [Sắp xếp: Giá cao ▾]                          │  sort=-median_price
│ bảng/thanh ngang: quận — giá trung vị — dải p25–p75 — đ/m²            │
├──────────────────────────────────────────────────────────────────────┤
│ Tin mới đăng (MOCK)                                                   │  lưới ListingCard từ mock
├──────────────────────────────────────────────────────────────────────┤
│ Dữ liệu cập nhật: 09/10/2026 16:52 · Snapshot db804eae                 │  từ meta.data_snapshot
└──────────────────────────────────────────────────────────────────────┘
```

**Thanh tìm kiếm (thành phần quan trọng nhất):**

1. **Nút Location** (bên trái, có icon 📍): mặc định "Toàn TP.HCM". Bấm mở **Location Picker**.
2. **Ô từ khoá**: tìm trong tin (mock). Nếu người dùng gõ chữ bắt đầu bằng "Phường ..." và chưa chọn
   khu vực → gọi `resolve` (debounce 300 ms) để gợi ý phường.
3. **Giá** (dropdown khoảng: < 2 tr, 2–3, 3–5, 5–8, > 8 tr, tuỳ chỉnh) và **Diện tích** (< 20, 20–30, 30–50, > 50 m²).
4. **Nút Tìm** → điều hướng `/tim-phong?district_id=...&ward_id=...&q=...&price_min=...&price_max=...`.
5. Trên mobile: thanh thu gọn thành 1 ô; bấm vào mở **bottom sheet** chứa đủ các trường.

**Location Picker (modal desktop / bottom sheet mobile):**

```
┌ Chọn khu vực ─────────────────────────────── ✕ ┐
│ 🔍 Tìm quận...                                  │  q → /locations/districts?q=...&per_page=50 (debounce 300 ms)
│ [Toàn TP.HCM]                                   │
│ Quận 7            16.088 tin · 5 tr      ›       │  sort=-listing_count
│ Quận Tân Bình     13.080 tin · 4,5 tr    ›       │
│ ...                                             │  cuộn vô hạn: dùng links.next / has_next
├─────────────────────────────────────────────────┤
│ ‹ Quận 7 — chọn phường                          │  bước 2: /districts/{id}/wards
│ [Toàn Quận 7]                                   │
│ Phường Tân Hưng    8.839 tin · 5 tr             │
│ Phường Tân Thuận   ...                          │
└─────────────────────────────────────────────────┘
```

- Bước 1 chọn quận → bước 2 chọn phường (hoặc "Toàn quận"). Nút Location hiển thị "Phường Tân Hưng, Quận 7".
- Lưu lựa chọn gần nhất vào `localStorage` (bọc try/catch).
- Tên quận/phường dùng **nguyên văn từ API** (đã là tên phường sau sáp nhập 2025).

### 7.2 Trang kết quả `/tim-phong`

- Trên cùng: lặp lại thanh tìm kiếm (thu nhỏ), giữ giá trị từ URL.
- Trái (desktop): bộ lọc — khu vực, giá, diện tích, sắp xếp. Mobile: nút "Bộ lọc" mở bottom sheet.
- Giữa: lưới `ListingCard` (**mock**) + phân trang (dùng `meta.pagination`, `links`).
- Phải/đầu trang: **thẻ thị trường** của khu vực đang chọn — gọi API thật:
  `/locations/districts/{id}` hoặc thẻ phường (lấy từ `/wards`) → "Giá trung vị khu này: 5 tr (4,2–6,5 tr)".
  So giá mỗi tin mock với dải p25–p75 để gắn nhãn "Rẻ hơn mặt bằng" / "Đắt hơn mặt bằng".

### 7.3 Trang khu vực `/khu-vuc/:districtId`

- Thẻ lớn quận (5.2): số tin, số phường, giá trung vị, dải p25–p75, đ/m², diện tích trung vị.
- Lưới thẻ phường (5.3) có sắp xếp `-listing_count` / `-median_price` / `name` và ô tìm `q`.
- Nút "Tìm phòng ở khu này" → `/tim-phong?district_id=...`.

## 8. Quy tắc hiển thị số

| Giá trị | Hiển thị |
|---|---|
| 5000000 | `5 triệu` (thẻ: `5 tr/tháng`) |
| 4500000 | `4,5 triệu` |
| 155556 (đ/m²) | `155.556 đ/m²` |
| 30.0 (m²) | `30 m²` |
| 16088 | `16.088 tin` |
| `null` | `Chưa đủ dữ liệu` |
| `priced_listing_count < 30` | thêm nhãn mờ "Ít dữ liệu" cạnh giá |

Dùng `Intl.NumberFormat("vi-VN")`.

## 9. Công nghệ & cấu trúc đề xuất

- **Vite + React + TypeScript**, **Tailwind CSS**, **TanStack Query**, **React Router**.
- Thư mục `frontend/` ở gốc repo:

```
frontend/
  src/api/client.ts          fetch + đọc envelope cho MỌI mã (kể cả 300/4xx/5xx), không ném lỗi mù
  src/api/locations.ts       5 hàm gọi API thật (mục 5)
  src/api/listings.mock.ts   mock theo mục 6 (cùng chữ ký sẽ dùng khi có API thật)
  src/types/api.ts           các type ở mục 4 và 6
  src/components/SearchBar/  SearchBar, LocationPicker, PriceFilter, AreaFilter
  src/components/cards/      DistrictCard, WardCard, ListingCard, MarketPriceBadge
  src/pages/                 Home, Search, District
  src/lib/format.ts          định dạng mục 8
```

## 10. Những điều KHÔNG được làm

- Không đặt API key trong code, bundle, `localStorage` hay biến `VITE_*`.
- Không gọi endpoint chưa tồn tại (mục 6) — dùng mock.
- Không vẽ bản đồ / ghim toạ độ, không tự suy toạ độ từ tên quận/phường.
- Không hiển thị hay suy đoán số điện thoại / thông tin người đăng.
- Không copy logo, tên, màu nhận diện hay ảnh của trang khác.
- Không hiển thị `0` khi giá trị là `null`.

## 11. Tiêu chí hoàn thành

- [ ] Trang chủ có thanh tìm kiếm lớn ở giữa; nút Location mở picker 2 bước quận → phường chạy với API thật.
- [ ] Gõ "Phường Tân Hưng" → hiện lựa chọn theo quận (xử lý đúng `300`).
- [ ] Thẻ quận/phường hiển thị số tin, giá trung vị, dải p25–p75, đ/m² theo đúng định dạng mục 8.
- [ ] Phân trang/cuộn dùng `meta.pagination` / `links.next`.
- [ ] Xử lý đủ 401/404/422/429/500/503 theo bảng 5.6; 500 hiển thị `request_id`.
- [ ] Key chỉ nằm trong proxy dev (`ROOMBEACON_API_KEY` trong `frontend/.env.local`, đã git-ignore).
- [ ] Footer hiển thị thời điểm cập nhật dữ liệu từ `meta.data_snapshot.loaded_at`.
- [ ] Tin đăng là mock và được đánh dấu rõ trong code (`listings.mock.ts`).
