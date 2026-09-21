import duckdb
conn = duckdb.connect("data/duckdb/roombeacon_analytics.duckdb", read_only=True)
df = conn.execute("""
SELECT
    COUNT(*) as total,
    COUNT_IF(full_address_text IS NULL) as missing_full,
    COUNT_IF(location_raw IS NULL) as missing_loc,
    COUNT_IF(best_address_text IS NULL) as missing_best
FROM v_latest_posts
""").df()
print(df)
