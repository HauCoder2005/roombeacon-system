# BÁO CÁO KIỂM TOÁN TÍNH SẴN SÀNG CỦA DỮ LIỆU TRƯỚC EDA (PRE-EDA DATA READINESS REPORT)

Tài liệu này xác lập kết quả kiểm toán toàn diện về chất lượng, độ bao phủ và tính toàn vẹn của dữ liệu trong hệ thống **RoomBeacon** trước khi tiến hành bước Phân tích Dữ liệu Khám phá (Exploratory Data Analysis - EDA).

---

## 1. Mục Tiêu Kiểm Toán Pre-EDA (Audit Objectives)

1. **Xác minh tính bảo toàn định lượng (Metric Conservation)**: Đảm bảo toàn bộ chỉ số cào, phân loại tin mới/cũ, số lượng quan sát theo nguồn và hàng đợi hoãn cào chi tiết cân bằng chính xác 100% trên cùng một snapshot dữ liệu nhất quán.
2. **Phân định rạch ròi 2 cấp độ đo lường độ bao phủ**:
   - **Tầng Quan Sát Lịch Sử (Observation Level)**: Mẫu số là tổng số phiên bản quan sát `rental_post_versions`.
   - **Tầng Tin Đăng Mới Nhất (Latest Unique Listing Level)**: Mẫu số là tập hợp các tin bài duy nhất `v_latest_posts` (1 dòng duy nhất cho mỗi `rental_post_id`).
3. **Kiểm toán chất lượng dữ liệu Bronze thực tế**: Xác minh số lượng bản ghi trên 12 bảng MySQL Bronze Primary và tính nhất quán đồng bộ sang Ubuntu Read-Only Replica.
4. **Đánh giá chất lượng dữ liệu số và vị trí**: Nhận diện các giá trị bất thường, thiếu hụt hoặc dị biệt để định hình chiến lược tiền xử lý cho EDA.
5. **Kiểm tra luồng kết nối phân tích DuckDB $\rightarrow$ Pandas DataFrame**: Đảm bảo chuyên viên phân tích có thể truy vấn trực tiếp từ DuckDB Analytical Views vào DataFrame mà không cần xuất file CSV cồng kềnh.

---

## 2. Phân Tầng Dữ Liệu: Observations vs Latest-Listing

### 2.1. Tầng Quan Sát Lịch Sử (Temporal Observations - `v_observations`)
Mỗi lần crawler quét qua danh sách hoặc cào trang chi tiết, một bản ghi `rental_post_versions` mới được tạo kèm nhãn thời gian `observed_at`.
- **Mục đích phân tích**: Nghiên cứu động thái thị trường theo chuỗi thời gian (Time-Series Analysis), đo lường tuổi thọ tin đăng (Listing Lifetime), tốc độ điều chỉnh giá thuê (Price Adjustments), và tần suất làm mới tin bài của chủ trọ.
- **Quy mô hiện tại**: **40.644 quan sát lịch sử** (khớp 1:1 với bảng `rental_post_versions` trong MySQL Primary).

### 2.2. Tầng Tin Đăng Mới Nhất (Latest Unique Listings - `v_latest_posts`)
Trích xuất quan sát mới nhất của từng bài đăng độc nhất bằng thuật toán xếp hạng cửa sổ đơn định:
```sql
ROW_NUMBER() OVER (
    PARTITION BY p.id
    ORDER BY v.observed_at DESC, v.id DESC
) AS rn
```
Lọc `rn = 1` đảm bảo **mỗi tin đăng chỉ xuất hiện duy nhất 1 lần**.
- **Mục đích phân tích**: Thống kê mô tả cắt ngang thị trường (Cross-sectional EDA) như phân bố giá trung bình theo quận, diện tích phổ biến, cơ cấu loại phòng.
- **Quy mô hiện tại**: **9.155 tin đăng độc nhất** (`duplicate rental_post_id = 0`).
- **Ý nghĩa sống còn**: Nếu phân tích EDA mô tả trực tiếp trên tầng quan sát lịch sử, các tin đăng được quét lặp lại nhiều lần (ví dụ: NhaTroVN trung bình 26,77 lần/tin) sẽ bị **thổi phồng trọng số (Multiplication Bias)**, làm méo mó hoàn toàn các phân vị và giá trị trung bình thị trường.

