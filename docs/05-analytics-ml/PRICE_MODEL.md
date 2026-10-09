# Mô Hình Định Giá Cho Thuê (Rental Price Modeling)

> **Plane:** Analytics & ML
> **Trạng thái tài liệu:** AUTHORITATIVE
> **Trạng thái thành phần:** IMPLEMENTED
> **Kiểm chứng lần cuối:** 2026-10-06, commit `80d2c1f`
> **Liên quan:** [ANALYTICS_AND_GOLD.md](ANALYTICS_AND_GOLD.md), [SEARCH_AND_DISCOVERY.md](SEARCH_AND_DISCOVERY.md)

---

## 1. Kết Quả Benchmark V3 & Mô Hình Champion Đã Khóa

Quá trình nghiên cứu và đánh giá mô hình được thực hiện có phương pháp luận chặt chẽ tại [`notebooks/04_roombeacon_modeling.ipynb`](../../notebooks/04_roombeacon_modeling.ipynb), lưu vết tại `data/modeling/roombeacon_price_benchmark_v3/`:

- **Mô hình Champion được khóa:** `LightGBM Regressor`
- **Biến mục tiêu:** `price_model_value` (Giá thuê hàng tháng bằng VNĐ)
- **Phép biến đổi mục tiêu:** `RAW` (Không dùng log transform do RAW tối ưu MAE tốt hơn)
- **Tập đặc trưng được chọn:** **F4 — AREA + SOURCE + LOCATION**
  1. `area_value_clean` (Diện tích đã làm sạch)
  2. `source_code` (Mã sàn cào)
  3. `ward_current` (Tên phường hành chính hiện hành sau ánh xạ)
  4. `district_text_extracted` (Tên quận/huyện trích xuất)
- **Giao thức đánh giá:** Temporal & Group-Aware Split (Chia tập theo thời gian kết hợp nhóm tin trùng lặp để chống rò rỉ dữ liệu).

---

## 2. Bảng Chỉ Số Đánh Giá Trên Tập TEST Niêm Phong (Sealed Test)

Dưới đây là các chỉ số chính xác trích xuất từ [`final_test.csv`](../../data/modeling/roombeacon_price_benchmark_v3/final_test.csv):

| Mô hình / Đường cơ sở (Baseline) | Biến đổi | MAE (VNĐ) | Median AE (VNĐ) | RMSE (VNĐ) | $R^2$ | Fit Time (s) | Predict Time (s) |
|:---|:---:|---:|---:|---:|---:|---:|---:|
| **LightGBM Regressor (Champion)** | **RAW** | **904,290.83** | **624,464.82** | **1,333,621.37** | **0.2241** | 3.22 | 0.036 |
| Hierarchical Segment Median | RAW | 968,169.08 | 700,000.00 | 1,390,149.23 | 0.1569 | — | — |
| Hierarchical Location Median | RAW | 1,119,072.39 | 900,000.00 | 1,511,336.34 | 0.0035 | — | — |
| Global Median | RAW | 1,169,145.74 | 1,000,000.00 | 1,538,992.97 | -0.0333 | — | — |

### Nhận xét hiệu năng:
- Sai số tuyệt đối trung vị (Median AE) của Champion đạt **~624,000 VNĐ**, phản ánh mức sai số chấp nhận được cho phần lớn các tin đăng phòng trọ phổ thông.
- Champion cải thiện **22.65%** so với đường cơ sở trung vị toàn cục (Global Median) và cải thiện **19.19%** so với trung vị theo vị trí (Location Median).
- Thời gian dự báo siêu nhanh: chỉ **0.036 giây** cho toàn bộ tập test, sẵn sàng tích hợp vào API trực tuyến.

---

## 3. Kiểm Thử Bóng & Mức Độ Sẵn Sàng Vận Hành (Shadow Validation & Readiness)

Theo biên bản kết luận tại [`final_verdict.csv`](../../data/modeling/roombeacon_price_benchmark_v3/final_verdict.csv) và thử nghiệm trong [`notebooks/06_roombeacon_shadow_validation.ipynb`](../../notebooks/06_roombeacon_shadow_validation.ipynb):

- **Đánh giá mức độ sẵn sàng (Readiness):** `EXPERIMENTAL / PROTOTYPE-READY` — **CHƯA SẴN SÀNG PRODUCTION SERVING ĐỘC LẬP**.
- **Lý do hạn chế:** Dữ liệu huấn luyện hiện mới chỉ nằm trong cửa sổ thời gian hẹp khoảng 10 ngày (20/09/2026 – 30/09/2026). Dữ liệu này chưa trải qua chu kỳ biến động theo mùa (đầu năm học, sau Tết) nên chưa chứng minh được độ bền vững phân phối dài hạn.
- **Quy trình Shadow Validation:** Khi có dữ liệu cào mới, mô hình chạy suy luận ngầm (shadow mode), không trả kết quả trực tiếp cho người dùng mà ghi log append-only tại `data/modeling/shadow_validation/runs/` để theo dõi hiện tượng suy giảm hiệu năng (Model Drift).
