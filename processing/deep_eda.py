import json

def generate_deep_notebook():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    cells = []
    def add_md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": [line + '\n' for line in text.split('\n')]})

    def add_code(text):
        cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + '\n' for line in text.split('\n')]})

    # 1. Header
    add_md("# 🚀 Phân tích Khám phá Dữ liệu Chuyên sâu (Advanced EDA) - RoomBeacon\n\nQuy trình Data Engineering toàn diện: Từ Data thô (Bronze/Silver) -> Xử lý Khuyết (Missing) -> Lọc Nhiễu (Outliers) -> Phân tích Đa biến (Multivariate Relationships).")

    # 2. Imports
    add_md("## 1. Khởi tạo Môi trường & Nạp Dữ liệu\nSử dụng `create_analytics_connection` để kế thừa toàn bộ cấu trúc từ hệ thống.")
    add_code("""try:
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

plt.style.use('ggplot')
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
print("Đã nạp thư viện thành công.")""")

    add_code("""conn = create_analytics_connection()
df_raw = conn.sql("SELECT * FROM v_latest_posts").df()
print(f"Tổng số bài đăng gốc: {len(df_raw)}")
df_raw.head(3)""")

    # 3. Missing Data - BEFORE
    add_md("## 2. Kiểm tra Dữ liệu Khuyết (Missing Values) - TRƯỚC KHI LÀM SẠCH\nPhân tích chi tiết các trường bị trống `isnull()`, `isna()` bằng bảng biểu và Bản đồ nhiệt (Heatmap).")
    add_code("""# Thống kê số lượng và tỷ lệ % khuyết
missing_df = df_raw.isnull().sum().reset_index()
missing_df.columns = ['Trường dữ liệu', 'Số lượng Null']
missing_df['Tỷ lệ Khuyết (%)'] = (missing_df['Số lượng Null'] / len(df_raw)) * 100
missing_df = missing_df.sort_values('Tỷ lệ Khuyết (%)', ascending=False)

from IPython.display import display
print("BẢNG THỐNG KÊ DỮ LIỆU KHUYẾT (TRƯỚC XỬ LÝ):")
display(missing_df[missing_df['Số lượng Null'] > 0])

# Trực quan hóa Dữ liệu khuyết
fig, axes = plt.subplots(1, 2, figsize=(18, 6))

# 1. Bar chart tỷ lệ khuyết
sns.barplot(data=missing_df[missing_df['Số lượng Null'] > 0], x='Tỷ lệ Khuyết (%)', y='Trường dữ liệu', palette='Reds_r', ax=axes[0])
axes[0].set_title('Tỷ lệ % Dữ liệu Khuyết (Missing Rate)', fontsize=14, fontweight='bold')
axes[0].set_xlim(0, 100)

# 2. Heatmap vị trí dữ liệu khuyết (Trắng/Vàng = Missing, Tím/Đậm = Có dữ liệu)
sns.heatmap(df_raw.isnull(), cbar=False, cmap='viridis', yticklabels=False, ax=axes[1])
axes[1].set_title('Bản đồ Nhiệt Dữ liệu Khuyết (Missing Data Heatmap)', fontsize=14, fontweight='bold')

plt.tight_layout()
plt.show()""")

    # 4. Data Cleaning
    add_md("## 3. Tiền xử lý & Làm sạch (Data Cleaning)\nĐổi tên cột, ép kiểu dữ liệu và loại bỏ các dòng bị khuyết Giá, Diện tích hoặc Địa chỉ.")
    add_code("""# Copy data và đổi tên cột
df_cleaned = df_raw.rename(
    columns={
        "source": "domain",
        "rental_post_id": "roombeacon_id",
        "listing_id": "website_id",
        "title_raw": "title",
        "url": "post_url",
        "price": "monthly_price",
        "area": "area_m2"
    }
).copy()

# Ép kiểu dữ liệu Numeric (Giá trị không hợp lệ sẽ tự động thành NaN)
df_cleaned["monthly_price"] = pd.to_numeric(df_cleaned["monthly_price"], errors="coerce")
df_cleaned["area_m2"] = pd.to_numeric(df_cleaned["area_m2"], errors="coerce")

# DROP NA: Xóa các hàng bị thiếu các trường trọng yếu
df_cleaned = df_cleaned.dropna(subset=["monthly_price", "area_m2", "address"])

print(f"Số lượng bản ghi sau khi xóa Null: {len(df_cleaned)}")""")

    # 5. Missing Data - AFTER
    add_md("## 4. Kiểm tra Dữ liệu Khuyết (Missing Values) - SAU KHI LÀM SẠCH\nĐảm bảo bộ dữ liệu đã sạch bóng các giá trị Null ở các cột quan trọng.")
    add_code("""missing_after = df_cleaned[['monthly_price', 'area_m2', 'address']].isnull().mean() * 100

plt.figure(figsize=(8, 3))
sns.barplot(x=missing_after.values, y=missing_after.index, palette='Greens_r')
plt.title('Tỷ lệ Dữ liệu Khuyết SAU KHI LÀM SẠCH (Mục tiêu = 0%)', fontsize=14, fontweight='bold')
plt.xlabel('% Khuyết')
plt.xlim(0, 100)
plt.show()""")

    # 6. Feature Engineering & IQR
    add_md("## 5. Feature Engineering & Kiểm tra Outlier (Nhiễu)\nTạo các biến số mới (`price_per_m2`, `district`) và so sánh phân phối Dữ liệu TRƯỚC vs SAU khi lọc Outlier bằng thuật toán IQR.")
    add_code("""df_features = df_cleaned.copy()

# Tạo Feature: Giá (Triệu) và Đơn giá (Triệu/m2)
df_features["price_million"] = df_features["monthly_price"] / 1_000_000
df_features["price_per_m2"] = df_features["price_million"] / df_features["area_m2"]

# Trích xuất Vị trí
df_features["address_clean"] = df_features["address"].apply(clean_address)
df_features["current_location"] = df_features["address_clean"].apply(normalize_location)
df_features = df_features.explode("current_location").dropna(subset=["current_location"])

# Thuật toán lọc IQR
def remove_outliers_iqr(df, group_col, value_col):
    counts = df[group_col].value_counts()
    valid_groups = counts[counts >= 20].index
    df_valid = df[df[group_col].isin(valid_groups)]
    
    def filter_group(group):
        q1 = group[value_col].quantile(0.25)
        q3 = group[value_col].quantile(0.75)
        iqr = q3 - q1
        return group[(group[value_col] >= q1 - 1.5 * iqr) & (group[value_col] <= q3 + 1.5 * iqr)]
    
    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)

df_final = remove_outliers_iqr(df_features, "current_location", "price_per_m2")
print(f"Đã loại bỏ {len(df_features) - len(df_final)} bản ghi nhiễu (Outliers).")""")

    # 7. Outlier BEFORE vs AFTER Visualization
    add_md("### Trực quan hóa: Phân phối Diện tích & Giá thuê (TRƯỚC vs SAU khi lọc Outlier)\nDùng Histogram để thấy sự biến mất của các cái 'đuôi' dài (Long-tail anomalies).")
    add_code("""fig, axes = plt.subplots(2, 2, figsize=(18, 10))

# 1. Giá thuê - TRƯỚC
sns.histplot(df_features["price_million"], bins=100, ax=axes[0,0], color="#d62728", kde=True)
axes[0,0].set_title("Giá thuê TRƯỚC khi lọc (Nhiều tin giá ảo > 100tr)", fontweight='bold')
axes[0,0].set_xlim(0, df_features["price_million"].quantile(0.99))

# 2. Giá thuê - SAU
sns.histplot(df_final["price_million"], bins=100, ax=axes[0,1], color="#2ca02c", kde=True)
axes[0,1].set_title("Giá thuê SAU khi lọc (Chuẩn hình chuông)", fontweight='bold')

# 3. Diện tích - TRƯỚC
sns.histplot(df_features["area_m2"], bins=100, ax=axes[1,0], color="#d62728", kde=True)
axes[1,0].set_title("Diện tích TRƯỚC khi lọc", fontweight='bold')
axes[1,0].set_xlim(0, df_features["area_m2"].quantile(0.99))

# 4. Diện tích - SAU
sns.histplot(df_final["area_m2"], bins=100, ax=axes[1,1], color="#2ca02c", kde=True)
axes[1,1].set_title("Diện tích SAU khi lọc", fontweight='bold')

plt.tight_layout()
plt.show()""")

    # 8. Multivariate Relationships
    add_md("## 6. So sánh các trường với nhau (Multivariate Relationships)\nSử dụng các sơ đồ nâng cao (Pairplot, Jointplot, Violin) để tìm ra mối tương quan giữa Diện tích, Giá và Nguồn dữ liệu.")
    
    add_md("### 6.1. Ma trận Phân tán (Pairplot)\nNhìn tổng quan sự tương quan chéo giữa tất cả các biến số, phân loại bằng màu sắc theo Nguồn web (Domain).")
    add_code("""import warnings
warnings.filterwarnings('ignore') # Ẩn cảnh báo của Seaborn

sns.pairplot(
    df_final[["price_million", "area_m2", "price_per_m2", "domain"]], 
    hue="domain", 
    palette="husl",
    plot_kws={'alpha': 0.5, 's': 15},
    height=3
)
plt.suptitle("Ma trận Phân tán (Scatter Matrix) giữa các trường", y=1.02, fontsize=16, fontweight='bold')
plt.show()""")

    add_md("### 6.2. Phân phối Mật độ 2D (Jointplot: Giá vs Diện tích)\nHiển thị điểm tập trung đông đúc nhất (Màu càng đậm, số lượng phòng trọ ở phân khúc đó càng nhiều).")
    add_code("""g = sns.jointplot(
    data=df_final, 
    x="area_m2", 
    y="price_million", 
    kind="hex", 
    color="#4CB391", 
    height=7, 
    ratio=4
)
g.fig.suptitle("Mật độ tập trung: Diện tích vs Giá thuê", y=1.03, fontsize=14, fontweight='bold')
g.set_axis_labels("Diện tích (m²)", "Giá thuê (Triệu VNĐ)")
plt.show()""")

    add_md("### 6.3. Hình dạng Phân phối theo Nguồn (Violin Plot)\nBiểu đồ đàn vĩ cầm (Violin) cho thấy độ 'phình' của dữ liệu. Càng phình to, dữ liệu càng tập trung nhiều ở mức giá đó.")
    add_code("""plt.figure(figsize=(12, 6))
sns.violinplot(data=df_final, x="domain", y="price_million", palette="muted", inner="quartile")
plt.title("Phân bố Hình dạng (Violin) của Giá thuê theo Website", fontsize=16, fontweight='bold')
plt.xlabel("Nguồn Website")
plt.ylabel("Giá thuê (Triệu VNĐ)")
plt.show()""")

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump({'cells': cells, 'metadata': nb.get('metadata', {}), 'nbformat': nb.get('nbformat', 4), 'nbformat_minor': nb.get('nbformat_minor', 5)}, f, indent=1, ensure_ascii=False)

generate_deep_notebook()