---

## 3. Độ Bao Phủ Thuộc Tính Phân Cấp Rạch Ròi (Separation of Coverage Levels)

### 3.1. Cấp Độ Quan Sát (Observation Level — Mẫu số: 40.644 observations)
Đo lường tỷ lệ các thuộc tính xuất hiện trên toàn bộ 40.644 lượt quét lịch sử:
- **Quan sát có giá (Observations with Price)**: 40.571 / 40.644 = **99,82%** (Thiếu giá: 73).
- **Quan sát có diện tích (Observations with Area)**: 10.321 / 40.644 = **25,39%** (Không có diện tích: 30.323).
- **Quan sát có địa chỉ (Observations with Address)**: 38.525 / 40.644 = **94,79%** (Thiếu địa chỉ: 2.119).

### 3.2. Cấp Độ Tin Đăng Độc Nhất (Latest Unique Listing Level — Mẫu số: 9.155 listings)
Đo lường độ bao phủ thực tế trên 9.155 tin bài độc nhất phục vụ trực tiếp cho bài toán EDA:
- **Độ bao phủ Giá (Price Coverage)**: 9.149 / 9.155 = **99,93%** (Thiếu giá: 6).
- **Độ bao phủ Diện Tích (Area Coverage)**: 8.007 / 9.155 = **87,46%** (Thiếu/không hợp lệ: 1.148).
- **Độ bao phủ Địa Chỉ (Address Coverage)**: 7.460 / 9.155 = **81,49%** (Thiếu địa chỉ: 1.695).
- **Độ bao phủ Ảnh (Images Metadata Coverage)**: 9.111 / 9.155 = **99,52%** (Thiếu ảnh: 44).
- **Độ bao phủ Chi Tiết Chuyên Sâu (Detail Coverage)**: 3 / 9.155 = **0,03%** (Tin quan sát nhẹ: 9.152).

---

## 4. Phân Bố Dữ Liệu Theo Nguồn Thu Thập (Source Distribution)

Tất cả các chỉ số dưới đây được kết xuất đồng thời từ **một database snapshot nhất quán**:

| Nguồn | Unique Posts | Observations | Avg Obs/Post | Price Cov | Area Cov | Addr Cov | Img Cov | Detail Cov |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **phongtro123** | 6.972 | 8.249 | 1,18 | 99,9% | 100,0% | 81,8% | 100,0% | 0,0% |
| **nhatrovn** | 1.148 | 30.734 | 26,77 | 99,9% | 0,3% | 100,0% | 96,2% | 0,3% |
| **nhatot** | 1.006 | 1.547 | 1,54 | 100,0% | 100,0% | 57,9% | 100,0% | 0,0% |
| **batdongsan** | 29 | 114 | 3,93 | 100,0% | 100,0% | 100,0% | 100,0% | 0,0% |
| **TỔNG CỘNG** | **9.155** | **40.644** | **4,44** | **99,93%** | **87,46%** | **81,49%** | **99,52%** | **0,03%** |

### Định Luật Bảo Toàn Dữ Liệu (Conservation Checks):
$$\sum \text{source\_observations} = 8.249 + 30.734 + 1.547 + 114 = 40.644 = \text{COUNT(rental\_post\_versions)} \quad [\textbf{PASS}]$$

$$\sum \text{source\_unique\_posts} = 6.972 + 1.148 + 1.006 + 29 = 9.155 = \text{COUNT(rental\_posts)} = \text{COUNT}(v\_latest\_posts) \quad [\textbf{PASS}]$$

> [!NOTE]
> **Nhận định về nguồn NhaTroVN**:
> - `nhatrovn` có 1.148 bài đăng độc nhất nhưng chiếm tới 30.734 quan sát lịch sử (mật độ 26,77 quan sát/tin).
> - Điều này phản ánh chính xác hoạt động cào quét định kỳ kiểm thử cơ chế Historical Frontier và Deferred Detail Backlog.
> - Thẻ danh mục của NhaTroVN thường không chứa diện tích thô trên trang danh sách, dẫn đến Area Coverage trên tầng thẻ là 0,3%, nhưng độ phủ địa chỉ và ảnh đều đạt xấp xỉ 100%.

