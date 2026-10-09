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

## 2. API đã có — tất cả là dữ liệu thật

| Nhóm | Endpoint | Ghi chú |
|---|---|---|
| Khu vực | `GET /locations/districts`, `/districts/{id}`, `/districts/{id}/wards`, `/locations/resolve` | Thẻ quận/phường kèm thống kê giá |
| **Tin đăng** | `GET /listings`, `/listings/{id}`, `/listings/{id}/price-history` | Tin TP.HCM có giá hợp lệ, đã bỏ tin trùng; kèm **định giá model** cho từng tin |
| **Định giá (model)** | `POST /price-estimates`, `GET /price-estimates/model` | Model LightGBM champion — **thử nghiệm**, luôn hiển thị khoảng giá + cảnh báo |
| **Thị trường** | `GET /market/summary`, `GET /market/daily` | Số liệu toàn TP hoặc 1 quận; chuỗi theo ngày |

Tất cả có tiền tố `/api/v1`. **Không có** ảnh tin đăng và **không** vẽ bản đồ/ghim toạ độ (toạ độ tin cậy < 2%).
Code gọi dữ liệu đi qua **một lớp adapter** (`lib/api/`), component không gọi `fetch` trực tiếp.

## 3. Kết nối & bảo mật (Next.js App Router)

- Backend: `ROOMBEACON_API_URL` — dev `http://127.0.0.1:8000`, trong Docker `http://api:8000`.
  Swagger: `http://127.0.0.1:8000/docs`. Mọi endpoint `/api/v1/*` bắt buộc header **`X-API-Key`**.
- **Key chỉ tồn tại phía server Next.js**: đọc `process.env.ROOMBEACON_API_KEY` trong module có
  `import "server-only"`. **Không** dùng tiền tố `NEXT_PUBLIC_` cho key, **không** truyền key xuống client component.
- Hai đường gọi API:
  1. **Server Components / `generateMetadata`** gọi thẳng backend qua `lib/api/server.ts` (kèm key) — trang chủ,
     trang khu vực, thẻ thị trường. Cache: `fetch(url, { next: { revalidate: Number(process.env.REVALIDATE_SECONDS ?? 300) } })`.
  2. **Tương tác phía trình duyệt** (Location Picker, gợi ý khi gõ, cuộn vô hạn) gọi **route handler cùng origin**
     `GET /api/rb/<đường dẫn sau /api/v1/>` — handler chuyển tiếp sang backend kèm key. Ví dụ trình duyệt gọi
     `/api/rb/locations/districts?q=binh` thay cho `/api/v1/locations/districts?q=binh`.

```ts
// app/api/rb/[...path]/route.ts — BFF proxy: chỉ GET, chỉ các đường /locations/* có thật
import "server-only";
import { NextRequest, NextResponse } from "next/server";

const ALLOWED = /^(locations\/(districts(\/[0-9a-f]{16}(\/wards)?)?|resolve)|listings(\/[0-9]{1,19}(\/price-history)?)?|market\/(summary|daily)|price-estimates\/model)$/;
const PASS_HEADERS = ["Retry-After", "ETag", "X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"];

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const path = (await params).path.join("/");
  if (!ALLOWED.test(path)) {
    return NextResponse.json({ success: false, code: 404, status: "NOT_FOUND" }, { status: 404 });
  }
  const headers: Record<string, string> = { "X-API-Key": process.env.ROOMBEACON_API_KEY ?? "" };
  const ifNoneMatch = req.headers.get("if-none-match");
  if (ifNoneMatch) headers["If-None-Match"] = ifNoneMatch;
  const upstream = await fetch(`${process.env.ROOMBEACON_API_URL}/api/v1/${path}${req.nextUrl.search}`, {
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  const out = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new NextResponse(upstream.status === 304 ? null : await upstream.text(), { status: upstream.status, headers: out });
}

// Chỉ một endpoint ghi: định giá. Thân request tối đa 2 KB, chuyển nguyên JSON.
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  if ((await params).path.join("/") !== "price-estimates") {
    return NextResponse.json({ success: false, code: 404, status: "NOT_FOUND" }, { status: 404 });
  }
  const body = await req.text();
  if (body.length > 2048) return NextResponse.json({ success: false, code: 413 }, { status: 413 });
  const upstream = await fetch(`${process.env.ROOMBEACON_API_URL}/api/v1/price-estimates`, {
    method: "POST",
    headers: { "X-API-Key": process.env.ROOMBEACON_API_KEY ?? "", "Content-Type": "application/json" },
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  const out = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  for (const name of ["Retry-After", "X-Request-ID"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new NextResponse(await upstream.text(), { status: upstream.status, headers: out });
}
```

