import json

def update_notebook():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
        
    for cell in nb['cells']:
        source = "".join(cell.get('source', []))
        
        # 1. Update Missing Values cell
        if "# 3. Xóa các dòng thiếu Giá hoặc Diện tích" in source:
            new_source = """# 1. Đổi tên cột cho dễ thao tác
df_renamed = df_raw.rename(
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

# 2. Ép kiểu dữ liệu dạng số
df_renamed["monthly_price"] = pd.to_numeric(df_renamed["monthly_price"], errors="coerce")
df_renamed["area_m2"] = pd.to_numeric(df_renamed["area_m2"], errors="coerce")

# ---------------- TRỰC QUAN HÓA DỮ LIỆU KHUYẾT (MISSING DATA) ----------------
from IPython.display import display

missing_data = df_renamed.isna().sum().reset_index()
missing_data.columns = ['Feature', 'Missing Count']
missing_data['Missing %'] = (missing_data['Missing Count'] / len(df_renamed)) * 100
missing_data = missing_data[missing_data['Missing Count'] > 0].sort_values('Missing %', ascending=False)

print("Bảng thống kê Dữ liệu khuyết (Missing Values):")
display(missing_data)

if not missing_data.empty:
    plt.figure(figsize=(10, 4))
    sns.barplot(data=missing_data, x='Missing %', y='Feature', palette='Reds_r')
    plt.title('Tỷ lệ phần trăm Dữ liệu khuyết (Missing Data Rate)', fontsize=14)
    plt.xlabel('Tỷ lệ khuyết (%)')
    plt.ylabel('Trường dữ liệu')
    plt.tight_layout()
    plt.show()
# -----------------------------------------------------------------------------

# 3. Xóa các dòng thiếu Giá hoặc Diện tích và gán vào DataFrame mới
df_cleaned = df_renamed.dropna(subset=["monthly_price", "area_m2"]).copy()

# 4. Tạo các đặc trưng (Feature Engineering)
df_cleaned["price_million"] = df_cleaned["monthly_price"] / 1_000_000
df_cleaned["price_per_m2"] = df_cleaned["price_million"] / df_cleaned["area_m2"]

print(f"\\nSố bản ghi hợp lệ sau khi làm sạch: {len(df_cleaned)}")
"""
            # Ensure lines don't end up with double newlines
            cell['source'] = [line + '\n' for line in new_source.split('\n')]
            if cell['source'][-1] == '\n':
                cell['source'] = cell['source'][:-1]

        # 2. Update Outlier distribution cell
        if "df_final = remove_outliers_iqr(" in source:
            new_source = """def remove_outliers_iqr(df, group_col, value_col):
    # Lọc các khu vực có >= 20 bài đăng để tính IQR chính xác
    counts = df[group_col].value_counts()
    valid_groups = counts[counts >= 20].index
    df_valid = df[df[group_col].isin(valid_groups)]
    
    def filter_group(group):
        q1 = group[value_col].quantile(0.25)
        q3 = group[value_col].quantile(0.75)
        iqr = q3 - q1
        return group[(group[value_col] >= q1 - 1.5 * iqr) & (group[value_col] <= q3 + 1.5 * iqr)]
    
    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)

# Loại bỏ giá trị dị biệt và lưu vào DataFrame mới (df_final)
df_final = remove_outliers_iqr(df_features, "current_location", "price_per_m2")
outliers_removed = len(df_features) - len(df_final)

print(f"Tổng số bài đăng TRƯỚC khi lọc Outlier: {len(df_features)}")
print(f"Tổng số bài đăng SAU khi lọc Outlier: {len(df_final)}")
print(f"-> Số lượng Outlier đã loại bỏ: {outliers_removed} ({outliers_removed/len(df_features)*100:.2f}%)\\n")

# ---------------- TRỰC QUAN HÓA PHÂN PHỐI OUTLIERS (HISTOGRAM/KDE) ----------------
fig, axes = plt.subplots(1, 2, figsize=(16, 5))

# Biểu đồ Trước khi lọc
sns.histplot(df_features["price_per_m2"], bins=100, kde=True, ax=axes[0], color="#d62728")
axes[0].set_title("Phân phối Đơn giá TRƯỚC khi lọc", fontsize=14, fontweight='bold', color='#d62728')
axes[0].set_xlabel("Đơn giá (Triệu/m²)")
axes[0].set_ylabel("Số lượng bài đăng")
axes[0].set_xlim(0, df_features["price_per_m2"].quantile(0.99)) # Hiển thị đến phân vị 99% để tránh bị ép trục X

# Biểu đồ Sau khi lọc
sns.histplot(df_final["price_per_m2"], bins=100, kde=True, ax=axes[1], color="#2ca02c")
axes[1].set_title("Phân phối Đơn giá SAU khi lọc IQR", fontsize=14, fontweight='bold', color='#2ca02c')
axes[1].set_xlabel("Đơn giá (Triệu/m²)")
axes[1].set_ylabel("Số lượng bài đăng")

plt.tight_layout()
plt.show()
# ----------------------------------------------------------------------------------
"""
            cell['source'] = [line + '\n' for line in new_source.split('\n')]
            if cell['source'][-1] == '\n':
                cell['source'] = cell['source'][:-1]

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

update_notebook()
