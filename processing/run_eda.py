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

query = """
SELECT 
    source as domain,
    price,
    area,
    address
FROM v_latest_posts;
"""
df = con.execute(query).df()
con.close()
print(f"Loaded {len(df)} rows.")

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

print(f"Data cleaned. Proceeding with {len(df)} rows for plotting.")

plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x='area_m2', y='price_million', alpha=0.3, color='#1f77b4', s=15)
plt.title('Mối liên hệ giữa Diện tích và Giá thuê', fontsize=14, pad=15)
plt.xlabel('Diện tích (m²)', fontsize=12)
plt.ylabel('Giá thuê (Triệu VNĐ)', fontsize=12)
plt.savefig(f"{PLOT_DIR}/price_vs_area.png", dpi=150, bbox_inches='tight')
plt.close()

plt.figure(figsize=(12, 6))
district_counts = df['district'].value_counts().head(15)
sns.barplot(x=district_counts.index, y=district_counts.values, palette='viridis')
plt.title('Top 15 Quận/Huyện có nhiều bài đăng nhất', fontsize=14, pad=15)
plt.xticks(rotation=45, ha='right')
plt.ylabel('Số lượng tin đăng')
plt.savefig(f"{PLOT_DIR}/top_districts.png", dpi=150, bbox_inches='tight')
plt.close()

top_districts = district_counts.index
df_top = df[df['district'].isin(top_districts)]
plt.figure(figsize=(14, 7))
sns.boxplot(data=df_top, x='district', y='price_per_m2', order=top_districts, palette='Set2')
plt.title('Phân bố Đơn giá (Triệu/m²) tại các Quận/Huyện phổ biến', fontsize=14, pad=15)
plt.xticks(rotation=45, ha='right')
plt.ylabel('Đơn giá (Triệu/m²)')
plt.ylim(0, 0.5)
plt.savefig(f"{PLOT_DIR}/price_m2_by_district.png", dpi=150, bbox_inches='tight')
plt.close()

plt.figure(figsize=(10, 6))
source_stats = df.groupby('domain').agg({'price_million': 'mean', 'domain': 'count'}).rename(columns={'domain': 'count'}).reset_index()
source_stats = source_stats.sort_values('count', ascending=False)
fig, ax1 = plt.subplots(figsize=(10, 6))
sns.barplot(data=source_stats, x='domain', y='count', ax=ax1, color='#4c72b0', alpha=0.7)
ax1.set_ylabel('Số lượng tin đăng', color='#4c72b0')
ax2 = ax1.twinx()
sns.lineplot(data=source_stats, x='domain', y='price_million', ax=ax2, color='#c44e52', marker='o', linewidth=2, markersize=8)
ax2.set_ylabel('Giá trung bình (Triệu VNĐ)', color='#c44e52')
plt.title('Tương quan giữa Nguồn cào (Domain) và Giá trung bình', fontsize=14, pad=15)
plt.savefig(f"{PLOT_DIR}/source_vs_price.png", dpi=150, bbox_inches='tight')
plt.close()

print("Plots generated successfully!")