- **Mọi trình duyệt dùng chung một key** qua BFF, nên giới hạn tần suất của backend tính chung cho cả site:
  đặt `API_RATE_LIMIT_PER_MINUTE` của backend đủ lớn (vd 600) và tận dụng cache `revalidate`. Phía client vẫn
  **debounce 300 ms** ô gõ và cache bằng TanStack Query (`staleTime: 5 phút`). Gặp `429` → đọc `Retry-After`,
  hiển thị "Thử lại sau N giây".
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

```ts
export type Ref = { id: string; name: string };

export type ListingCard = {
  id: string;                                   // chuỗi số, vd "105419"
  type: "listing";
  title: string;                                // số điện thoại đã bị che thành "***"
  source: string;                               // nguồn crawl, vd "phongtro123"
  source_url: string | null;                    // null nếu URL gốc chứa số điện thoại
  price: { currency: "VND"; amount: number; period: "month" } | null;
  area_m2: number | null;
  price_per_m2: number | null;
  location: { level: "WARD" | "DISTRICT" | "UNKNOWN"; district: Ref | null; ward: Ref | null };
  intent: "RENT" | "TRANSFER" | "SALE" | "UNKNOWN" | null;
  scope: string | null;
  first_observed_at: string | null;
  last_observed_at: string | null;
  active_days: number | null;
  quality: { price_suitability: string | null; duplicate_status: string | null };
  valuation: { estimate: number; delta_pct: number; label: "BELOW_ESTIMATE" | "NEAR_ESTIMATE" | "ABOVE_ESTIMATE" } | null;
  links: { self: string; price_history: string };
};

export type MarketPosition = {
  scope: "ward" | "district"; name: string;
  median: number | null; p25: number | null; p75: number | null; listing_count: number;
  position: "BELOW_P25" | "WITHIN_P25_P75" | "ABOVE_P75" | null;   // vị trí của giá tin/giá ước tính trong dải
};

export type ListingDetail = ListingCard & { market: MarketPosition | null };

export type PricePoint = {
  observed_at: string; price: number | null; area_m2: number | null;
  is_price_change: boolean; is_content_change: boolean;
};

export type PriceEstimate = {
  estimate: number;
  range: { low: number; high: number; coverage: number };   // coverage 0.5 = khoảng chứa giá thật của ~50% tin
  inputs_used: { area_m2: number; district: string; ward: string | null; source_policy: string };
  market: MarketPosition;
  warnings: ("area_outside_typical_range" | "low_price_segment_less_accurate" | "high_price_segment_less_accurate"
            | "district_unknown_to_model" | "ward_unknown_to_model")[];
  disclaimer: string;
  model: { model_id: string; readiness: "experimental" };
};

export type ModelCard = {
  model_id: string; family: string; feature_set: string; target_transform: string; trained_until: string | null;
  test_metrics: { mae: number | null; median_ae: number | null; r2: number | null };
  readiness: "experimental"; reference_source: string; interval_coverage: number;
  typical_area_range: { low: number; high: number }; reliable_price_range: { low: number; high: number };
};

export type MarketSummary = {
  scope: { type: "city" | "district"; district: Ref | null };
  listing_count: number; priced_listing_count: number; district_count: number;
  price: { currency: "VND"; median: number | null; p25: number | null; p75: number | null };
  data_from: string | null; data_until: string | null;
};

export type MarketDay = {
  date: string; listings_observed: number; new_listings: number; price_changes: number; median_price: number | null;
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

### 5.5 `GET /api/v1/listings` — tìm tin đăng

| Query | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|
| `district_id`, `ward_id` | 16 hex | — | từ API khu vực |
| `q` | string ≤ 100 | "" | tìm trong tiêu đề, không phân biệt hoa thường |
| `price_min`, `price_max` | int VND/tháng | — | min > max → 422 (`errors[0].field = "price_min"`) |
| `area_min`, `area_max` | số m² | — | |
| `intent` | `RENT` \| `TRANSFER` \| `SALE` \| `UNKNOWN` \| `ANY` | `RENT` | |
| `include_duplicates` | bool | `false` | |
| `sort` | `last_observed_at` \| `price` \| `area`, thêm `-` để giảm dần | `-last_observed_at` | |
| `page`, `per_page` | | 1, 20 (≤ 100) | |

Chỉ tin **TP.HCM**, giá hợp lệ (`SUPPORTED`). Hiện có ~76.500 tin. Ví dụ phần tử `data` (thật):

```json
{"id": "105419", "type": "listing", "title": "Phòng trọ Quận Gò Vấp - Đường số 8 - 25m²",
 "source": "phongtro123", "source_url": "https://phongtro123.com/...",
 "price": {"currency": "VND", "amount": 2900000, "period": "month"}, "area_m2": 25.0, "price_per_m2": 116000,
 "location": {"level": "WARD", "district": {"id": "…", "name": "Quận Gò Vấp"}, "ward": {"id": "…", "name": "Phường …"}},
 "intent": "RENT", "active_days": 12,
 "valuation": {"estimate": 3724191, "delta_pct": -22.1, "label": "BELOW_ESTIMATE"},
 "links": {"self": "/api/v1/listings/105419", "price_history": "/api/v1/listings/105419/price-history"}}
