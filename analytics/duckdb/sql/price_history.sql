-- 3. v_price_history: Lịch sử biến động giá sử dụng LAG(price_amount)
WITH price_events AS (
    SELECT
        pl.code AS source_code,
        p.id AS rental_post_id,
        p.platform_post_id AS source_listing_id,
        v.crawl_run_id AS run_id,
        v.observed_at,
        pr.price_amount,
        LAG(pr.price_amount) OVER (
            PARTITION BY p.id
            ORDER BY v.observed_at, v.id
        ) AS previous_price
    FROM mysql_db.rental_post_versions v
    JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
    JOIN mysql_db.platforms pl ON p.platform_id = pl.id
    JOIN mysql_db.post_prices pr ON pr.rental_post_version_id = v.id
)
SELECT
    source_code,
    rental_post_id,
    source_listing_id,
    run_id,
    observed_at,
    price_amount,
    previous_price,
    (price_amount - previous_price) AS price_change,
    CASE
        WHEN previous_price IS NOT NULL AND previous_price > 0
        THEN ROUND((price_amount - previous_price) * 100.0 / previous_price, 2)
        ELSE NULL
    END AS price_change_pct
FROM price_events
ORDER BY rental_post_id, observed_at;
