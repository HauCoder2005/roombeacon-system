# Seaborn Visualization Guide

## 1. Overview

Seaborn là thư viện visualization xây dựng trên nền Matplotlib, tập trung vào:

- Exploratory Data Analysis (EDA)
- Statistical visualization
- Visualization trực tiếp từ Pandas DataFrame
- Biểu diễn nhiều chiều dữ liệu thông qua:
    - Position
    - Color
    - Size
    - Shape


Trong RoomBeacon, Seaborn được sử dụng để:

- Phân tích phân phối giá thuê.
- Phát hiện outlier.
- Phân tích quan hệ giữa:
    - diện tích
    - giá thuê
    - khu vực
    - nguồn cung.


---

# 2. Setup cơ bản


```python
import seaborn as sns
import matplotlib.pyplot as plt


sns.set_theme(
    style="whitegrid"
)
```


## set_theme()

Thiết lập giao diện chung cho toàn bộ biểu đồ.

Một số style phổ biến:

```python
sns.set_theme(style="white")
sns.set_theme(style="dark")
sns.set_theme(style="whitegrid")
sns.set_theme(style="darkgrid")
sns.set_theme(style="ticks")
```


Ví dụ:

```python
sns.set_theme(
    style="whitegrid"
)
```

Tạo:

- nền trắng
- có grid
- dễ đọc giá trị


---

# 3. Relationship Plot (relplot)

## 3.1 Tổng quan


`relplot()` dùng để biểu diễn mối quan hệ giữa các biến.


Cấu trúc:

```
DataFrame

      |
      |

x variable  -------->  vị trí ngang

y variable  -------->  vị trí dọc

hue          -------->  màu sắc

size         -------->  kích thước điểm
```


Ví dụ:

```python
g = sns.relplot(
    data=df,

    x="area_m2",

    y="monthly_price",

    hue="current_location",

    size="monthly_price"
)
```


Ý nghĩa:

| Thành phần | Ý nghĩa |
|-|-|
| x | biến trên trục X |
| y | biến trên trục Y |
| hue | nhóm bằng màu |
| size | kích thước điểm |


---

# 4. Example: Scatterplot with continuous hues and sizes


Ví dụ Seaborn:


```python
import seaborn as sns


sns.set_theme(
    style="whitegrid"
)


planets = sns.load_dataset(
    "planets"
)


cmap = sns.cubehelix_palette(
    rot=-.2,
    as_cmap=True
)


g = sns.relplot(

    data=planets,

    x="distance",

    y="orbital_period",

    hue="year",

    size="mass",

    palette=cmap,

    sizes=(10,200)

)
```


---

# 5. Giải thích các tham số trong relplot()


## data


```python
data=planets
```


DataFrame nguồn.


Trong RoomBeacon:


```python
data=df_work
```


Ví dụ:


```
df_work

room_id
price
area
location
```


---

## x và y


```python
x="distance"

y="orbital_period"
```


Xác định hai biến cần quan sát.


Ví dụ RoomBeacon:


```python
x="area_m2"

y="monthly_price"
```


Câu hỏi:

> Diện tích có ảnh hưởng đến giá thuê không?


---

## hue


```python
hue="year"
```


Dùng màu để biểu diễn thêm một chiều dữ liệu.


Ví dụ:


```python
hue="current_location"
```


Kết quả:


```
Phường A  → màu 1

Phường B  → màu 2

Phường C  → màu 3
```


---

## size


```python
size="mass"
```


Dùng kích thước điểm để biểu diễn giá trị.


Ví dụ RoomBeacon:


```python
size="monthly_price"
```


Giá cao:

```
●
```


Giá thấp:

```
•
```


---

# 6. Color palette


```python
cmap = sns.cubehelix_palette(
    rot=-0.2,
    as_cmap=True
)
```


Tạo bảng màu.


`cubehelix_palette()` phù hợp cho dữ liệu liên tục vì:

- dễ phân biệt mức độ
- nhìn tốt khi in
- tăng giảm độ sáng theo giá trị


---

# 7. Log scale


```python
g.set(
    xscale="log",
    yscale="log"
)
```


Dùng khi dữ liệu có khoảng giá trị rất lớn.


Ví dụ:

```
1

10

100

1000

10000
```


Trong RoomBeacon:

Giá thuê có thể:

```
1 triệu

5 triệu

50 triệu

500 triệu
```


Log scale giúp nhìn rõ nhóm dữ liệu nhỏ.


---

# 8. Grid


```python
g.ax.xaxis.grid(
    True,
    "minor",
    linewidth=.25
)
```


Thêm grid nhỏ để đọc biểu đồ chính xác hơn.


---

# 9. Remove border


```python
g.despine(
    left=True,
    bottom=True
)
```


Xóa đường viền:

- bên trái
- phía dưới


Giúp biểu đồ sạch hơn.


---

# 10. Áp dụng cho RoomBeacon


## Phân tích quan hệ diện tích và giá thuê


```python
plot_df = (

    df_work

    .explode(
        "current_location"
    )

    .dropna(
        subset=[
            "area_m2",
            "monthly_price",
            "current_location"
        ]
    )

)


g = sns.relplot(

    data=plot_df,

    x="area_m2",

    y="monthly_price",

    hue="current_location",

    size="monthly_price",

    sizes=(20,200),

    alpha=0.5

)


g.set(

    xlabel="Diện tích (m²)",

    ylabel="Giá thuê (VNĐ/tháng)"

)


plt.show()
```


Biểu đồ giúp phát hiện:

- Phòng nhỏ nhưng giá quá cao.
- Phòng lớn nhưng giá thấp.
- Khu vực có mặt bằng giá khác nhau.


---

# 11. Các biểu đồ Seaborn khác

## 11.1 Distribution Plot

Mục đích:

- xem phân phối dữ liệu
- phát hiện lệch
- phát hiện outlier


```python

# TODO

```



---

## 11.2 Box Plot

Mục đích:

- phát hiện outlier
- so sánh nhóm


```python

# TODO

```



---

## 11.3 Bar Plot

Mục đích:

- so sánh giá trị giữa các nhóm


```python

# TODO

```



---

## 11.4 Heatmap

Mục đích:

- correlation
- ma trận dữ liệu


```python

# TODO

```



---

## 11.5 Pair Plot

Mục đích:

- xem quan hệ nhiều biến


```python

# TODO

```



---

# 12. RoomBeacon Visualization Roadmap


## EDA Phase

```
Raw Data

    |

    ↓

Seaborn

    |

    ├── Distribution Plot
    |
    ├── Boxplot
    |
    ├── Scatter Plot
    |
    ├── Heatmap
    |
    └── Bar Plot


```


## Dashboard Phase

```
Clean Dataset

        |

        ↓

Plotly / Streamlit

```