```

`valuation` = giá model ước tính cho chính tin đó; `delta_pct` = (giá đăng − ước tính) / ước tính × 100.
Nhãn: < −10% `BELOW_ESTIMATE` ("Rẻ hơn ước tính"), > +10% `ABOVE_ESTIMATE`, còn lại `NEAR_ESTIMATE`.
`valuation` có thể `null` (thiếu diện tích/giá hoặc model tạm không khả dụng) — khi đó ẩn nhãn.

### 5.6 `GET /api/v1/listings/{id}` — chi tiết tin

`id` là chuỗi số (≤ 19 chữ số; sai → 422; không có → 404). `data` = `ListingDetail`, ví dụ thật:

```json
{"market": {"scope": "ward", "name": "Phường Tân Hưng", "median": 5000000, "p25": 4200000, "p75": 6500000,
            "listing_count": 8839, "position": "BELOW_P25"},
 "valuation": {"estimate": 4238966, "delta_pct": -29.2, "label": "BELOW_ESTIMATE"}, "...": "các trường như ListingCard"}
```

### 5.7 `GET /api/v1/listings/{id}/price-history` — lịch sử giá

Phân trang (`per_page` mặc định 50). `data` = `PricePoint[]` theo thời gian tăng dần, ví dụ:
`{"observed_at": "2026-09-21T05:01:13Z", "price": 3000000, "area_m2": 28.0, "is_price_change": false, "is_content_change": true}`.

### 5.8 `POST /api/v1/price-estimates` — định giá phòng

Body JSON (không nhận trường lạ → 422): `{"area_m2": 25, "district_id": "e2ed9f251d8cc334", "ward_id": "2482f9f85888cdc4"}`
— `area_m2` 5–500, `ward_id` tuỳ chọn nhưng phải thuộc `district_id` (sai → 422 `field = "ward_id"`).
Response thật (`data`):

```json
{"estimate": 4074861,
 "range": {"low": 3333304, "high": 4798459, "coverage": 0.5},
 "inputs_used": {"area_m2": 25.0, "district": "Quận 7", "ward": "Phường Tân Hưng", "source_policy": "development_modal_source:phongtro123"},
 "market": {"scope": "ward", "name": "Phường Tân Hưng", "median": 5000000, "p25": 4200000, "p75": 6500000, "listing_count": 8839, "position": "BELOW_P25"},
 "warnings": [],
 "disclaimer": "Ước tính tham khảo từ mô hình thử nghiệm, không phải giá niêm yết; khoảng giá chứa giá thật của khoảng 50% tin trong tập kiểm thử.",
 "model": {"model_id": "roombeacon-price-lgbm-f4-raw-4c203abb3b62", "readiness": "experimental"}}
```

Ví dụ 12 m² ở Quận 7 → `warnings: ["area_outside_typical_range", "low_price_segment_less_accurate"]`.
Response không cache (`Cache-Control: no-store`). Model chưa sẵn sàng → `503` + `Retry-After`.

### 5.9 `GET /api/v1/price-estimates/model` — thẻ model

```json
{"model_id": "roombeacon-price-lgbm-f4-raw-4c203abb3b62", "family": "LightGBM Regressor",
 "feature_set": "F4 — AREA + SOURCE + LOCATION", "trained_until": "2026-09-29T14:31:04Z",
 "test_metrics": {"mae": 916127, "median_ae": 623718, "r2": 0.205}, "readiness": "experimental",
 "interval_coverage": 0.5, "typical_area_range": {"low": 15.0, "high": 50.0},
 "reliable_price_range": {"low": 3000000, "high": 5500000}}
