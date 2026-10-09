# Prompt cho Antigravity — dựng giao diện RoomBeacon

> Dán toàn bộ khối dưới đây vào Antigravity (agent mode), mở đúng thư mục gốc repo.

---

Bạn là một **senior frontend engineer kiêm product designer**. Hãy dựng giao diện web cho **RoomBeacon** —
nền tảng tìm phòng trọ / nhà thuê tại **TP.HCM** dựa trên dữ liệu thật đã được thu thập và phân tích.

## 0. Đọc trước khi làm

1. Đọc kỹ **`docs/06-serving/frontend-ui-brief.md`**. Đây là **nguồn sự thật** về API (endpoint, kiểu dữ liệu,
   ví dụ response thật, mã lỗi, cách hiển thị định giá có trách nhiệm). **Mọi dữ liệu đều là API thật — không tạo dữ liệu giả.** Nếu prompt này và brief mâu thuẫn
   về API, **brief thắng**.
2. Backend đang chạy ở máy local: `http://127.0.0.1:8000` (Swagger: `http://127.0.0.1:8000/docs`).
   Biến môi trường nằm trong `frontend/.env.local` (mẫu: `frontend/.env.example`):
   - `ROOMBEACON_API_URL` — địa chỉ backend
   - `ROOMBEACON_API_KEY` — key gốc, **chỉ code phía server Next.js** được đọc
   - `REVALIDATE_SECONDS=300` — thời gian cache phía server; `PORT=3000`
   - Trình duyệt **không** gọi thẳng `/api/v1/*`: dùng route handler cùng origin `/api/rb/*` (brief mục 3).
3. **Chỉ tạo/sửa file trong thư mục `frontend/`.** Không đụng backend, crawler, Airflow, docker-compose hay
   bất kỳ file nào ngoài `frontend/`. Giữ nguyên `frontend/.env.example` và `frontend/.gitignore` đã có.

## 1. Ý tưởng thiết kế

**Tinh thần:** "Biết rõ giá trước khi hỏi thuê." RoomBeacon giống một **ngọn hải đăng** giữa rừng tin rao —
bố cục quen thuộc của trang rao vặt (lưới tin, bộ lọc, thẻ giá to) để người dùng không phải học lại, nhưng
điểm khác biệt là **mọi nơi đều cho thấy giá thị trường thật của khu vực**.

**Thương hiệu riêng — không sao chép** logo, tên, màu vàng nhận diện hay hình ảnh của Chợ Tốt hoặc trang nào khác.

| Token | Giá trị | Dùng cho |
|---|---|---|
| `--brand` | `#0F766E` (teal 700) | header, link, viền focus, trạng thái chọn |
| `--brand-soft` | `#CCFBF1` | nền chip đang chọn, nền hero nhạt |
| `--beacon` | `#F59E0B` (amber 500) | **chỉ** nút hành động chính "Tìm phòng", điểm median trên dải giá |
| `--ink` | `#0F172A` | chữ chính |
| `--muted` | `#64748B` | chữ phụ |
| `--surface` / `--bg` | `#FFFFFF` / `#F8FAFC` | thẻ / nền trang |
| `--good` / `--bad` | `#059669` / `#DC2626` | nhãn "Rẻ hơn" / "Đắt hơn mặt bằng" |

- Có **dark mode** theo hệ thống (định nghĩa lại các token dưới `prefers-color-scheme: dark`), đạt tương phản WCAG AA.
- Font: **Be Vietnam Pro** (Google Fonts, hỗ trợ đầy đủ dấu tiếng Việt), weight 400/500/600/700.
- Bo góc: thẻ `16px`, thanh tìm kiếm dạng **pill** (`9999px`). Đổ bóng mềm, không viền đậm.
- Icon: `lucide-react` (`MapPin`, `Search`, `SlidersHorizontal`, `ChevronRight`, `X`, `TrendingDown`, `TrendingUp`).
- Logo: chữ "RoomBeacon" + một icon ngọn hải đăng đơn giản tự vẽ bằng SVG (không lấy ảnh ngoài).

**Thành phần nhận diện riêng — "Dải giá" (PriceRangeStrip):** một thanh ngang mảnh biểu diễn khoảng
`p25 → p75` của khu vực, chấm tròn màu `--beacon` tại `median`; khi đặt trong thẻ tin thì có thêm vạch nhỏ
chỉ vị trí giá của tin đó. Dùng nhất quán ở thẻ quận, thẻ phường, thẻ tin và trang khu vực.

## 2. Trang chủ `/` — khác biệt, lấy thanh tìm kiếm làm trung tâm

Từ trên xuống:

