SELECT
    p.code AS source_code,
    COUNT(v.id) AS replayed_versions,
    COUNT(DISTINCT v.rental_post_id) AS distinct_posts,
    MIN(TRY_CAST(json_extract_string(v.source_payload, '$.crawled_at') AS TIMESTAMP)) AS source_crawled_at_min,
    MAX(TRY_CAST(json_extract_string(v.source_payload, '$.crawled_at') AS TIMESTAMP)) AS source_crawled_at_max,
    MIN(v.observed_at) AS observed_at_min,
    MAX(v.observed_at) AS observed_at_max
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts post ON v.rental_post_id = post.id
JOIN mysql_db.platforms p ON post.platform_id = p.id
WHERE v.ingestion_origin = 'BRONZE_RECONCILER'
GROUP BY p.code;
