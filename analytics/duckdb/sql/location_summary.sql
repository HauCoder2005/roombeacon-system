-- 7. v_location_summary: Thống kê tin đăng theo khu vực
SELECT
    pl.code AS platform,
    COALESCE(addr.full_address_text, 'Chưa xác định') AS location_raw,
    COUNT(DISTINCT p.id) AS total_listings,
    ROUND(AVG(dt.area_value), 2) AS avg_area_m2
FROM mysql_db.post_addresses addr
JOIN mysql_db.rental_posts p ON addr.rental_post_id = p.id
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
LEFT JOIN mysql_db.post_details dt ON dt.rental_post_version_id = addr.rental_post_version_id
GROUP BY pl.code, addr.full_address_text
ORDER BY total_listings DESC;
