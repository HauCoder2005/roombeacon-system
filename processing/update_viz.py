import json

def update_viz():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
        
    for cell in nb['cells']:
        source = "".join(cell.get('source', []))
        
        # Modify the header
        if "## 6. Trực quan hóa Dữ liệu (Visualizations)" in source:
            cell['source'] = [
                "## 6. Trực quan hóa Dữ liệu (Visualizations)\n",
                "Biểu đồ Boxplot so sánh phân bố Giá thuê giữa các khu vực **Trực quan hóa sự khác biệt Trước và Sau khi lọc Outlier**."
            ]

        # Modify the plotting cell
        if "plt.figure(figsize=(16, 8))" in source and "sns.boxplot(" in source:
            cell['source'] = [
                "# Chọn ra Top 15 khu vực có nhiều bài đăng nhất\n",
                "top_locations = df_final[\"current_location\"].value_counts().head(15).index\n\n",
                "# Lấy dữ liệu của top 15 khu vực từ CẢ HAI tập dữ liệu (Trước và Sau khi lọc Outlier)\n",
                "plot_df_before = df_features[df_features[\"current_location\"].isin(top_locations)]\n",
                "plot_df_after = df_final[df_final[\"current_location\"].isin(top_locations)]\n\n",
                "fig, axes = plt.subplots(2, 1, figsize=(16, 14))\n\n",
                "# Biểu đồ 1: TRƯỚC khi lọc nhiễu (df_features)\n",
                "sns.boxplot(\n",
                "    data=plot_df_before,\n",
                "    x=\"current_location\",\n",
                "    y=\"price_per_m2\",\n",
                "    order=top_locations,\n",
                "    ax=axes[0],\n",
                "    palette=\"pastel\"\n",
                ")\n",
                "axes[0].set_title(\"TRƯỚC KHI LỌC NHIỄU (Chứa nhiều giá trị dị biệt / Outliers)\", fontsize=16, fontweight='bold', color='#d62728')\n",
                "axes[0].tick_params(axis='x', rotation=45)\n",
                "axes[0].set_ylabel(\"Đơn giá (Triệu/m²)\", fontsize=12)\n",
                "axes[0].set_xlabel(\"\")\n\n",
                "# Biểu đồ 2: SAU khi lọc nhiễu (df_final)\n",
                "sns.boxplot(\n",
                "    data=plot_df_after,\n",
                "    x=\"current_location\",\n",
                "    y=\"price_per_m2\",\n",
                "    order=top_locations,\n",
                "    ax=axes[1],\n",
                "    palette=\"Set2\"\n",
                ")\n",
                "axes[1].set_title(\"SAU KHI LỌC NHIỄU BẰNG IQR (Dữ liệu sạch, phản ánh đúng thị trường)\", fontsize=16, fontweight='bold', color='#2ca02c')\n",
                "axes[1].tick_params(axis='x', rotation=45)\n",
                "axes[1].set_ylabel(\"Đơn giá (Triệu/m²)\", fontsize=12)\n",
                "axes[1].set_xlabel(\"Khu vực (Phường/Quận)\", fontsize=12)\n\n",
                "plt.tight_layout()\n",
                "plt.show()\n"
            ]

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

update_viz()
