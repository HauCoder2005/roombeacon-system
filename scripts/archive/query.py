import duckdb
conn = duckdb.connect("data/duckdb/roombeacon_analytics.duckdb", read_only=True)
print("=== V LATEST POSTS ===")
print(conn.execute("SELECT source_code, COUNT(*) as total, COUNT_IF(best_address_text IS NULL OR TRIM(best_address_text) = '') as missing_address FROM v_latest_posts GROUP BY source_code ORDER BY missing_address DESC").df().to_string(index=False))
