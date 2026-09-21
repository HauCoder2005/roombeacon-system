import duckdb
import pandas as pd

# Connect to DuckDB
conn = duckdb.connect("data/duckdb/roombeacon_analytics.duckdb", read_only=True)

df = conn.execute("""
    SELECT 
        source_code,
        COUNT(*) as total_posts,
        COUNT_IF(best_address_text IS NULL OR TRIM(best_address_text) = '') as missing_address,
        ROUND(100.0 * COUNT_IF(best_address_text IS NULL OR TRIM(best_address_text) = '') / COUNT(*), 2) as missing_pct
    FROM v_latest_posts
    GROUP BY source_code
    ORDER BY missing_address DESC
""").df()

print(df.to_string())