1. **Header** sticky, cao 64px: logo trái; menu "Tìm phòng · Khu vực · Bảng giá"; nền trắng mờ (backdrop-blur) khi cuộn.
2. **Hero** (chiếm ~70vh trên desktop): nền gradient rất nhạt `--brand-soft → --bg` với hoạ tiết lưới mảnh
   bằng CSS (gợi bản đồ, **không** phải bản đồ thật).
   - Tiêu đề lớn: **"Tìm phòng trọ ở TP.HCM — biết rõ giá trước khi hỏi"**
   - Dòng phụ có số liệu thật: "**{tổng số tin}** tin · **{số quận}** quận · cập nhật {ngày giờ}" — lấy từ
     `/api/v1/locations/districts?per_page=100` (cộng `stats.listing_count`, `meta.pagination.total_items`,
     `meta.data_snapshot.loaded_at`).
   - **THANH TÌM KIẾM LỚN** ở chính giữa — thành phần quan trọng nhất:
     ```
     ┌──────────────────────────────────────────────────────────────────────────────┐
     │ 📍 Khu vực          │ 🔍 Tìm theo đường, phường, tiện ích…   │ Giá ▾ │ m² ▾ │ [ 🔍 Tìm phòng ] │
     │    Toàn TP.HCM ▾    │                                        │       │      │   (nền --beacon)  │
     └──────────────────────────────────────────────────────────────────────────────┘
     ```
     - Cao 64–72px, rộng `min(1040px, 92vw)`, pill, `shadow-xl`, các ô ngăn bằng vạch dọc mảnh.
     - **Nút Khu vực** (trái) mở **Location Picker** (mục 4). Hiển thị lựa chọn hiện tại, vd "Phường Tân Hưng, Quận 7".
     - Ô từ khoá: placeholder đổi luân phiên ("Phòng gần ĐH Bách Khoa…", "Có gác, giờ tự do…").
       Nếu người dùng gõ bắt đầu bằng "Phường " mà chưa chọn khu vực → gợi ý phường qua `resolve` (debounce 300ms).
     - Dropdown **Giá**: < 2 tr · 2–3 tr · 3–5 tr · 5–8 tr · > 8 tr · Tuỳ chỉnh (2 ô min/max).
       **Diện tích**: < 20 · 20–30 · 30–50 · > 50 m².
     - Nút **Tìm phòng** → `/tim-phong?district_id=&ward_id=&q=&price_min=&price_max=&area_min=&area_max=`.
     - Phím tắt: `/` để focus ô tìm, `Enter` để tìm, `Esc` đóng dropdown.
     - **Mobile:** thu thành 1 ô "Tìm phòng ở…"; chạm vào mở **bottom sheet toàn màn hình** có đủ các trường, nút
       "Tìm phòng" dính đáy.
   - Nút phụ cạnh thanh (hoặc ngay dưới): **"Định giá phòng của bạn →"** dẫn tới `/dinh-gia`.
   - Hàng **chip gợi ý** dưới thanh: "Dưới 3 triệu", "3–5 triệu", "Quận 7", "Bình Thạnh", "Gò Vấp" (chip quận lấy
     3 quận nhiều tin nhất từ API thật; bấm chip = điền sẵn bộ lọc).
3. **"Khám phá theo khu vực"** — lưới 8 **thẻ quận** (API thật, `sort=-listing_count`): tên quận, "16.088 tin",
   giá trung vị to ("5 tr/tháng"), **PriceRangeStrip**, "155.556 đ/m²", nhãn "Ít dữ liệu" nếu
   `priced_listing_count < 30`. Hover nổi nhẹ. Nút "Xem tất cả khu vực →".
4. **"Bảng giá thuê theo khu vực"** — danh sách xếp theo giá trung vị (`sort=-median_price`), mỗi dòng một
   PriceRangeStrip dài; công tắc **"Theo tháng / Theo m²"**; ô tìm quận nhỏ.
5. **"Tin mới cập nhật"** — 8 thẻ tin thật (`GET /listings?per_page=8`) kèm nhãn định giá, nút "Xem thêm".
6. **Khối "Định giá phòng trong 10 giây"** — mini form (khu vực + m²) gửi sang `/dinh-gia`.
7. **"Vì sao RoomBeacon"** — 3 cột ngắn: Giá minh bạch theo khu vực · Dữ liệu cập nhật hằng ngày · Không hiển
   thị thông tin cá nhân người đăng.
8. **Footer** — "Dữ liệu cập nhật: {loaded_at theo giờ VN} · Snapshot {8 ký tự đầu}", link Swagger cho dev.

## 3. Trang kết quả `/tim-phong`