```

### 5.10 `GET /api/v1/market/summary?district_id=` và `GET /api/v1/market/daily?district_id=&date_from=&date_to=`

- `summary` (thật, toàn TP): `listing_count` 132.494 · `priced_listing_count` 80.513 · `district_count` 55 ·
  `price` {median 4.000.000, p25 3.000.000, p75 5.200.000} · `data_from` / `data_until`.
  Có `district_id` → `scope.type = "district"` (Quận 7: 16.088 tin, median 5 triệu).
- `daily`: `MarketDay[]` theo ngày (ngày dạng `YYYY-MM-DD`; khoảng ≤ 92 ngày; `date_from > date_to` → 422).
  Ví dụ Quận 7: `{"date": "2026-09-24", "listings_observed": 4400, "new_listings": 287, "price_changes": 3455, "median_price": 4500000}`.
  Hai ngày 20–22/09 là đợt crawl đầu: `new_listings` rất cao, **không** phải tin mới thật — mặc định biểu đồ bắt đầu từ 23/09.

### 5.11 Hệ thống

- `GET /health` → 200 khi API sống. `GET /ready` → 200 khi đọc được kho dữ liệu, 503 khi không.

### 5.12 Mã lỗi & cách hiển thị

| code | Ý nghĩa | UI |
|---|---|---|
| 304 | Không đổi (khi gửi `If-None-Match`) | dùng cache |
| 401 | Thiếu/sai key | "Phiên kết nối không hợp lệ" (lỗi cấu hình server, không phải lỗi người dùng) |
| 404 | Không tìm thấy | trạng thái rỗng thân thiện |
| 422 | Tham số sai — `errors[].field` cho biết ô nào | báo lỗi tại ô tương ứng |
| 429 | Gọi quá nhanh | "Thử lại sau {Retry-After} giây" |
| 500 | Lỗi hệ thống | "Có lỗi xảy ra" + hiển thị `meta.request_id` nhỏ để báo lỗi |
| 503 | Kho dữ liệu tạm không sẵn sàng | banner "Dữ liệu tạm thời không khả dụng", tự thử lại sau 30 s |

## 6. Hiển thị định giá có trách nhiệm

Model đang ở mức **thử nghiệm** (sai số trung vị ~620 nghìn, dự báo bị "nén" về khoảng 3–5,5 triệu). Bắt buộc:

- Luôn hiển thị **khoảng giá** (`range.low`–`range.high`) to hơn hoặc ngang con số `estimate`; nhãn "Ước tính".
- Luôn hiển thị `disclaimer` (chữ nhỏ) và huy hiệu "Thử nghiệm".
- Map `warnings` sang câu tiếng Việt:

| warning | Câu hiển thị |
|---|---|
| `area_outside_typical_range` | "Diện tích ngoài khoảng phổ biến (15–50 m²), ước tính kém chính xác hơn." |
| `low_price_segment_less_accurate` | "Phân khúc giá thấp — model thường ước tính cao hơn thực tế." |
| `high_price_segment_less_accurate` | "Phân khúc giá cao — model thường ước tính thấp hơn thực tế." |
| `district_unknown_to_model` / `ward_unknown_to_model` | "Khu vực này có ít dữ liệu huấn luyện." |

- Đặt cạnh ước tính **giá thị trường thật** của khu vực (`market.median`, dải p25–p75) — người dùng tin số liệu thật hơn.
- Nhãn trên thẻ tin: `BELOW_ESTIMATE` → "Rẻ hơn ước tính {|delta_pct|}%", `ABOVE_ESTIMATE` → "Cao hơn ước tính {delta_pct}%",
  `NEAR_ESTIMATE` → "Sát ước tính". Không dùng từ "lừa đảo", "hời", "đắt vô lý".

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
│   Gợi ý nhanh: [Dưới 3 triệu] [3–5 triệu] [Quận 7] [Gò Vấp]          │  chip = điền sẵn bộ lọc
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
│ Tin mới cập nhật                                                      │  GET /listings?per_page=8
├──────────────────────────────────────────────────────────────────────┤
│ Dữ liệu cập nhật: 09/10/2026 16:52 · Snapshot db804eae                 │  từ meta.data_snapshot
└──────────────────────────────────────────────────────────────────────┘
```

**Thanh tìm kiếm (thành phần quan trọng nhất):**