---

## 5. Kiểm Toán Chất Lượng Dữ Liệu Số (Data Quality Audit)

### 5.1. Dữ Liệu Giá (Price Quality)
- Giá hợp lệ (> 0): 9.149 tin độc nhất (40.571 quan sát).
- Giá $\le$ 0: **0 bản ghi** (Không có giá âm hoặc bằng 0).
- Giá dị biệt (> 100 triệu VNĐ): 0 bản ghi.

### 5.2. Dữ Liệu Diện Tích (Area Quality)
- Diện tích hợp lệ (> 0): 8.007 tin độc nhất (10.321 quan sát).
- Diện tích $\le$ 0: 3 tin đăng ở tầng mới nhất (6 quan sát ở tầng thô). Đã được nhận diện và xử lý gán `NULL` ở tầng analytical views.
- Diện tích bất thường (> 1.000 $m^2$): **0 bản ghi**.

### 5.3. Địa Chỉ & Tọa Độ (Location Quality)
- Địa chỉ đầy đủ (`full_address_text`): 7.460 tin độc nhất (81,49%).
- Tọa độ GPS (`latitude`/`longitude`): **NOT AVAILABLE** (Crawler không thu thập tọa độ thô do nguồn web công khai không cung cấp).

---

## 6. Kiến Trúc Phân Tích & Luồng Kết Nối DuckDB $\rightarrow$ Pandas

```
┌─────────────────────────────────────────────────────────┐
│                    MySQL Bronze Primary                 │
│         (12 Bảng dữ liệu thô - Bind-mounted Host Disk)  │
└────────────────────────────┬────────────────────────────┘
                             │  ATTACH (READ_ONLY)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    DuckDB Analytics Engine              │
│  - v_observations (40.644 dòng quan sát lịch sử)        │
│  - v_latest_posts (9.155 dòng tin đăng độc nhất)        │
│  - 7 views bổ trợ: lifetime, price_history, quality...  │
└────────────────────────────┬────────────────────────────┘
                             │  d_conn.execute(...).df()
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    Pandas DataFrame / EDA               │
│         (Phân tích thống kê, trực quan hóa biểu đồ)     │
└─────────────────────────────────────────────────────────┘
```

Mã mẫu tải trực tiếp dữ liệu sạch vào DataFrame (không cần CSV):
```python
import duckdb
from analytics.duckdb.views import DuckDBViewManager

conn = duckdb.connect()
conn.execute("INSTALL mysql; LOAD mysql;")
conn.execute("ATTACH 'host=127.0.0.1 port=3307 user=codeser password=... database=roombeacon_bronze' AS mysql_db (TYPE MYSQL, READ_ONLY);")

DuckDBViewManager.create_views(conn)

# Lấy 1 dòng cho mỗi tin đăng độc nhất:
df_latest = conn.execute("SELECT * FROM v_latest_posts").df()
print("Kích thước DataFrame:", df_latest.shape)  # (9155, 12)
```

---

## 7. Quyết Định Sẵn Sàng Cho EDA (EDA Readiness Decision)

- **Trạng thái**: **READY (SẴN SÀNG)**.
- **Nguồn dữ liệu khuyến nghị cho EDA**: **DuckDB `v_latest_posts`** (kết hợp `v_observations` khi phân tích biến động theo thời gian).
- **Lý do**:
  1. Toàn bộ định luật bảo toàn quan sát và tin độc nhất đều đạt **PASS 100%**.
  2. Bảng `v_latest_posts` đảm bảo tuyệt đối tính chất One-Row-Per-Listing (`duplicate rental_post_id = 0`).
  3. Độ bao phủ giá (99,93%), diện tích (87,46%), địa chỉ (81,49%) và ảnh (99,52%) đạt chuẩn chất lượng cao.
  4. Không có lỗi chặn kỹ thuật. Không cần xây dựng tầng Silver nhân tạo trước khi EDA khám phá các phân phối thực tế.
