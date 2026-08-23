-- 5. v_source_activity: Thống kê hoạt động theo nguồn, run_id và ngày
SELECT
    pl.code AS platform,
    v.crawl_run_id AS run_id,
    CAST(v.observed_at AS DATE) AS date,
    COUNT(v.id) AS observations_count,
    COUNT(DISTINCT v.rental_post_id) AS distinct_posts_count
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
GROUP BY pl.code, v.crawl_run_id, CAST(v.observed_at AS DATE)
ORDER BY date DESC, pl.code, observations_count DESC;
