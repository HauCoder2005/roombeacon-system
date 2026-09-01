# Price Outlier Analysis - Phân tích giá trị bất thường của giá thuê

## 1. Mục tiêu phân tích

Trong quá trình khám phá dữ liệu (Exploratory Data Analysis - EDA), việc phát hiện các giá trị bất thường (outlier) là một bước quan trọng nhằm đánh giá chất lượng dữ liệu trước khi xây dựng bộ dữ liệu sạch (Silver Dataset).

Đối với RoomBeacon, trường dữ liệu quan trọng được phân tích là:

- `monthly_price`: Giá thuê theo tháng.
- `price_million`: Giá thuê đã được chuẩn hóa về đơn vị triệu đồng/tháng.
- `current_location`: Khu vực/phường hiện tại sau bước chuẩn hóa địa lý.

Mục tiêu của bước phân tích outlier không phải là loại bỏ ngay các giá trị có giá cao hoặc thấp bất thường, mà nhằm trả lời các câu hỏi:

- Giá trị này có phải lỗi dữ liệu không?
- Giá trị này có phải do crawler lấy sai dữ liệu không?
- Hay đây là một listing hợp lệ nhưng thuộc phân khúc thuê khác?

Trong dữ liệu thực tế từ crawler, một giá trị khác biệt về mặt thống kê chưa chắc là dữ liệu sai. Vì vậy cần kết hợp phương pháp thống kê và kiểm tra ngữ cảnh thực tế của từng listing.

---

# 2. Quan sát ban đầu từ phân bố giá

Thông qua biểu đồ Boxplot:

```
Monthly Rental Price Distribution by Ward
```

có thể quan sát:

- Phần lớn dữ liệu giá thuê tập trung trong khoảng:

```
2 - 6 triệu đồng/tháng
```

- Median của phần lớn phường nằm khoảng:

```
3 - 4 triệu đồng/tháng
```

Điều này cho thấy phần lớn dữ liệu đang phản ánh nhóm phòng thuê phổ biến, phù hợp với nhóm người thuê là học sinh, sinh viên.

Tuy nhiên, một số điểm dữ liệu nằm ngoài vùng phân bố chính xuất hiện ở nhiều phường khác nhau.

Các giá trị này được đánh dấu là outlier theo phương pháp thống kê và cần được kiểm tra thêm.

---

# 3. Phương pháp phát hiện Outlier

RoomBeacon sử dụng phương pháp IQR (Interquartile Range) để phát hiện outlier.

Khác với cách tính trên toàn bộ dataset, hệ thống thực hiện tính toán theo từng nhóm địa lý (`current_location`).

Lý do:

Giá thuê phụ thuộc rất lớn vào vị trí.

Ví dụ:

- Một phòng giá 8 triệu/tháng tại khu vực trung tâm có thể là mức giá hợp lý.
- Nhưng cùng mức giá đó tại một khu vực ngoại thành có thể được xem là cao.

Do đó, việc áp dụng một ngưỡng chung cho toàn bộ thành phố có thể gây sai lệch.

Quy trình:

```
current_location
        |
        ↓
Chia dữ liệu theo từng phường
        |
        ↓
Tính Q1 và Q3 cho từng nhóm
        |
        ↓
Tính IQR
        |
        ↓
Xác định các giá trị khác biệt
```

---

# 4. Công thức IQR

Với mỗi nhóm dữ liệu:

## Q1 (Quartile 1)

Q1 là giá trị tại phân vị 25%.

Nó đại diện cho mức giá mà 25% dữ liệu nhỏ hơn hoặc bằng giá trị này.

## Q3 (Quartile 3)

Q3 là giá trị tại phân vị 75%.

Nó đại diện cho mức giá mà 75% dữ liệu nhỏ hơn hoặc bằng giá trị này.

## IQR

Công thức:

```
IQR = Q3 - Q1
```

IQR thể hiện khoảng phân bố của 50% dữ liệu trung tâm.

---

Khoảng giá được xem là bình thường:

```
Lower Bound = Q1 - 1.5 * IQR

Upper Bound = Q3 + 1.5 * IQR
```

Các giá trị:

```
price < Lower Bound

hoặc

price > Upper Bound
```

được đánh dấu là outlier.

---

# 5. Triển khai trong Python

Hàm phát hiện outlier:

```python
def get_outliers(df, group_col, value_col):

    def iqr_outliers(group):

        q1 = group[value_col].quantile(0.25)
        q3 = group[value_col].quantile(0.75)

        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        return group[
            (group[value_col] < lower) |
            (group[value_col] > upper)
        ]

    return (
        df.groupby(
            group_col,
            group_keys=False
        )
        .apply(iqr_outliers)
    )
```

