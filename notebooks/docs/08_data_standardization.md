# 08 — Chuẩn hóa Dữ liệu Tổng quát (General Data Standardization)

## 1. Kiến thức cốt lõi về Chuẩn hóa Dữ liệu

### 1.1 Data Standardization là gì?
- **Data Standardization (Chuẩn hóa dữ liệu cấu trúc/representation):** Là quá trình đưa dữ liệu về một định dạng tiêu chuẩn (Canonical Representation) thống nhất, dễ đoán và so sánh. Quá trình này **không** thay đổi ngữ nghĩa (Semantic) của dữ liệu.
- Phân biệt với **Statistical Standardization (Chuẩn hóa thống kê - z-score):** Việc chuyển biến về trung bình 0 và độ lệch chuẩn 1 (Z-score) dùng trong Machine Learning là chuẩn hóa phân phối, khác hoàn toàn với chuẩn hóa Representation trong Data Engineering.

### 1.2 Data Cleaning khác Data Standardization như thế nào?
- **Standardization:** Chỉnh sửa cách biểu diễn (ví dụ: cắt khoảng trắng dư, đưa Unicode về chuẩn NFC, thống nhất chữ hoa/thường cho category).
- **Cleaning:** Loại bỏ hoặc sửa đổi các dữ liệu bị sai lệch logic (ví dụ: giá phòng 1 tỷ USD -> lọc bỏ Outlier, hoặc map ward_name sai chính tả về đúng danh mục chuẩn).
- Standardization tạo tiền đề cho Cleaning dễ dàng hơn (Ví dụ: So sánh chuỗi sẽ không bị sai lệch do khoảng trắng hay Unicode ẩn).

### 1.3 Unicode Normalization (NFC, NFD)
- Văn bản tiếng Việt có thể biểu diễn dấu bằng nhiều cách:
  - **NFC (Normalization Form Canonical Composition):** Kết hợp các ký tự gốc và dấu thành một ký tự duy nhất (Ví dụ: `e` + `^` + `´` = `ế` - 1 ký tự).
  - **NFD (Normalization Form Canonical Decomposition):** Tách riêng chữ cái và các dấu (Ví dụ: `ế` = `e` + `^` + `´` - 3 ký tự).
- Hai chuỗi hiển thị giống hệt nhau trên màn hình nhưng nếu khác dạng (NFC vs NFD) thì máy tính sẽ đánh giá là khác nhau (`"ế" == "ế"` sẽ trả về `False`). Do đó, chuẩn hóa text tiếng Việt **bắt buộc** phải sử dụng `NFC` làm Canonical Representation.
- **NFKC/NFKD:** Các chuẩn có tính tương thích (Compatibility), có thể làm biến đổi các ký tự (Ví dụ: `1/2` thành ký tự `½`). Không nên dùng mặc định để tránh Lossy Transformation.

### 1.4 Lossless, Lossy và SOURCE-PRESERVING SEMANTICALLY LOSSLESS CANONICALIZATION
- **Lossless (Bảo toàn):** Không làm mất mát thông tin ngữ nghĩa (ví dụ Unicode NFC).
- **Lossy (Mất mát):** Thay đổi hẳn thông tin gốc (ví dụ: chuyển chuỗi thành lowercase, xóa dấu tiếng Việt). 
- **Reversible (Có thể đảo ngược):** Từ chuỗi kết quả có thể khôi phục 100% chuỗi ban đầu.
- **Idempotency (Tính lũy đẳng):** $f(f(x)) = f(x)$. Chạy hàm chuẩn hóa 2 lần không làm thay đổi giá trị so với chạy 1 lần.

### 1.5 Decimal vs Float
- Dữ liệu tài chính (`price_amount`) cần tính toán chính xác số học hệ cơ số 10.
- Nếu lưu bằng `FLOAT`, hệ nhị phân có thể sinh ra sai số (ví dụ: `0.1 + 0.2 = 0.30000000000000004`).
- `DECIMAL(15,2)` bảo toàn chính xác độ lớn tài chính. Không được tự ý ép kiểu (cast) về FLOAT.

### 1.6 Cấm Overwrite Raw Fields (Bảo toàn Source Truth)
- Tuyệt đối không lưu đè giá trị đã qua chuẩn hóa lên các cột raw (`title_raw`, `location_raw`). 
- Chúng ta sử dụng chiến lược sinh ra cột phái sinh (Derived Representation) như `title_normalized`.

---

## 2. Các Sơ đồ Kiến trúc (Mermaid)

### 2.1 Standardization Flow
```mermaid
flowchart TD
    A[Current Analytical Data]
        --> B[Representation Audit]

    B --> C{Có vấn đề representation?}

    C -->|Không| D[NO_TRANSFORMATION_REQUIRED]
    C -->|Có| E{Transformation an toàn?}

    E -->|Có| F[Derived Standardized Value]
    E -->|Không| G[DEFER / NOT_SAFE]

    F --> H[Before / After Validation]
    H --> I[Row & Identity Conservation]
```

