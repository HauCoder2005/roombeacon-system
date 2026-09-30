import json

def engineer_notebook():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    # Check if section 7 already exists to avoid duplicates
    has_target_section = any("## 7. Lựa chọn Target Variable" in "".join(c.get('source', [])) for c in nb['cells'])
    
    if not has_target_section:
        def add_md(text):
            nb['cells'].append({"cell_type": "markdown", "metadata": {}, "source": [line + '\n' for line in text.split('\n')]})

        def add_code(text):
            nb['cells'].append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + '\n' for line in text.split('\n')]})

        add_md("## 7. Data Engineering: Định nghĩa Target Variable & Phân tích Đa biến\nTrong bài toán Học máy (Machine Learning) sắp tới, mục tiêu của chúng ta là xây dựng mô hình dự đoán giá thuê nhà. Do đó:\n- **Biến mục tiêu (Target Variable):** `price_million` (Giá thuê tính bằng triệu VNĐ).\n- **Đặc trưng (Features):** `area_m2` (Diện tích), `current_location` (Khu vực), `domain` (Nguồn đăng).\n\nDưới đây là các bước phân tích sự tương quan giữa Features và Target.")

        add_code("""# 1. Tương quan giữa Diện tích (Feature) và Giá thuê (Target)
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df_final, x="area_m2", y="price_million", alpha=0.5, hue="domain", palette="Set1")
plt.title("Mối quan hệ giữa Diện tích và Giá thuê (Phân loại theo Nguồn)", fontsize=14, fontweight="bold")
plt.xlabel("Diện tích (m²)")
plt.ylabel("Giá thuê (Triệu VNĐ) - TARGET")
plt.legend(title="Nguồn cào (Domain)")
plt.show()""")

        add_code("""# 2. Ma trận Tương quan (Correlation Heatmap) cho các biến số học
numeric_df = df_final[["price_million", "area_m2", "price_per_m2"]].corr()

plt.figure(figsize=(6, 5))
sns.heatmap(numeric_df, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
plt.title("Ma trận Tương quan (Correlation Matrix)", fontsize=14, fontweight="bold")
plt.show()""")

        add_code("""# 3. Phân tích Feature Category: Phân khúc diện tích trung bình theo Quận/Huyện
plt.figure(figsize=(14, 6))
area_by_loc = df_final.groupby("current_location")["area_m2"].mean().sort_values(ascending=False).head(15)

sns.barplot(x=area_by_loc.index, y=area_by_loc.values, palette="mako")
plt.title("Trung bình Diện tích (m²) tại Top 15 Khu vực", fontsize=14, fontweight="bold")
plt.xticks(rotation=45, ha="right")
plt.ylabel("Diện tích trung bình (m²)")
plt.show()""")

        add_code("""# 4. Lưu dữ liệu sạch (Silver Data) chuẩn bị cho Machine Learning
# Data Engineer sẽ lưu Dataframe cuối cùng này thành định dạng Parquet để tối ưu dung lượng và tốc độ nạp.
# df_final.to_parquet("../data/silver/cleaned_rental_posts.parquet", index=False)
print(f"Sẵn sàng đưa {len(df_final)} bản ghi vào huấn luyện Model dự đoán Giá thuê!")""")

    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

engineer_notebook()