Áp dụng cho dữ liệu RoomBeacon:

```python
outliers = get_outliers(
    plot_df_price,
    group_col="current_location",
    value_col="price_million"
)
```

Trong đó:

- `group_col="current_location"`:
    - Tính toán riêng theo từng phường.

- `value_col="price_million"`:
    - Phân tích biến giá thuê theo triệu đồng.

---

# 6. Kiểm tra thực tế các giá trị Outlier

Sau khi phát hiện bằng IQR, các giá trị này không được xóa ngay.

Các trường thông tin được sử dụng để kiểm tra:

- `title`
- `price_million`
- `area_m2`
- `domain`
- `address`

Mục đích là xác định nguyên nhân của sự khác biệt.

Ví dụ:

| Giá thuê | Diện tích | Nội dung | Đánh giá |
|---|---|---|---|
| 10 triệu | 100m² | Thuê nguyên lầu | Giá hợp lý |
| 10 triệu | 50m² | Căn hộ 2 phòng ngủ | Giá hợp lý |
| 8.6 triệu | 40m² | Studio full nội thất | Giá hợp lý |
| 8-10 triệu | 20-30m² | Phòng cao cấp gần trường | Cần đánh giá thêm |

---

# 7. Kết quả phân tích

Sau khi kiểm tra các giá trị bị đánh dấu là outlier, nhận thấy:

Phần lớn các giá trị cao không phải lỗi dữ liệu.

Các nguyên nhân chính:

## 7.1. Khác biệt về loại hình thuê

Dataset crawler hiện tại có thể chứa nhiều loại hình:

- Phòng trọ truyền thống.
- Studio.
- Căn hộ mini.
- Căn hộ nhiều phòng ngủ.
- Ký túc xá cao cấp.
- Thuê nguyên tầng/nguyên căn.

Các loại hình này có mức giá khác nhau.

Ví dụ:

```
Phòng trọ 20m²
```

và:

```
Căn hộ 50m²
```

không nên được đánh giá cùng một tiêu chuẩn.

---

## 7.2. Khác biệt về tiện ích

Một số listing có:

- Nội thất đầy đủ.
- Ban công.
- Máy lạnh.
- Vị trí gần trường đại học.
- Khu vực trung tâm.

Do đó giá cao hơn là hợp lý.

---

# 8. Quyết định Cleaning

Dựa trên kết quả phân tích:

Không loại bỏ các giá trị cao chỉ dựa trên phương pháp IQR.

Lý do:

IQR chỉ cho biết:

> Giá trị này khác biệt so với phần lớn dữ liệu.

Nó không chứng minh:

> Giá trị này sai.

Vì vậy:

Các giá trị như:

```
8 - 10 triệu/tháng
```

vẫn được giữ lại trong dataset.

---

Chỉ loại bỏ những trường hợp có bằng chứng rõ ràng:

- Giá trị không thực tế.
- Sai đơn vị tiền tệ.
- Parser lấy nhầm dữ liệu.
- Giá bán bị nhầm thành giá thuê.
- Giá trị vượt xa thực tế thị trường.

Ví dụ:

```
7.777.000.000 đồng/tháng
```

cho một phòng trọ nhỏ sẽ cần kiểm tra lại.

---

# 9. Hướng phát triển tiếp theo

Kết quả phân tích outlier cho thấy vấn đề chính không nằm ở việc loại bỏ giá cao, mà nằm ở việc dataset chưa có phân loại loại hình thuê.

Feature cần bổ sung trong tương lai:

```
listing_type
```

Ví dụ:

```
room
studio
apartment
house
dormitory
whole_floor
```

Feature này giúp mô hình sau này hiểu được sự khác biệt giữa:

```
Phòng 20m² giá 10 triệu
```

và:

```
Căn hộ 50m² giá 10 triệu
```

---

# 10. Trạng thái hiện tại

Đã hoàn thành:

- Xây dựng Boxplot phân bố giá theo phường.
- Xác định outlier bằng IQR theo từng khu vực.
- Kiểm tra thủ công các giá trị bất thường.
- Xác định phần lớn outlier là listing hợp lệ.

Chưa thực hiện:

- Loại bỏ dữ liệu lỗi.
- Phân loại listing_type.
- Xây dựng cleaning rule cuối cùng.

Kết luận hiện tại:

> Outlier trong dữ liệu RoomBeacon chủ yếu phản ánh sự khác biệt về phân khúc thuê thay vì lỗi dữ liệu. Vì vậy cần giữ lại các giá trị này và tiếp tục phân tích loại hình thuê trước khi thực hiện cleaning cuối cùng.