- Thanh tìm kiếm thu nhỏ ở đầu trang, đồng bộ hai chiều với URL query (refresh không mất bộ lọc).
- Desktop 3 cột: **bộ lọc** trái (khu vực, giá, diện tích, sắp xếp) · **lưới tin** giữa · **thẻ thị trường** phải.
  Mobile: nút "Bộ lọc (n)" mở bottom sheet; thẻ thị trường nằm trên đầu danh sách.
- **Thẻ thị trường** (API thật): thẻ quận hoặc phường đang chọn — "Giá trung vị khu này **5 tr** (4,2–6,5 tr)",
  PriceRangeStrip, số tin.
- **Thẻ tin** (API thật `GET /listings`): ảnh placeholder 4:3 (gradient + icon, không dùng ảnh người khác), giá to "4,5 triệu/tháng",
  "25 m² · 180.000 đ/m²", dòng vị trí "Phường Tân Hưng, Quận 7", thời gian "3 ngày trước", nhãn nguồn nhỏ,
  và **nhãn định giá** từ `valuation` (brief mục 6): `TrendingDown` "Rẻ hơn ước tính 22%" (xanh) / `TrendingUp`
  "Cao hơn ước tính 8%" (đỏ) / "Sát ước tính"; `valuation = null` thì không hiện nhãn.
- Phân trang dưới cùng dựa trên `meta.pagination` (Trước · 1 2 3 … · Sau) + "Hiển thị 1–20 trên 5.873".

## 4. Location Picker (dùng chung cho mọi nơi)

- Desktop: popover/modal 480px neo dưới nút Khu vực. Mobile: bottom sheet.
- **Bước 1 — Quận:** ô tìm (debounce 300ms → `/api/v1/locations/districts?q=…&per_page=50`), mục đầu
  "Toàn TP.HCM", danh sách quận "Quận 7 · 16.088 tin · 5 tr", cuộn vô hạn theo `has_next`.
- **Bước 2 — Phường:** header "‹ Quận 7", mục đầu "Toàn Quận 7", danh sách phường từ
  `/api/v1/locations/districts/{id}/wards`, có ô tìm `q`.
- Gõ tên phường tự do khi chưa chọn quận → `resolve`: `200` chọn luôn; **`300`** hiện "Phường Tân Hưng — Quận 7 /
  Quận 12 / …" kèm số tin để chọn; `404` "Không tìm thấy, hãy chọn từ danh sách".
- Bàn phím: ↑/↓ di chuyển, `Enter` chọn, `Backspace` khi ô trống quay lại bước 1; ARIA combobox/listbox đúng chuẩn.
- Lưu 5 khu vực gần nhất vào `localStorage` (bọc try/catch), hiện ở đầu bước 1 dưới tiêu đề "Gần đây".

## 5. Trang khu vực `/khu-vuc/:districtId`

- Hero nhỏ: tên quận, 4 ô số liệu (Số tin · Giá trung vị · Giá/m² · Diện tích trung vị), PriceRangeStrip lớn.
- Lưới **thẻ phường** có sắp xếp (Nhiều tin / Giá cao / Giá thấp / Tên) và ô tìm.
- Nút "Tìm phòng ở Quận 7" → `/tim-phong?district_id=…`. Trang `/khu-vuc` (không id) = danh sách toàn bộ quận.

## 5b. Trang chi tiết tin `/phong/[id]` và trang định giá `/dinh-gia`

Làm đúng brief mục 7.3 và 7.4. Điểm nhấn thiết kế:
- **Định giá là tính năng "chữ ký"**: thẻ kết quả lớn, nền `--brand-soft`, con số chính là **khoảng giá**
  ("3,3 – 4,8 triệu/tháng"), bên dưới PriceRangeStrip so với thị trường thật của phường/quận, huy hiệu "Thử nghiệm"
  màu `--beacon` viền mảnh, cảnh báo dạng callout vàng nhạt, disclaimer chữ nhỏ `--muted`.
- Chi tiết tin: biểu đồ lịch sử giá dạng bậc thang (SVG tự vẽ), nút "Xem tin gốc" chỉ khi có `source_url`.

## 6. Trạng thái & chất lượng

- **Loading:** skeleton đúng hình thẻ (không spinner trơn). **Empty:** minh hoạ nhẹ + gợi ý nới bộ lọc.
- **Lỗi** theo bảng mã lỗi trong brief: 429 → toast "Thử lại sau {Retry-After} giây"; 503 → banner đầu trang và
  tự thử lại sau 30s; 500 → thông báo kèm `meta.request_id` nhỏ để báo lỗi; 401 → thông báo lỗi cấu hình (dev).
