import duckdb
import pandas as pd
conn = duckdb.connect("/tmp/temp.duckdb")
df = conn.execute("""
    SELECT 
        source_code,
        COUNT(*) as total_posts,
        COUNT_IF(best_address_text IS NULL OR TRIM(best_address_text) = '') as missing_address
    FROM v_latest_posts
    GROUP BY source_code
    ORDER BY missing_address DESC
""").df()
print(df.to_string())
