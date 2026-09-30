import duckdb
conn = duckdb.connect("data/duckdb/roombeacon_analytics.duckdb")
df = conn.execute("""
SELECT
    COUNT(*) as total,
    COUNT_IF(full_address_text IS NULL OR TRIM(full_address_text) = '') as missing_full,
    COUNT_IF(location_raw IS NULL OR TRIM(location_raw) = '') as missing_location,
    COUNT_IF(best_address_text IS NULL OR TRIM(best_address_text) = '') as missing_best
FROM v_latest_posts
""").df()
print(df)
