import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import duckdb
import re
import os

PLOT_DIR = "/home/codeser/Data/projects/roombeacon/data/eda_plots"
os.makedirs(PLOT_DIR, exist_ok=True)

plt.style.use('ggplot')
sns.set_theme(style="whitegrid", rc={"axes.facecolor": "#F9F9F9"})

print("Connecting to DuckDB...")
con = duckdb.connect('/tmp/temp_analytics.duckdb', read_only=True)
con.execute("INSTALL mysql;")
con.execute("LOAD mysql;")
con.execute("ATTACH 'host=localhost port=3307 database=roombeacon_bronze user=root password=12345678' AS mysql_db (TYPE mysql, READ_ONLY);")

df = con.execute("SELECT source as domain, price, area, address FROM v_latest_posts;").df()
con.close()

df['price_million'] = pd.to_numeric(df['price'], errors='coerce') / 1_000_000
df['area_m2'] = pd.to_numeric(df['area'], errors='coerce')
df = df.dropna(subset=['price_million', 'area_m2'])

def extract_district(addr):
    if not isinstance(addr, str): return "Khác"
    match = re.search(r'(Quận \d+|Quận [\w\s]+|Huyện [\w\s]+|TP Thủ Đức)', addr, re.IGNORECASE)
    return match.group(1).strip() if match else "Khác"

df['district'] = df['address'].apply(extract_district)
df = df[(df['price_million'] > 0.5) & (df['price_million'] < 50)]
df = df[(df['area_m2'] >= 5) & (df['area_m2'] < 200)]
df['price_per_m2'] = df['price_million'] / df['area_m2']

# 1. Scatter Plot with Domain Hue
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x="area_m2", y="price_million", alpha=0.6, hue="domain", palette="Set1", s=20)
plt.title("Mối quan hệ giữa Diện tích và Giá thuê (Phân loại theo Nguồn)", fontsize=14, fontweight="bold")
plt.xlabel("Diện tích (m²)")
plt.ylabel("Giá thuê (Triệu VNĐ) - TARGET")
plt.legend(title="Nguồn cào (Domain)")
plt.savefig(f"{PLOT_DIR}/scatter_domain_price.png", dpi=150, bbox_inches='tight')
plt.close()

# 2. Correlation Heatmap
numeric_df = df[["price_million", "area_m2", "price_per_m2"]].corr()
plt.figure(figsize=(6, 5))
sns.heatmap(numeric_df, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
plt.title("Ma trận Tương quan (Correlation Matrix)", fontsize=14, fontweight="bold")
plt.savefig(f"{PLOT_DIR}/correlation_heatmap.png", dpi=150, bbox_inches='tight')
plt.close()

# 3. Area by District Bar Chart
plt.figure(figsize=(12, 6))
area_by_loc = df.groupby("district")["area_m2"].mean().sort_values(ascending=False).head(15)
sns.barplot(x=area_by_loc.index, y=area_by_loc.values, palette="mako")
plt.title("Trung bình Diện tích (m²) tại Top 15 Khu vực", fontsize=14, fontweight="bold")
plt.xticks(rotation=45, ha="right")
plt.ylabel("Diện tích trung bình (m²)")
plt.savefig(f"{PLOT_DIR}/area_by_district.png", dpi=150, bbox_inches='tight')
plt.close()

