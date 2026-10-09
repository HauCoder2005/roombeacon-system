# Prompt cho Antigravity — dựng giao diện RoomBeacon

> Dán toàn bộ khối dưới đây vào Antigravity (agent mode), mở đúng thư mục gốc repo.

---

Bạn là một **senior frontend engineer kiêm product designer**. Hãy dựng giao diện web cho **RoomBeacon** —
nền tảng tìm phòng trọ / nhà thuê tại **TP.HCM** dựa trên dữ liệu thật đã được thu thập và phân tích.

## 0. Đọc trước khi làm

1. Đọc kỹ **`docs/06-serving/frontend-ui-brief.md`**. Đây là **nguồn sự thật** về API (endpoint, kiểu dữ liệu,
   ví dụ response thật, mã lỗi, phần nào có thật / phần nào phải mock). Nếu prompt này và brief mâu thuẫn
   về API, **brief thắng**.
2. Backend đang chạy ở máy local: `http://127.0.0.1:8000` (Swagger: `http://127.0.0.1:8000/docs`).
   Biến môi trường nằm trong `frontend/.env.local` (mẫu: `frontend/.env.example`):
   - `ROOMBEACON_API_URL` — địa chỉ backend
   - `ROOMBEACON_API_KEY` — key gốc, **chỉ** proxy dev được đọc
   - `VITE_API_BASE_PATH=/api/v1`, `VITE_DEV_PORT=5173`
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
   - Hàng **chip gợi ý** dưới thanh: "Dưới 3 triệu", "3–5 triệu", "Quận 7", "Bình Thạnh", "Gò Vấp" (chip quận lấy
     3 quận nhiều tin nhất từ API thật; bấm chip = điền sẵn bộ lọc).
3. **"Khám phá theo khu vực"** — lưới 8 **thẻ quận** (API thật, `sort=-listing_count`): tên quận, "16.088 tin",
   giá trung vị to ("5 tr/tháng"), **PriceRangeStrip**, "155.556 đ/m²", nhãn "Ít dữ liệu" nếu
   `priced_listing_count < 30`. Hover nổi nhẹ. Nút "Xem tất cả khu vực →".
4. **"Bảng giá thuê theo khu vực"** — danh sách xếp theo giá trung vị (`sort=-median_price`), mỗi dòng một
   PriceRangeStrip dài; công tắc **"Theo tháng / Theo m²"**; ô tìm quận nhỏ.
5. **"Tin mới đăng"** — lưới thẻ tin từ **mock** (ghi rõ trong code là mock), 8 tin, nút "Xem thêm".
6. **"Vì sao RoomBeacon"** — 3 cột ngắn: Giá minh bạch theo khu vực · Dữ liệu cập nhật hằng ngày · Không hiển
   thị thông tin cá nhân người đăng.
7. **Footer** — "Dữ liệu cập nhật: {loaded_at theo giờ VN} · Snapshot {8 ký tự đầu}", link Swagger cho dev.

## 3. Trang kết quả `/tim-phong`

- Thanh tìm kiếm thu nhỏ ở đầu trang, đồng bộ hai chiều với URL query (refresh không mất bộ lọc).
- Desktop 3 cột: **bộ lọc** trái (khu vực, giá, diện tích, sắp xếp) · **lưới tin** giữa · **thẻ thị trường** phải.
  Mobile: nút "Bộ lọc (n)" mở bottom sheet; thẻ thị trường nằm trên đầu danh sách.
- **Thẻ thị trường** (API thật): thẻ quận hoặc phường đang chọn — "Giá trung vị khu này **5 tr** (4,2–6,5 tr)",
  PriceRangeStrip, số tin.
- **Thẻ tin** (mock): ảnh placeholder 4:3 (gradient + icon, không dùng ảnh người khác), giá to "4,5 triệu/tháng",
  "25 m² · 180.000 đ/m²", dòng vị trí "Phường Tân Hưng, Quận 7", thời gian "3 ngày trước", nhãn nguồn nhỏ,
  và **nhãn so sánh** tính từ median khu vực: `TrendingDown` "Rẻ hơn mặt bằng 12%" (xanh) / `TrendingUp`
  "Đắt hơn mặt bằng 8%" (đỏ) / "Ngang mặt bằng" (±5%).
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