- `null` → "Chưa đủ dữ liệu", **không bao giờ hiển thị 0**. Định dạng số theo mục 8 của brief (`Intl.NumberFormat("vi-VN")`).
- Responsive từ 360px; không cuộn ngang; ảnh/placeholder giữ tỉ lệ; chạm tối thiểu 44px.
- Tôn trọng `prefers-reduced-motion`. Focus ring rõ ràng bằng `--brand`.

## 7. Kỹ thuật — Next.js

- **Next.js 16.3.6 App Router**, React 19.3.0, TypeScript 6.0.3 strict, Tailwind CSS 4.3.3 (+ `@tailwindcss/postcss`
  4.3.3), TanStack Query 5.103.2, lucide-react 1.48.0, `server-only` 0.0.1. **Ghim phiên bản chính xác** trong
  `package.json` (không `^`/`~`), commit `package-lock.json`. `output: "standalone"`.
- Scaffold vào `frontend/` (không dùng `src/`), giữ `.env.example` và `.gitignore` đã có.
- **Server-first:** trang chủ, trang khu vực, thẻ thị trường là **Server Components** lấy dữ liệu qua
  `lib/api/server.ts` (`import "server-only"`, kèm `X-API-Key`, `next: { revalidate }`). Chỉ SearchBar,
  LocationPicker, bộ lọc, phân trang tương tác là Client Components (`"use client"`).
- **BFF proxy** `app/api/rb/[...path]/route.ts` đúng như brief mục 3 (chỉ GET, whitelist `/locations/*`, timeout 10s,
  chuyển tiếp `Retry-After`/`ETag`/`X-Request-ID`). Client gọi `/api/rb/...` qua `lib/api/client.ts`, đọc envelope cho
  **mọi** mã HTTP (kể cả 300/4xx/5xx). Hook: `useDistricts`, `useWards`, `useResolveWard`, `useListings`, `useListing`, `usePriceHistory`, `useEstimate` (mutation), `useMarketDaily`.
- **SEO:** `generateMetadata` cho `/khu-vuc/[districtId]` ("Giá thuê phòng trọ Quận 7 — RoomBeacon", mô tả có giá
  trung vị); `app/sitemap.ts` liệt kê các trang khu vực; `robots.ts`.
- `loading.tsx` (skeleton) và `error.tsx` cho từng route; `not-found.tsx` thân thiện.
- `frontend/Dockerfile`: multi-stage (deps → build → runner `node:22-alpine` ghim tag cụ thể), copy
  `.next/standalone` + `.next/static` + `public`, chạy user không phải root, `EXPOSE 3000`, `CMD ["node","server.js"]`.
- Key **không** được xuất hiện trong client component, `NEXT_PUBLIC_*`, `localStorage`, log trình duyệt hay `.next/static`.
- Không thêm thư viện bản đồ; không vẽ ghim toạ độ; không hiển thị số điện thoại hay thông tin người đăng.

## 8. Thứ tự làm & tự kiểm tra

1. Scaffold Next.js (App Router, TypeScript, Tailwind, không `src/`) + token màu/font + layout (header/footer).
2. `lib/types/api.ts`, `lib/api/server.ts`, route handler `/api/rb/[...path]`, `lib/api/client.ts` + hook; gọi thử
   `/api/rb/locations/districts` từ trình duyệt và từ Server Component.
3. SearchBar + LocationPicker (kể cả xử lý `300`) → trang chủ đầy đủ.
4. Trang `/tim-phong` (tin thật + thẻ thị trường) → `/phong/[id]` (chi tiết + lịch sử giá) → `/dinh-gia` → `/khu-vuc/[id]` (xu hướng).
5. Trạng thái loading/empty/lỗi, dark mode, mobile bottom sheet, bàn phím/ARIA.
6. Kiểm tra cuối:
   - `npm run build` và `npx tsc --noEmit` không lỗi.
   - `npm run dev`, mở `http://localhost:3000`: thanh tìm kiếm ở giữa trang chủ; Location Picker chọn được
     "Quận 7 → Phường Tân Hưng"; gõ "Phường Tân Hưng" khi chưa chọn quận → hiện lựa chọn theo quận.
   - Không thấy chuỗi key trong bundle: `grep -r "$ROOMBEACON_API_KEY" .next/static` rỗng.
   - Xem nguồn trang `/khu-vuc/e2ed9f251d8cc334` thấy sẵn "Quận 7" và giá (render phía server).
   - Đi qua từng mục trong phần **11. Tiêu chí hoàn thành** của brief và đánh dấu.
7. Báo cáo: ảnh chụp trang chủ (desktop + mobile), Location Picker, trang kết quả, chi tiết tin, trang định giá
   (một kết quả có cảnh báo, vd 12 m² Quận 7) và trang khu vực.
