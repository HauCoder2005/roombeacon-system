SELECT
    p.code AS source_code,
    COUNT(v.id) AS unknown_versions
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts post ON v.rental_post_id = post.id
JOIN mysql_db.platforms p ON post.platform_id = p.id
WHERE v.ingestion_origin = 'UNKNOWN'
GROUP BY p.code
UNION ALL
SELECT
    'TOTAL' AS source_code,
    COUNT(id) AS unknown_versions
FROM mysql_db.rental_post_versions
WHERE ingestion_origin = 'UNKNOWN';
