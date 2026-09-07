import json

def build_granular_notebook():
    cells = []
    
    def add_md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": [line + '\n' for line in text.split('\n')]})

    def add_code(text):
        cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + '\n' for line in text.split('\n')]})

    # TITLE & TOC
    add_md("""# 🔬 Khám phá Dữ liệu Chuyên sâu (EDA) - Trích xuất Đặc trưng (Feature Engineering)

**Tóm tắt (Abstract):**
Tài liệu này trình bày quy trình Khám phá Dữ liệu (Exploratory Data Analysis - EDA) từng bước một. Tập trung vào việc xử lý các giá trị khuyết (Missing Data), loại bỏ nhiễu (Outliers) bằng phương pháp thống kê, và phân tích mối quan hệ đa biến (Multivariate Analysis).

**Biến mục tiêu (Target Variable):** `price_million` (Giá thuê quy đổi ra Triệu VNĐ).""")

    # 1. SETUP
    add_md("## 1. Khởi tạo Môi trường")
    add_md("Nhập các thư viện và thiết lập đường dẫn dự án.")
    
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

from IPython.display import display
from analytics.duckdb.connection import create_analytics_connection
from utils.address_cleaner import clean_address
from utils.location_normalizer import normalize_location""")

    add_md("Cấu hình phong cách biểu đồ chuẩn khoa học cho toàn bộ Notebook.")
    add_code("""plt.style.use('ggplot')
sns.set_theme(style="whitegrid", rc={"axes.facecolor": "#F9F9F9"})
plt.rcParams['figure.figsize'] = (10, 5)
plt.rcParams['font.size'] = 11""")

    add_md("## 2. Thu thập Dữ liệu (Data Acquisition)")
    add_md("Kết nối DuckDB và lấy dữ liệu tin đăng độc nhất (`v_latest_posts`).")
    add_code("""conn = create_analytics_connection()
df_raw = conn.sql("SELECT * FROM v_latest_posts").df()""")

    add_md("Kiểm tra kích thước và xem qua vài dòng dữ liệu thô đầu tiên.")
    add_code("""print(f"Kích thước tập dữ liệu gốc: {df_raw.shape[0]} quan sát x {df_raw.shape[1]} thuộc tính")
display(df_raw.head(3))""")


    # 3. MISSING DATA
    add_md("## 3. Đánh giá Dữ liệu Khuyết (Missing Data)")
    add_md("Tính toán số lượng và tỷ lệ % khuyết cho mỗi trường.")
    
    add_code("""missing_df = df_raw.isnull().sum().reset_index()
missing_df.columns = ['Feature', 'Missing Count']
missing_df['Missing Rate (%)'] = (missing_df['Missing Count'] / len(df_raw)) * 100
missing_df = missing_df.sort_values('Missing Rate (%)', ascending=False)""")

    add_md("Hiển thị bảng thống kê các trường bị khuyết.")
    add_code("""display(missing_df[missing_df['Missing Count'] > 0])""")

    add_md("### Trực quan hóa Dữ liệu Khuyết")
    add_md("Biểu đồ thanh ngang (Bar Chart) biểu diễn Tỷ lệ khuyết phần trăm.")
    add_code("""plt.figure(figsize=(10, 4))
sns.barplot(data=missing_df[missing_df['Missing Count'] > 0], x='Missing Rate (%)', y='Feature', palette='Reds_r')
plt.title('Tỷ lệ Dữ liệu Khuyết (Missing Rate)', fontweight='bold')
plt.xlabel('Tỷ lệ (%)')
plt.xlim(0, 100)
plt.show()""")

    add_md("Bản đồ nhiệt (Heatmap) giúp nhận diện quy luật khuyết (Missing Pattern).")
    add_code("""plt.figure(figsize=(12, 5))
sns.heatmap(df_raw.isnull(), cbar=False, cmap='viridis', yticklabels=False)
plt.title('Bản đồ phân phối Dữ liệu Khuyết (Missing Pattern)', fontweight='bold')
plt.show()""")

    # 4. CLEANING & FE
    add_md("## 4. Tiền xử lý & Trích xuất Đặc trưng (Data Cleaning & Feature Engineering)")
    add_md("Đổi tên cột cho chuẩn mực và dễ thao tác.")
    add_code("""df_cleaned = df_raw.rename(
    columns={
        "source": "domain", "rental_post_id": "roombeacon_id", "listing_id": "website_id",
        "title_raw": "title", "url": "post_url", "price": "monthly_price", "area": "area_m2"
    }
).copy()""")

    add_md("Ép kiểu dữ liệu Numeric để phát hiện các lỗi định dạng chuỗi.")
    add_code("""df_cleaned["monthly_price"] = pd.to_numeric(df_cleaned["monthly_price"], errors="coerce")
df_cleaned["area_m2"] = pd.to_numeric(df_cleaned["area_m2"], errors="coerce")""")

    add_md("Loại bỏ hoàn toàn (Listwise Deletion) các dòng thiếu Giá, Diện tích hoặc Địa chỉ.")
    add_code("""df_cleaned = df_cleaned.dropna(subset=["monthly_price", "area_m2", "address"]).copy()
print(f"Tổng số mẫu hợp lệ sau khi làm sạch: {len(df_cleaned)}")""")

    add_md("Trích xuất thêm các đặc trưng quan trọng: Giá (Triệu), Đơn giá (Triệu/m²) và Vị trí.")
    add_code("""# Chuẩn hóa giá