1. **Nút Location** (bên trái, có icon 📍): mặc định "Toàn TP.HCM". Bấm mở **Location Picker**.
2. **Ô từ khoá**: tìm trong tiêu đề tin (`q` của `GET /listings`). Nếu người dùng gõ chữ bắt đầu bằng "Phường ..." và chưa chọn
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

- Thanh tìm kiếm thu nhỏ ở đầu, đồng bộ hai chiều với URL query (`district_id`, `ward_id`, `q`, `price_min`,
  `price_max`, `area_min`, `area_max`, `sort`, `page`) → gọi **`GET /listings`** thật.
- Desktop 3 cột: bộ lọc trái · lưới **ListingCard** giữa · **thẻ thị trường** phải (`/market/summary?district_id=`
  hoặc thẻ phường). Mobile: nút "Bộ lọc (n)" mở bottom sheet.
- ListingCard: placeholder ảnh 4:3 (gradient + icon — API không có ảnh), giá to "4,5 triệu/tháng",
  "25 m² · 180.000 đ/m²", "Phường Tân Hưng, Quận 7", "3 ngày trước", nhãn nguồn, **nhãn định giá** (mục 6).
- Sắp xếp: Mới nhất · Giá thấp → cao · Giá cao → thấp · Diện tích. Phân trang theo `meta.pagination`.
- "Hiển thị 1–20 trên 3.860 tin".

### 7.3 Trang chi tiết tin `/phong/[id]`

- Server Component gọi `GET /listings/{id}` + `generateMetadata` (title = tiêu đề tin).
- Khối giá: giá đăng to · "Ước tính model: 4,24 tr (Rẻ hơn ước tính 29%)" · **PriceRangeStrip** của `market`
  với vạch vị trí giá tin.
- Thông tin: diện tích, đ/m², khu vực (link sang `/khu-vuc/[districtId]`), đăng lần đầu / cập nhật, số ngày hoạt động.
- **Biểu đồ lịch sử giá** (`/price-history`, bậc thang theo `observed_at`; chấm đỏ ở `is_price_change`).
- Nút "Xem tin gốc" chỉ khi `source_url` khác null (mở tab mới, `rel="noopener noreferrer nofollow"`).
- "Tin tương tự": `GET /listings?ward_id=…&price_min=…&price_max=…` (±20% giá), loại chính tin này.

### 7.4 Trang định giá `/dinh-gia` — tính năng nổi bật

- Form gọn: **Location Picker** (bắt buộc quận, phường tuỳ chọn) + ô **Diện tích (m²)** (slider 10–80 + ô số).
- Gọi `POST /api/rb/price-estimates`. Kết quả dạng thẻ lớn:
  "Giá thuê ước tính **3,3 – 4,8 triệu/tháng**" (khoảng to), "điểm giữa 4,07 tr" nhỏ hơn, huy hiệu "Thử nghiệm",
  **so sánh với thị trường thật** của phường/quận (PriceRangeStrip), danh sách cảnh báo (mục 6), `disclaimer`.
- Nút "Xem phòng trong khoảng giá này" → `/tim-phong?district_id=…&ward_id=…&price_min={low}&price_max={high}`.
- Liên kết "Về mô hình" mở drawer hiển thị `GET /price-estimates/model` (MAE, ngày train, phạm vi tin cậy).
- Lối vào: nút thứ hai trong hero trang chủ "Định giá phòng của bạn", và menu header.

### 7.5 Trang khu vực `/khu-vuc/[districtId]`

- Hero: tên quận, 4 ô số (`/market/summary?district_id=`): số tin · giá trung vị · dải p25–p75 · số phường.
- **Biểu đồ xu hướng** từ `/market/daily?district_id=…&date_from=2026-09-23`: đường median_price + cột new_listings.
- Lưới thẻ phường (sắp xếp, tìm `q`), mỗi thẻ có nút "Định giá ở phường này" → `/dinh-gia?district_id=…&ward_id=…`.
- Danh sách 8 tin mới nhất của quận (`/listings?district_id=…&per_page=8`).
- `generateMetadata`: "Giá thuê phòng trọ {Quận} — RoomBeacon".

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

## 9. Công nghệ & cấu trúc

- **Next.js 16.3.6 (App Router)**, React 19.3.0, TypeScript 6.0.3 (strict), Tailwind CSS 4.3.3 +
  `@tailwindcss/postcss` 4.3.3, TanStack Query 5.103.2 (chỉ cho phần tương tác phía client), lucide-react 1.48.0,
  `server-only` 0.0.1. Node ≥ 20.9 (máy dev có Node 22). **Ghim phiên bản chính xác** (không `^`/`~`), commit
  `package-lock.json`. `next.config.ts` bật `output: "standalone"`.
