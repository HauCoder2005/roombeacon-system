-- 9. v_acquisition_efficiency: Thống kê hiệu suất thu thập, độ lặp quan sát và tăng trưởng tin độc nhất theo nguồn
SELECT
    pl.code AS platform,
    COUNT(DISTINCT p.id) AS total_unique_posts,
    COUNT(v.id) AS total_observations,
    ROUND(CAST(COUNT(v.id) AS DOUBLE) / NULLIF(COUNT(DISTINCT p.id), 0), 2) AS avg_observations_per_post,
    COUNT(DISTINCT v.content_hash) AS total_distinct_contents,
    MIN(v.observed_at) AS first_observed_at,
    MAX(v.observed_at) AS last_observed_at
FROM mysql_db.rental_posts p
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
LEFT JOIN mysql_db.rental_post_versions v ON v.rental_post_id = p.id
GROUP BY pl.code
ORDER BY total_observations DESC;
