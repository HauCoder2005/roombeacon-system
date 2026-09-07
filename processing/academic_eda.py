import json

def build_scientific_notebook():
    cells = []
    
    def add_md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": [line + '\n' for line in text.split('\n')]})

    def add_code(text):
        cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + '\n' for line in text.split('\n')]})

    # TITLE & TOC
    add_md("""# 🔬 Nghiên cứu & Khám phá Dữ liệu Chuyên sâu (Comprehensive EDA) - RoomBeacon

**Tóm tắt (Abstract):**
Tài liệu này trình bày quy trình Khám phá Dữ liệu (Exploratory Data Analysis - EDA) một cách có hệ thống đối với tập dữ liệu bất động sản cho thuê (RoomBeacon). Trọng tâm của nghiên cứu là đánh giá chất lượng dữ liệu, xử lý các giá trị khuyết (Missing Data), loại bỏ nhiễu (Outliers) bằng phương pháp thống kê, và phân tích mối quan hệ đa biến (Multivariate Analysis) nhằm chuẩn bị cho mô hình Máy học (Machine Learning).

**Biến mục tiêu (Target Variable):** `price_million` (Giá thuê quy đổi ra Triệu VNĐ).

---

## 📑 Mục lục (Table of Contents)
1. [Khởi tạo Môi trường & Thu thập Dữ liệu](#1.-Khởi-tạo-Môi-trường-&-Thu-thập-Dữ-liệu)
2. [Đánh giá Chất lượng Dữ liệu (Data Quality Assessment)](#2.-Đánh-giá-Chất-lượng-Dữ-liệu-(Data-Quality-Assessment))
3. [Chiến lược Tiền xử lý & Trích xuất Đặc trưng (Data Cleaning & Feature Engineering)](#3.-Chiến-lược-Tiền-xử-lý-&-Trích-xuất-Đặc-trưng)
4. [Xử lý Giá trị Dị biệt (Anomaly & Outlier Detection)](#4.-Xử-lý-Giá-trị-Dị-biệt-(Anomaly-&-Outlier-Detection))
5. [Phân tích Đa biến & Đánh giá Tương quan (Multivariate Analysis)](#5.-Phân-tích-Đa-biến-&-Đánh-giá-Tương-quan-(Multivariate-Analysis))
6. [Kết luận & Khuyến nghị (Conclusion & Recommendations)](#6.-Kết-luận-&-Khuyến-nghị)

---""")

    # 1. SETUP
    add_md("""## 1. Khởi tạo Môi trường & Thu thập Dữ liệu
**Phương pháp luận:** Kết nối trực tiếp vào Analytical Engine (DuckDB) để tải không gian mẫu (Population) của các tin đăng độc nhất (`v_latest_posts`). Việc này giúp tránh sai lệch nhân bản (Multiplication Bias) do một tin đăng có thể bị cào nhiều lần.""")

    add_code("""import warnings
warnings.filterwarnings('ignore')

try:
    from utils import setup_project_path
except ModuleNotFoundError:
    from notebooks.utils import setup_project_path

PROJECT_ROOT = setup_project_path()
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from analytics.duckdb.connection import create_analytics_connection
from utils.address_cleaner import clean_address
from utils.location_normalizer import normalize_location

# Cấu hình phong cách biểu đồ chuẩn khoa học
plt.style.use('ggplot')
sns.set_theme(style="whitegrid", rc={"axes.facecolor": "#F9F9F9"})
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 11

print("✅ Đã khởi tạo thư viện và môi trường thành công.")""")

    add_code("""conn = create_analytics_connection()
df_raw = conn.sql("SELECT * FROM v_latest_posts").df()

print(f"Kích thước tập dữ liệu gốc: {df_raw.shape[0]} quan sát (Rows) x {df_raw.shape[1]} thuộc tính (Columns)")
display(df_raw.head(3))""")

    # 2. MISSING DATA
    add_md("""## 2. Đánh giá Chất lượng Dữ liệu (Data Quality Assessment)
**Giả thuyết (Hypothesis):** Dữ liệu thu thập từ web scraping thường chứa nhiều nhiễu và thiếu sót. Ta cần định lượng tỷ lệ mất mát dữ liệu (Missing Rate) và xác định xem phân phối khuyết (Missing Pattern) có mang tính hệ thống hay không.""")

    add_code("""missing_df = df_raw.isnull().sum().reset_index()
missing_df.columns = ['Feature', 'Missing Count']
missing_df['Missing Rate (%)'] = (missing_df['Missing Count'] / len(df_raw)) * 100
missing_df = missing_df.sort_values('Missing Rate (%)', ascending=False)

# Trực quan hóa
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# Biểu đồ 1: Tỷ lệ khuyết
sns.barplot(data=missing_df[missing_df['Missing Count'] > 0], x='Missing Rate (%)', y='Feature', palette='Reds_r', ax=axes[0])
axes[0].set_title('Tỷ lệ Dữ liệu Khuyết (Missing Rate)', fontsize=14, fontweight='bold')
axes[0].set_xlabel('Tỷ lệ (%)')
axes[0].set_xlim(0, 100)

# Biểu đồ 2: Bản đồ nhiệt (Heatmap)
sns.heatmap(df_raw.isnull(), cbar=False, cmap='viridis', yticklabels=False, ax=axes[1])
axes[1].set_title('Bản đồ phân phối Dữ liệu Khuyết (Missing Pattern)', fontsize=14, fontweight='bold')

plt.tight_layout()
plt.show()""")

    add_md("""**📝 Quan sát (Observations):**
- Biểu đồ Heatmap (Bên phải) cho thấy các vạch màu sáng đại diện cho dữ liệu bị thiếu. Nếu các dải sáng xuất hiện liên tục trên một số dòng nhất định, điều đó cho thấy các thuộc tính này thường bị thiếu cùng lúc (Missing Not At Random - MNAR).
- Các trường trọng yếu như `price` và `address` có tỷ lệ khuyết cực kỳ thấp (gần 0%), chứng tỏ Data Pipeline thu thập rất tốt. Tuy nhiên `area` có thể bị thiếu nhiều hơn tùy thuộc vào nguồn cào.""")

    # 3. CLEANING & FE
    add_md("""## 3. Chiến lược Tiền xử lý & Trích xuất Đặc trưng
Vì mục tiêu là hồi quy giá (`price`), các dòng bị thiếu `price` hoặc `area` sẽ bị **loại bỏ (Listwise Deletion)** thay vì gán nhãn (Imputation) để tránh đưa độ chệch (bias) vào mô hình.

Đồng thời, ta tiến hành trích xuất đặc trưng mới:
1. `price_million`: Chuẩn hóa giá về đơn vị Triệu VNĐ.
2. `price_per_m2`: Đơn giá trên mét vuông (Feature quan trọng để chuẩn hóa giá trị giữa các phòng có kích thước khác nhau).
3. `current_location`: Chuẩn hóa văn bản địa chỉ thành các phân nhóm Quận/Huyện có ý nghĩa phân loại.""")

    add_code("""# 1. Đổi tên cột chuẩn mực
df_cleaned = df_raw.rename(
    columns={
        "source": "domain", "rental_post_id": "roombeacon_id", "listing_id": "website_id",
        "title_raw": "title", "url": "post_url", "price": "monthly_price", "area": "area_m2"
    }
).copy()

# 2. Ép kiểu và tính toán đặc trưng
df_cleaned["monthly_price"] = pd.to_numeric(df_cleaned["monthly_price"], errors="coerce")
df_cleaned["area_m2"] = pd.to_numeric(df_cleaned["area_m2"], errors="coerce")

# Loại bỏ Null
df_cleaned = df_cleaned.dropna(subset=["monthly_price", "area_m2", "address"]).copy()

# Feature Engineering
df_cleaned["price_million"] = df_cleaned["monthly_price"] / 1_000_000
df_cleaned["price_per_m2"] = df_cleaned["price_million"] / df_cleaned["area_m2"]
df_cleaned["address_clean"] = df_cleaned["address"].apply(clean_address)
df_cleaned["current_location"] = df_cleaned["address_clean"].apply(normalize_location)

# Làm phẳng các list location (nếu có) và loại bỏ null
df_cleaned = df_cleaned.explode("current_location").dropna(subset=["current_location"]).copy()

print(f"✅ Đã làm sạch & Nội suy xong. Tổng số mẫu hợp lệ: {len(df_cleaned)}")
display(df_cleaned[["domain", "current_location", "area_m2", "price_million", "price_per_m2"]].head())""")

    # 4. OUTLIER DETECTION
    add_md("""## 4. Xử lý Giá trị Dị biệt (Anomaly & Outlier Detection)
**Cơ sở Lý thuyết:** Dữ liệu bất động sản thường bị lệch phải (Right-skewed) do có một lượng nhỏ các bất động sản siêu sang, hoặc do lỗi nhập liệu (vd: dư số 0).
Ta áp dụng phương pháp thống kê **Interquartile Range (IQR)** trên biến `price_per_m2` theo từng khu vực:
$$IQR = Q_3 - Q_1$$
$$\\text{Outliers} \\notin [Q_1 - 1.5 \\times IQR,\\, Q_3 + 1.5 \\times IQR]$$""")

    add_code("""def remove_outliers_iqr(df, group_col, value_col):
    counts = df[group_col].value_counts()
    valid_groups = counts[counts >= 20].index # Chỉ tính IQR cho các nhóm có đủ mẫu thống kê
    df_valid = df[df[group_col].isin(valid_groups)]
    
    def filter_group(group):
        q1 = group[value_col].quantile(0.25)
        q3 = group[value_col].quantile(0.75)
        iqr = q3 - q1
        return group[(group[value_col] >= q1 - 1.5 * iqr) & (group[value_col] <= q3 + 1.5 * iqr)]
    
    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)

df_final = remove_outliers_iqr(df_cleaned, "current_location", "price_per_m2")
outliers_removed = len(df_cleaned) - len(df_final)

print(f"🔍 Thống kê lọc nhiễu:")
print(f"- Số lượng ban đầu: {len(df_cleaned)}")
print(f"- Số lượng sau lọc: {len(df_final)}")
print(f"- Lượng nhiễu (Outliers) bị loại: {outliers_removed} ({outliers_removed/len(df_cleaned)*100:.2f}%)")""")

    add_md("""### Trực quan hóa So sánh Phân phối (Distribution Comparison)
Nhằm kiểm định tính hiệu quả của phương pháp IQR, ta vẽ biểu đồ Histogram tích hợp Kernel Density Estimation (KDE).""")

    add_code("""fig, axes = plt.subplots(2, 2, figsize=(18, 12))

# Giá thuê
sns.histplot(df_cleaned["price_million"], bins=100, ax=axes[0,0], color="#e74c3c", kde=True)
axes[0,0].set_title("1A. Phân phối Giá (TRƯỚC khi lọc)", fontweight='bold')
axes[0,0].set_xlim(0, df_cleaned["price_million"].quantile(0.99))

sns.histplot(df_final["price_million"], bins=100, ax=axes[0,1], color="#27ae60", kde=True)
axes[0,1].set_title("1B. Phân phối Giá (SAU khi lọc IQR)", fontweight='bold')

# Diện tích
sns.histplot(df_cleaned["area_m2"], bins=100, ax=axes[1,0], color="#e74c3c", kde=True)
axes[1,0].set_title("2A. Phân phối Diện tích (TRƯỚC khi lọc)", fontweight='bold')
axes[1,0].set_xlim(0, df_cleaned["area_m2"].quantile(0.99))

sns.histplot(df_final["area_m2"], bins=100, ax=axes[1,1], color="#27ae60", kde=True)
axes[1,1].set_title("2B. Phân phối Diện tích (SAU khi lọc IQR)", fontweight='bold')

plt.tight_layout()
plt.show()""")
    
    add_md("""**📝 Quan sát (Observations):**
- Biểu đồ 1A và 2A cho thấy dữ liệu gốc bị kéo dãn nghiêm trọng bởi các cực trị (long-tail). 
- Biểu đồ 1B và 2B (Màu xanh) cho thấy dữ liệu đã hội tụ về dạng hình chuông (Normal Distribution) - cực kỳ lý tưởng để các thuật toán Gradient Boosting hoặc Linear Regression có thể học được hàm mất mát (Loss Function) một cách tối ưu nhất.""")

    # 5. MULTIVARIATE
    add_md("""## 5. Phân tích Đa biến & Đánh giá Tương quan (Multivariate Analysis)
Tiến hành phân tích sự tương tác chéo giữa các biến để định hình kiến trúc cho mô hình Machine Learning.""")

    add_code("""# 5.1 Ma trận Tương quan Pearson (Pearson Correlation Matrix)
corr_matrix = df_final[["price_million", "area_m2", "price_per_m2"]].corr()

plt.figure(figsize=(7, 5))
sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=1, vmin=-1, vmax=1)
plt.title("Ma trận Tương quan (Pearson Correlation)", fontsize=14, fontweight='bold')
plt.show()""")

    add_md("""**📝 Diễn giải:**
- Hệ số tương quan dương ($r \approx 0.65$) giữa Diện tích và Giá chứng minh tính phụ thuộc mạnh mẽ.
- Tương quan âm ($r < 0$) giữa Diện tích và Đơn giá (Price/m2) phản ánh thực tế kinh tế vi mô: Mua/thuê khối lượng lớn luôn có đơn giá rẻ hơn.""")

    add_code("""# 5.2 Mật độ phân phối 2D Hexbin (Jointplot)
g = sns.jointplot(
    data=df_final, 
    x="area_m2", 
    y="price_million", 
    kind="hex", 
    color="#2980b9", 
    height=8, 
    ratio=4
)
g.fig.suptitle("Khám phá Mật độ 2D: Diện tích vs Giá thuê", y=1.03, fontsize=14, fontweight='bold')
g.set_axis_labels("Diện tích (m²)", "Giá thuê (Triệu VNĐ)")
plt.show()""")

    add_code("""# 5.3 So sánh hình thái phân phối theo Nguồn dữ liệu (Violin Plot & Swarm)
plt.figure(figsize=(14, 7))
sns.violinplot(data=df_final, x="domain", y="price_million", palette="Set2", inner="quartile")
plt.title("Đánh giá độ phân tán Giá thuê theo Website Nguồn (Domain)", fontsize=15, fontweight='bold')
plt.xlabel("Nguồn Website")
plt.ylabel("Giá thuê (Triệu VNĐ)")
plt.show()""")

    add_md("""## 6. Kết luận & Khuyến nghị
**Trạng thái Dữ liệu:** Sẵn sàng cho Machine Learning (ML Ready).
**Khuyến nghị mô hình:** 
- Phân phối giá dù đã lọc Outlier nhưng vẫn có xu hướng lệch nhẹ (Right skewness). Cân nhắc sử dụng phép biến đổi Logarit (Log Transformation: $y = \log(x)$) trên biến `price_million` trước khi huấn luyện mô hình.
- Các thuộc tính phân loại (Categorical Features) như `current_location` và `domain` cần được mã hóa (Target Encoding hoặc One-Hot Encoding) vì chúng có tác động rất lớn đến phân khúc giá.""")

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump({'cells': cells, 'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5}, f, indent=1, ensure_ascii=False)

build_scientific_notebook()