## 6. Trạng thái & chất lượng

- **Loading:** skeleton đúng hình thẻ (không spinner trơn). **Empty:** minh hoạ nhẹ + gợi ý nới bộ lọc.
- **Lỗi** theo bảng mã lỗi trong brief: 429 → toast "Thử lại sau {Retry-After} giây"; 503 → banner đầu trang và
  tự thử lại sau 30s; 500 → thông báo kèm `meta.request_id` nhỏ để báo lỗi; 401 → thông báo lỗi cấu hình (dev).
- `null` → "Chưa đủ dữ liệu", **không bao giờ hiển thị 0**. Định dạng số theo mục 8 của brief (`Intl.NumberFormat("vi-VN")`).
- Responsive từ 360px; không cuộn ngang; ảnh/placeholder giữ tỉ lệ; chạm tối thiểu 44px.
- Tôn trọng `prefers-reduced-motion`. Focus ring rõ ràng bằng `--brand`.

## 7. Kỹ thuật

- **Vite + React 18 + TypeScript (strict) + Tailwind CSS + TanStack Query + React Router + lucide-react.**
- Scaffold vào `frontend/` (giữ `.env.example`, `.gitignore`). **Ghim phiên bản chính xác** trong `package.json`
  (không `^`/`~`), commit `package-lock.json`.
- `vite.config.ts`: đọc `ROOMBEACON_API_URL`, `ROOMBEACON_API_KEY`, `VITE_DEV_PORT` bằng `loadEnv(mode, cwd, "")`;
  proxy `/api` → `ROOMBEACON_API_URL` và **chèn header `X-API-Key` phía proxy**. Key **không** được xuất hiện trong
  bundle, `import.meta.env`, `localStorage` hay log trình duyệt.
- Lớp dữ liệu `src/api/`: `client.ts` đọc envelope cho **mọi** mã HTTP (kể cả 300/4xx/5xx, không ném lỗi mù);
  `locations.ts` (API thật); `listings.mock.ts` (mock, cùng chữ ký với API dự kiến). Component chỉ gọi hook
  `useDistricts`, `useWards`, `useResolveWard`, `useListings`.
- Cấu trúc thư mục theo mục 9 của brief. Tách component nhỏ, không file > 300 dòng.
- Không thêm thư viện bản đồ; không vẽ ghim toạ độ; không hiển thị số điện thoại hay thông tin người đăng.

## 8. Thứ tự làm & tự kiểm tra

1. Scaffold + Tailwind + token màu/font + layout (header/footer).
2. `src/types/api.ts`, `src/api/*`, hook TanStack Query; gọi thử `/api/v1/locations/districts` qua proxy.
3. SearchBar + LocationPicker (kể cả xử lý `300`) → trang chủ đầy đủ.
4. Trang `/tim-phong` (mock tin + thẻ thị trường thật) → trang `/khu-vuc/:id`.
5. Trạng thái loading/empty/lỗi, dark mode, mobile bottom sheet, bàn phím/ARIA.
6. Kiểm tra cuối:
   - `npm run build` và `npx tsc --noEmit` không lỗi.
   - `npm run dev`, mở `http://localhost:5173`: thanh tìm kiếm ở giữa trang chủ; Location Picker chọn được
     "Quận 7 → Phường Tân Hưng"; gõ "Phường Tân Hưng" khi chưa chọn quận → hiện lựa chọn theo quận.
   - Tìm trong `dist/` không thấy chuỗi key (`grep -r "$ROOMBEACON_API_KEY" dist` rỗng).
   - Đi qua từng mục trong phần **11. Tiêu chí hoàn thành** của brief và đánh dấu.
7. Báo cáo: ảnh chụp trang chủ (desktop + mobile), Location Picker, trang kết quả; danh sách những gì đang là mock.