df_cleaned["price_million"] = df_cleaned["monthly_price"] / 1_000_000
df_cleaned["price_per_m2"] = df_cleaned["price_million"] / df_cleaned["area_m2"]

# Xử lý địa chỉ
df_cleaned["address_clean"] = df_cleaned["address"].apply(clean_address)
df_cleaned["current_location"] = df_cleaned["address_clean"].apply(normalize_location)

# Làm phẳng list location
df_cleaned = df_cleaned.explode("current_location").dropna(subset=["current_location"]).copy()""")


    # 5. OUTLIER DETECTION
    add_md("## 5. Xử lý Giá trị Dị biệt (Outlier Detection)")
    add_md("Khai báo hàm phát hiện Outlier sử dụng thuật toán Interquartile Range (IQR).")
    add_code("""def remove_outliers_iqr(df, group_col, value_col):
    counts = df[group_col].value_counts()
    valid_groups = counts[counts >= 20].index
    df_valid = df[df[group_col].isin(valid_groups)]
    
    def filter_group(group):
        q1 = group[value_col].quantile(0.25)
        q3 = group[value_col].quantile(0.75)
        iqr = q3 - q1
        return group[(group[value_col] >= q1 - 1.5 * iqr) & (group[value_col] <= q3 + 1.5 * iqr)]
    
    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)""")

    add_md("Thực thi hàm IQR trên biến `price_per_m2` để loại bỏ nhiễu.")
    add_code("""df_final = remove_outliers_iqr(df_cleaned, "current_location", "price_per_m2")
outliers_removed = len(df_cleaned) - len(df_final)

print(f"- Số lượng ban đầu: {len(df_cleaned)}")
print(f"- Số lượng sau lọc: {len(df_final)}")
print(f"- Lượng nhiễu (Outliers) bị loại: {outliers_removed} ({outliers_removed/len(df_cleaned)*100:.2f}%)")""")

    add_md("### Trực quan hóa So sánh Outlier (Trước và Sau)")
    add_md("Đối chiếu sự thay đổi phân phối của **Giá thuê** trước và sau khi lọc nhiễu.")
    add_code("""fig, axes = plt.subplots(1, 2, figsize=(16, 5))

# Giá thuê TRƯỚC
sns.histplot(df_cleaned["price_million"], bins=100, ax=axes[0], color="#e74c3c", kde=True)
axes[0].set_title("Phân phối Giá (TRƯỚC khi lọc)", fontweight='bold')
axes[0].set_xlim(0, df_cleaned["price_million"].quantile(0.99))

# Giá thuê SAU
sns.histplot(df_final["price_million"], bins=100, ax=axes[1], color="#27ae60", kde=True)
axes[1].set_title("Phân phối Giá (SAU khi lọc IQR)", fontweight='bold')
plt.show()""")

    add_md("Đối chiếu sự thay đổi phân phối của **Diện tích** trước và sau khi lọc nhiễu.")
    add_code("""fig, axes = plt.subplots(1, 2, figsize=(16, 5))

# Diện tích TRƯỚC
sns.histplot(df_cleaned["area_m2"], bins=100, ax=axes[0], color="#e74c3c", kde=True)
axes[0].set_title("Phân phối Diện tích (TRƯỚC khi lọc)", fontweight='bold')
axes[0].set_xlim(0, df_cleaned["area_m2"].quantile(0.99))

# Diện tích SAU
sns.histplot(df_final["area_m2"], bins=100, ax=axes[1], color="#27ae60", kde=True)
axes[1].set_title("Phân phối Diện tích (SAU khi lọc IQR)", fontweight='bold')
plt.show()""")


    # 6. MULTIVARIATE
    add_md("## 6. Phân tích Đa biến & Đánh giá Tương quan (Multivariate Analysis)")
    add_md("Ma trận Tương quan (Pearson Correlation Matrix) cho các biến số học.")
    add_code("""corr_matrix = df_final[["price_million", "area_m2", "price_per_m2"]].corr()

plt.figure(figsize=(7, 5))
sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=1, vmin=-1, vmax=1)
plt.title("Ma trận Tương quan (Pearson Correlation)", fontweight='bold')
plt.show()""")

    add_md("Biểu đồ Mật độ phân phối 2D Hexbin (Jointplot) giữa Diện tích và Giá.")
    add_code("""g = sns.jointplot(
    data=df_final, 
    x="area_m2", 
    y="price_million", 
    kind="hex", 
    color="#2980b9", 
    height=8, 
    ratio=4
)
g.fig.suptitle("Mật độ 2D: Diện tích vs Giá thuê", y=1.03, fontweight='bold')
g.set_axis_labels("Diện tích (m²)", "Giá thuê (Triệu VNĐ)")
plt.show()""")

    add_md("So sánh sự phân tán Giá thuê theo Website Nguồn (Violin Plot).")
    add_code("""plt.figure(figsize=(14, 6))
sns.violinplot(data=df_final, x="domain", y="price_million", palette="Set2", inner="quartile")
plt.title("Phân bố Giá thuê theo Website Nguồn", fontweight='bold')
plt.xlabel("Nguồn Website")
plt.ylabel("Giá thuê (Triệu VNĐ)")
plt.show()""")

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump({'cells': cells, 'metadata': {}, 'nbformat': 4, 'nbformat_minor': 5}, f, indent=1, ensure_ascii=False)

build_granular_notebook()
