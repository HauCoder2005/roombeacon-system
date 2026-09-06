import json

def fix_notebook():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
        
    for idx, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            source = "".join(cell.get('source', []))
            
            # Fix rename logic
            if "df_work.rename(" in source:
                cell['source'] = [
                    "# Đổi tên các cột cho dễ thao tác (Cập nhật theo schema mới của v_latest_posts)\n",
                    "df_work = df_work.rename(\n",
                    "    columns={\n",
                    "        \"source\": \"domain\",\n",
                    "        \"rental_post_id\": \"roombeacon_id\",\n",
                    "        \"listing_id\": \"website_id\",\n",
                    "        \"title_raw\": \"title\",\n",
                    "        \"url\": \"post_url\",\n",
                    "        \"price\": \"monthly_price\",\n",
                    "        \"area\": \"area_m2\"\n",
                    "    }\n",
                    ")\n"
                ]
                
            # Add price_per_m2 calculation
            if "df_work[\"price_million\"] =" in source:
                cell['source'] = [
                    "# Quy đổi giá sang đơn vị Triệu VNĐ\n",
                    "df_work[\"price_million\"] = (\n",
                    "    pd.to_numeric(df_work[\"monthly_price\"], errors=\"coerce\")\n",
                    "    / 1_000_000\n",
                    ")\n\n",
                    "# Ép kiểu diện tích và tính Đơn giá (Triệu VNĐ / m2) để so sánh công bằng hơn\n",
                    "df_work[\"area_m2\"] = pd.to_numeric(df_work[\"area_m2\"], errors=\"coerce\")\n",
                    "df_work[\"price_per_m2\"] = df_work[\"price_million\"] / df_work[\"area_m2\"]\n"
                ]
                
            # Fix the plot to use price_per_m2 (optional but recommended for outliers)
            if "plot_df_price = (" in source:
                cell['source'] = [
                    "# Chuẩn bị dữ liệu để vẽ biểu đồ và tìm Outlier\n",
                    "plot_df_price = (\n",
                    "    df_work.loc[df_work[\"price_million\"].between(1, 100)] # Mở rộng biên độ xíu\n",
                    "    .explode(\"current_location\")\n",
                    "    .dropna(subset=[\"current_location\"])\n",
                    "    .copy()\n",
                    ")\n"
                ]
                
            if "outliers = get_outliers(" in source:
                cell['source'] = [
                    "# Tìm Outlier dựa trên Đơn giá (Price per m2) thay vì Tổng giá\n",
                    "outliers = get_outliers(\n",
                    "    plot_df_price,\n",
                    "    group_col=\"current_location\",\n",
                    "    value_col=\"price_per_m2\"\n",
                    ")\n"
                ]

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

fix_notebook()
