import json

def rewrite_notebook():
    with open('notebooks/roombeacon_eda.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    # We will build a completely new list of cells
    cells = []
    
    def add_md(text):
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + '\n' for line in text.split('\n')[:-1]] + [text.split('\n')[-1]] if text else []
        })
        
    def add_code(text):
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [line + '\n' for line in text.split('\n')[:-1]] + [text.split('\n')[-1]] if text else []
        })

    add_md("# Phân tích Khám phá Dữ liệu (EDA) - Thị trường Cho thuê RoomBeacon\n\nNotebook này thực hiện các bước chuẩn hóa và phân tích dữ liệu bất động sản.")
    
    add_md("## 1. Khởi tạo & Tải Dữ liệu")
    add_code("import pandas as pd\nimport matplotlib.pyplot as plt\nimport seaborn as sns\nimport duckdb\nimport json\nimport re\n\nplt.style.use('ggplot')\nplt.rcParams['figure.figsize'] = (12, 6)")
    add_code("con = duckdb.connect('../data/duckdb/roombeacon_analytics.duckdb', read_only=True)\n\nquery = \"\"\"\nSELECT \n    source,\n    rental_post_id,\n    listing_id,\n    title_raw,\n    url,\n    price,\n    area,\n    address\nFROM v_latest_posts;\n\"\"\"\n\ndf = con.execute(query).df()\ncon.close()\ndf.head()")

    add_md("## 2. Tiền xử lý Dữ liệu (Data Preprocessing)")
    add_md("### 2.1. Đổi tên cột cho dễ hiểu")
    add_code("df_work = df.copy()\ndf_work = df_work.rename(\n    columns={\n        \"source\": \"domain\",\n        \"rental_post_id\": \"roombeacon_id\",\n        \"listing_id\": \"website_id\",\n        \"title_raw\": \"title\",\n        \"url\": \"post_url\",\n        \"price\": \"monthly_price\",\n        \"area\": \"area_m2\",\n    }\n)\ndf_work.head()")
    
    add_md("### 2.2. Làm sạch & Chuẩn hóa kiểu dữ liệu")
    add_code("# Ép kiểu giá và diện tích sang numeric, những giá trị không hợp lệ sẽ thành NaN\ndf_work['monthly_price'] = pd.to_numeric(df_work['monthly_price'], errors='coerce')\ndf_work['area_m2'] = pd.to_numeric(df_work['area_m2'], errors='coerce')\n\n# Đổi giá sang đơn vị Triệu VNĐ\ndf_work['price_million'] = df_work['monthly_price'] / 1_000_000\n\n# Xóa các dòng thiếu Giá hoặc Diện tích\ndf_work = df_work.dropna(subset=['monthly_price', 'area_m2'])\n\n# Tạo cột Đơn giá (Giá trên 1 mét vuông)\ndf_work['price_per_m2'] = df_work['price_million'] / df_work['area_m2']")

    add_md("### 2.3. Trích xuất Vị trí (Location Engineering)")
    add_code("def clean_address(addr):\n    if not isinstance(addr, str):\n        return \"\"\n    # Xóa khoảng trắng thừa và dấu chấm phẩy\n    return re.sub(r'\\s+', ' ', addr).replace(';', ',').strip()\n\ndf_work['address_clean'] = df_work['address'].apply(clean_address)\n\n# Bạn có thể bổ sung hàm normalize_location của bạn ở đây\ndef extract_district(addr):\n    match = re.search(r'(Quận \\d+|Quận [\\w\\s]+|Huyện [\\w\\s]+)', addr, re.IGNORECASE)\n    return match.group(1).strip() if match else \"Khác\"\n\ndf_work['district'] = df_work['address_clean'].apply(extract_district)\ndf_work[['address_clean', 'district']].head()")

    add_md("## 3. Xử lý Nhiễu (Outlier Removal)")
    add_md("Sử dụng phương pháp IQR trên **Đơn giá (price_per_m2)** thay vì Giá tổng để công bằng giữa các phòng diện tích khác nhau.")
    add_code("def remove_outliers_iqr(df, group_col, value_col):\n    # Chỉ giữ lại các nhóm có đủ số lượng mẫu (>= 30) để tính thống kê cho chính xác\n    counts = df[group_col].value_counts()\n    valid_groups = counts[counts >= 30].index\n    df_valid = df[df[group_col].isin(valid_groups)]\n    \n    def filter_group(group):\n        q1 = group[value_col].quantile(0.25)\n        q3 = group[value_col].quantile(0.75)\n        iqr = q3 - q1\n        lower = q1 - 1.5 * iqr\n        upper = q3 + 1.5 * iqr\n        return group[(group[value_col] >= lower) & (group[value_col] <= upper)]\n    \n    return df_valid.groupby(group_col, group_keys=False).apply(filter_group)\n\ndf_clean = remove_outliers_iqr(df_work, 'district', 'price_per_m2')\nprint(f\"Số lượng bài đăng trước khi lọc: {len(df_work)}\")\nprint(f\"Số lượng bài đăng sau khi lọc nhiễu: {len(df_clean)}\")")
    
    add_md("## 4. Trực quan hóa Dữ liệu (Data Visualization)")
    add_md("### 4.1. Phân bố Giá theo Quận/Huyện")
    add_code("plt.figure(figsize=(16, 8))\nsns.boxplot(data=df_clean, x='district', y='price_million')\nplt.xticks(rotation=45, ha='right')\nplt.title('Phân bố Giá thuê (Triệu VND) theo Quận/Huyện')\nplt.tight_layout()\nplt.show()")
    
    add_md("### 4.2. Phân bố Đơn giá (Triệu/m²) theo Quận/Huyện")
    add_code("plt.figure(figsize=(16, 8))\nsns.boxplot(data=df_clean, x='district', y='price_per_m2')\nplt.xticks(rotation=45, ha='right')\nplt.title('Phân bố Đơn giá (Triệu VND / m²) theo Quận/Huyện')\nplt.tight_layout()\nplt.show()")

    nb['cells'] = cells
    
    with open('notebooks/roombeacon_eda.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

rewrite_notebook()
