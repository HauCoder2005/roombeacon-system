import json

def update_dataframe_names():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
        
    for cell in nb['cells']:
        source = "".join(cell.get('source', []))
        
        if "df = conn.sql" in source:
            cell['source'] = [
                "conn = create_analytics_connection()\n",
                "attached = {row[0] for row in conn.execute(\"SHOW DATABASES\").fetchall()}\n",
                "if \"mysql_db\" not in attached:\n",
                "    raise RuntimeError(\"Lỗi: Không tìm thấy mysql_db được gắn vào DuckDB!\")\n\n",
                "print(\"Đã kết nối DuckDB thành công!\")\n",
                "df_raw = conn.sql(\"SELECT * FROM v_latest_posts\").df()\n",
                "print(f\"Tổng số bài đăng tải về: {len(df_raw)}\")\n",
                "df_raw.head(3)\n"
            ]
            
        elif "# Đổi tên cột cho dễ thao tác" in source:
            cell['source'] = [
                "# 1. Đổi tên cột cho dễ thao tác\n",
                "df_renamed = df_raw.rename(\n",
                "    columns={\n",
                "        \"source\": \"domain\",\n",
                "        \"rental_post_id\": \"roombeacon_id\",\n",
                "        \"listing_id\": \"website_id\",\n",
                "        \"title_raw\": \"title\",\n",
                "        \"url\": \"post_url\",\n",
                "        \"price\": \"monthly_price\",\n",
                "        \"area\": \"area_m2\"\n",
                "    }\n",
                ").copy()\n\n",
                "# 2. Ép kiểu dữ liệu dạng số\n",
                "df_renamed[\"monthly_price\"] = pd.to_numeric(df_renamed[\"monthly_price\"], errors=\"coerce\")\n",
                "df_renamed[\"area_m2\"] = pd.to_numeric(df_renamed[\"area_m2\"], errors=\"coerce\")\n\n",
                "# Đếm NaN trước khi xóa\n",
                "print(\"Số lượng giá trị NaN trước khi xóa:\")\n",
                "print(df_renamed[[\"monthly_price\", \"area_m2\", \"address\"]].isna().sum())\n\n",
                "# 3. Xóa các dòng thiếu Giá hoặc Diện tích và gán vào DataFrame mới\n",
                "df_cleaned = df_renamed.dropna(subset=[\"monthly_price\", \"area_m2\"]).copy()\n\n",
                "# 4. Tạo các đặc trưng (Feature Engineering)\n",
                "df_cleaned[\"price_million\"] = df_cleaned[\"monthly_price\"] / 1_000_000\n",
                "df_cleaned[\"price_per_m2\"] = df_cleaned[\"price_million\"] / df_cleaned[\"area_m2\"]\n\n",
                "print(f\"\\nSố bản ghi hợp lệ sau khi làm sạch: {len(df_cleaned)}\")\n"
            ]
            
        elif "# 1. Chạy hàm clean_address" in source:
            cell['source'] = [
                "# Tạo DataFrame mới cho bước kỹ thuật đặc trưng (Feature Engineering)\n",
                "df_features = df_cleaned.copy()\n\n",
                "# 1. Chạy hàm clean_address\n",
                "df_features[\"address_clean\"] = df_features[\"address\"].apply(clean_address)\n\n",
                "# 2. Map thành location chuẩn (Mảng gồm các Phường/Quận)\n",
                "df_features[\"current_location\"] = df_features[\"address_clean\"].apply(normalize_location)\n\n",
                "# NOTE: Normalize_location có thể trả về mảng (list). Explode để làm phẳng nếu 1 bài thuộc nhiều Phường\n",
                "df_features = df_features.explode(\"current_location\")\n\n",
                "# 3. Lọc bỏ các bài đăng không xác định được vị trí\n",
                "df_features = df_features.dropna(subset=[\"current_location\"]).copy()\n",
                "print(f\"Số bản ghi có vị trí hợp lệ: {len(df_features)}\")\n",
                "df_features[[\"address_clean\", \"current_location\", \"price_per_m2\"]].head(5)\n"
            ]
            
        elif "def remove_outliers_iqr" in source:
            cell['source'] = [
                "def remove_outliers_iqr(df, group_col, value_col):\n",
                "    # Lọc các khu vực có >= 20 bài đăng để tính IQR chính xác\n",
                "    counts = df[group_col].value_counts()\n",
                "    valid_groups = counts[counts >= 20].index\n",
                "    df_valid = df[df[group_col].isin(valid_groups)]\n",
                "    \n",
                "    def filter_group(group):\n",
                "        q1 = group[value_col].quantile(0.25)\n",
                "        q3 = group[value_col].quantile(0.75)\n",
                "        iqr = q3 - q1\n",
                "        return group[(group[value_col] >= q1 - 1.5 * iqr) & (group[value_col] <= q3 + 1.5 * iqr)]\n",
                "    \n",
                "    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)\n\n",
                "# Loại bỏ giá trị dị biệt và lưu vào DataFrame mới (df_final)\n",
                "df_final = remove_outliers_iqr(df_features, \"current_location\", \"price_per_m2\")\n",
                "print(f\"Số bài đăng sau khi lọc Outlier: {len(df_final)}\")\n"
            ]
            
        elif "# Chọn ra Top 15 khu vực có nhiều bài đăng nhất" in source:
            cell['source'] = [
                "# Chọn ra Top 15 khu vực có nhiều bài đăng nhất\n",
                "top_locations = df_final[\"current_location\"].value_counts().head(15).index\n",
                "plot_df = df_final[df_final[\"current_location\"].isin(top_locations)]\n\n",
                "plt.figure(figsize=(16, 8))\n",
                "sns.boxplot(\n",
                "    data=plot_df,\n",
                "    x=\"current_location\",\n",
                "    y=\"price_per_m2\",\n",
                "    order=top_locations\n",
                ")\n",
                "plt.title(\"Phân bố Đơn giá (Triệu VNĐ/m²) tại Top 15 Khu vực\", fontsize=16)\n",
                "plt.xticks(rotation=45, ha=\"right\", fontsize=12)\n",
                "plt.ylabel(\"Đơn giá (Triệu/m²)\", fontsize=12)\n",
                "plt.xlabel(\"Khu vực (Phường/Quận)\", fontsize=12)\n",
                "plt.tight_layout()\n",
                "plt.show()\n"
            ]

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

update_dataframe_names()
