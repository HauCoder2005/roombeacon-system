-- 4. v_content_changes: Phân loại biến động nội dung bằng content_hash và LAG()
WITH hash_history AS (
    SELECT
        pl.code AS source_code,
        p.id AS rental_post_id,
        p.platform_post_id AS source_listing_id,
        v.crawl_run_id AS run_id,
        v.observed_at,
        v.title_raw,
        v.content_hash,
        LAG(v.content_hash) OVER (
            PARTITION BY p.id
            ORDER BY v.observed_at, v.id
        ) AS prev_content_hash
    FROM mysql_db.rental_post_versions v
    JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
    JOIN mysql_db.platforms pl ON p.platform_id = pl.id
)
SELECT
    source_code,
    rental_post_id,
    source_listing_id,
    run_id,
    observed_at,
    title_raw,
    content_hash,
    prev_content_hash,
    CASE
        WHEN prev_content_hash IS NULL THEN 'FIRST_OBSERVATION'
        WHEN prev_content_hash = content_hash THEN 'UNCHANGED'
        ELSE 'CHANGED'
    END AS change_classification
FROM hash_history
ORDER BY rental_post_id, observed_at;