### 2.2 Source Truth Concept
```mermaid
flowchart LR
    A[Crawl Output] --> B[(Bronze Layer: raw_data)]
    B --> C[Analytical: title_raw = '  Phòng trọ  ']
    C -.->|Xóa bỏ dấu vết| D[Sai: UPDATE title_raw = 'Phòng trọ']
    C -->|Phái sinh an toàn| E[Đúng: Tạo title_normalized = 'Phòng trọ']
```

### 2.3 Unicode NFC Transformation
```mermaid
flowchart TD
    A[String Đầu vào: e + ^ + ´] --> B[Unicode NFD Decoder]
    B --> C[NFC Composer]
    C --> D[String Đầu ra: ế]
    D --> E{So sánh Semantic?}
    E -->|Giống hoàn toàn| F[Lossless Canonical Representation]
```

### 2.4 Task Boundary (Ranh giới các Task)
```mermaid
flowchart TD
    A[Task 08: General Standardization] --> B(Whitespace, Unicode, Dtypes)
    B --> C[Task 09: Address Standardization]
    C --> D[Task 10: Ward Normalization]
    D --> E[Task 11: Price/Area Validation]
    A -.->|Không xâm phạm domain| C
    A -.->|Không xâm phạm domain| E
```

---

## 3. Runtime Audit & Phát hiện (Findings)

Notebook `02_roombeacon_silver.ipynb` computes the audit from the current snapshot instead of storing hard-coded counts in documentation. The standardization step must expose:

- tổng số text values được kiểm tra;
- số values có emoji/icon trang trí trước cleanup;
- số values có ký tự Unicode ẩn/control trước cleanup;
- số values thay đổi ở từng stage;
- số raw/source values thay đổi, bắt buộc bằng `0`;
- tối đa 16 ví dụ before/after kèm lý do thay đổi.

Sau chuẩn hóa, notebook chạy lại parser địa chỉ trên representation trước và sau hardening, rồi so sánh phân phối `parse_status`, component coverage và `UNRECOGNIZED_FORMAT`. Regression guard là `0.01%` số records; vượt ngưỡng phải được điều tra và giải thích trước khi tiếp tục Task 10–11.

---

## 4. Standardization Contract & Hướng giải quyết

Vì Text Fields bộc lộ Issue về Unicode và Khoảng trắng, ta thiết lập Contract sau:

| Field Gốc | Issue Phát hiện | Standardization Rule | Output Derived Field | Loss Risk | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `title_raw` | Unicode, invisible/control, icon, whitespace, punctuation noise | Shared Task 08 pipeline | `title_raw_normalized` | Source preserved; decorative representation removed | **APPLIED** |
| `full_address_text` | Unicode, invisible/control, icon, whitespace, empty comma segment | Shared Task 08 pipeline | `full_address_text_normalized` | Source preserved; decorative representation removed | **APPLIED** |
| `location_raw` | Unicode, invisible/control, icon, whitespace, punctuation noise | Shared Task 08 pipeline | `location_raw_normalized` | Source preserved; decorative representation removed | **APPLIED** |
| `best_address_text` | Unicode, invisible/control, icon, whitespace, empty comma segment | Shared Task 08 pipeline | `best_address_text_normalized` | Source preserved; decorative representation removed | **APPLIED** |
| `source_code` | None | None | N/A | N/A | NO_TRANSFORMATION |
| `price_amount` | None | None | N/A | N/A | NO_TRANSFORMATION |

### Chú ý về DEFERRED_TRANSFORMATIONS
- **Address Semantic Parsing:** Tách đường, phường, quận sẽ bị dời (DEFER) sang **Task 09**.
- **Map danh mục Phường/Xã (Ward Mapping):** Dời sang **Task 10**.
- **Price/Area Validation (Outlier, sửa Parse Gap):** Dời sang **Task 11**.

---

## 5. Kết luận Bảo toàn Dữ liệu (Conservation Result)

- **Row Conservation:** notebook assert số rows không đổi; không có thao tác drop row.
- **Identity Conservation:** notebook giữ nguyên toàn bộ source columns và identities.
- **Raw Preservation:** chuẩn hóa chỉ ghi vào derived columns; raw/source change count phải bằng `0`.
- **Idempotency:** toàn bộ pipeline, gồm NFC, artifact ẩn, emoji/icon, whitespace, punctuation và empty-to-null, được chạy lần hai và assert không đổi.
- **Semantic Preservation:** regression tests bảo vệ `/ - , . : ; # % + ₫ $ m²`, house numbers, ranges, decimal values, Vietnamese accents và price/area semantics. Emoji sequences không được để lại ZWJ, variation selector hoặc keycap artifact mồ côi.