- Thư mục `frontend/` ở gốc repo (không dùng `src/`):

```
frontend/
  app/layout.tsx                     font Be Vietnam Pro (next/font/google), header/footer, <Providers>
  app/page.tsx                       Trang chủ — Server Component (thẻ quận + snapshot)
  app/tim-phong/page.tsx             Kết quả — đọc searchParams
  app/khu-vuc/page.tsx               Danh sách quận
  app/khu-vuc/[districtId]/page.tsx  Trang khu vực + generateMetadata (SEO)
  app/phong/[id]/page.tsx            Chi tiết tin + generateMetadata
  app/dinh-gia/page.tsx              Trang định giá (form là client component)
  app/api/rb/[...path]/route.ts      BFF proxy (mục 3)
  app/not-found.tsx, app/error.tsx, loading.tsx mỗi route (skeleton)
  lib/api/server.ts                  gọi backend kèm key — import "server-only"
  lib/api/client.ts                  gọi /api/rb/* từ trình duyệt; đọc envelope cho MỌI mã (kể cả 300/4xx/5xx)
  lib/types/api.ts                   type mục 4 và 6
  lib/format.ts                      định dạng mục 8
  components/search/                 SearchBar, LocationPicker, PriceFilter, AreaFilter ("use client")
  components/cards/                  DistrictCard, WardCard, ListingCard, PriceRangeStrip, ValuationBadge
  components/charts/                 PriceHistoryChart, MarketTrendChart (SVG tự vẽ, không thêm thư viện nặng)
  components/estimate/               EstimateForm, EstimateResult, ModelCardDrawer
  Dockerfile                         multi-stage, standalone, user non-root (uid 10002), EXPOSE 3000
```

- Giữ `frontend/.gitignore` (đã có `node_modules/`, `.next/`, `.env.local`) và `frontend/.env.example`.

## 10. Những điều KHÔNG được làm

- Không đặt API key trong client component, bundle, `localStorage` hay biến `NEXT_PUBLIC_*`; chỉ đọc trong module `server-only`.
- Không gọi endpoint ngoài danh sách mục 2; không tự tạo dữ liệu giả.
- Không vẽ bản đồ / ghim toạ độ, không tự suy toạ độ từ tên quận/phường.
- Không hiển thị hay suy đoán số điện thoại / thông tin người đăng.
- Không copy logo, tên, màu nhận diện hay ảnh của trang khác.
- Không hiển thị `0` khi giá trị là `null`.

## 11. Tiêu chí hoàn thành

- [ ] Trang chủ có thanh tìm kiếm lớn ở giữa; nút Location mở picker 2 bước quận → phường chạy với API thật.
- [ ] Gõ "Phường Tân Hưng" → hiện lựa chọn theo quận (xử lý đúng `300`).
- [ ] `/tim-phong` hiển thị tin thật từ `GET /listings`, lọc theo khu vực/giá/diện tích, sắp xếp, phân trang.
- [ ] Thẻ tin có nhãn định giá; `valuation = null` thì ẩn nhãn; `source_url = null` thì ẩn nút "Xem tin gốc".
- [ ] `/phong/[id]` có so sánh thị trường + biểu đồ lịch sử giá.
- [ ] `/dinh-gia` gọi `POST /price-estimates`, hiển thị **khoảng giá**, cảnh báo tiếng Việt, disclaimer, huy hiệu "Thử nghiệm".
- [ ] `/khu-vuc/[id]` có số liệu `market/summary` + biểu đồ `market/daily` bắt đầu 23/09.
- [ ] Thẻ quận/phường hiển thị số tin, giá trung vị, dải p25–p75, đ/m² theo đúng định dạng mục 8.
- [ ] Xử lý đủ 401/404/422/429/500/503 theo bảng 5.12; 500 hiển thị `request_id`.
- [ ] Key chỉ đọc phía server (`lib/api/server.ts`, route handler); `grep` chuỗi key trong `.next/static` rỗng.
- [ ] Route handler `/api/rb/*` chỉ cho GET các đường ở mục 3 và POST `price-estimates`.
- [ ] Trang `/khu-vuc/[districtId]` và `/phong/[id]` render sẵn nội dung và có `<title>` riêng.
- [ ] Footer hiển thị thời điểm cập nhật dữ liệu từ `meta.data_snapshot.loaded_at`.
