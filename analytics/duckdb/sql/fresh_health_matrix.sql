SELECT 
    p.code AS source_code,
    COUNT(v.id) AS observations,
    COUNT(DISTINCT v.rental_post_id) AS distinct_posts,
    SUM(CASE WHEN json_extract_string(v.source_payload, '$.price_raw') IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(v.id), 0) AS price_coverage_pct,
    SUM(CASE WHEN json_extract_string(v.source_payload, '$.area_raw') IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(v.id), 0) AS area_coverage_pct,
    SUM(CASE WHEN json_extract_string(v.source_payload, '$.location_raw') IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(v.id), 0) AS location_coverage_pct,
    SUM(CASE WHEN json_extract_string(v.source_payload, '$.address_raw') IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(v.id), 0) AS address_coverage_pct,
    SUM(CASE WHEN 
        json_extract_string(v.source_payload, '$.price_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.area_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.location_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.address_raw') IS NULL 
    THEN 1 ELSE 0 END) AS all_four_missing,
    SUM(CASE WHEN 
        json_extract_string(v.source_payload, '$.price_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.area_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.location_raw') IS NULL AND
        json_extract_string(v.source_payload, '$.address_raw') IS NULL 
    THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(v.id), 0) AS all_four_missing_pct,
    MIN(TRY_CAST(json_extract_string(v.source_payload, '$.crawled_at') AS TIMESTAMP)) AS min_source_crawled_at,
    MAX(TRY_CAST(json_extract_string(v.source_payload, '$.crawled_at') AS TIMESTAMP)) AS max_source_crawled_at
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts post ON v.rental_post_id = post.id
JOIN mysql_db.platforms p ON post.platform_id = p.id
WHERE v.ingestion_origin = 'LIVE_CRAWLER'
GROUP BY p.code;
