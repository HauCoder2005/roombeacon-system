# Chuyển đổi dữ liệu từ DuckDB sang Pandas DataFrame

Khi truy vấn dữ liệu từ DuckDB:

```python
df = conn.sql("""
    SELECT *
    FROM v_latest_posts
""")
```
Kết quả trả về là một đối tượng DuckDB Relation, chưa phải là Pandas DataFrame.

Để thực hiện các bước phân tích dữ liệu bằng Pandas như:

Kiểm tra missing values.
Thống kê mô tả.
Xử lý dữ liệu.
Trực quan hóa.

Cần chuyển đổi kết quả truy vấn sang DataFrame bằng phương thức .df():


```python
df = conn.sql("""
    SELECT *
    FROM v_latest_posts
""").df()
```
Luồng xử lý:

```
DuckDB Query
      |
      ↓
DuckDB Relation
      |
      ↓
     .df()
      |
      ↓
Pandas DataFrame
      |
      ↓
EDA Analysis
```

Trong RoomBeacon:

DuckDB chịu trách nhiệm truy vấn và xử lý dữ liệu ở tầng Analytics.
Pandas được sử dụng cho các bước khám phá và phân tích dữ liệu trong notebook.

Với dataset hiện tại (~19.000 records), việc chuyển toàn bộ dữ liệu sang Pandas DataFrame để thực hiện EDA là phù hợp.