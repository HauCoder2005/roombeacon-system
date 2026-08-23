-- 6. v_listing_lifetime: Thống kê vòng đời tin đăng theo sàn
SELECT
    pl.code AS platform,
    COUNT(p.id) AS total_posts,
    ROUND(AVG(date_diff('day', p.first_observed_at, p.last_observed_at)), 2) AS avg_active_days,
    MAX(date_diff('day', p.first_observed_at, p.last_observed_at)) AS max_active_days,
    MIN(p.first_observed_at) AS earliest_observation,
    MAX(p.last_observed_at) AS latest_observation
FROM mysql_db.rental_posts p
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
GROUP BY pl.code;
