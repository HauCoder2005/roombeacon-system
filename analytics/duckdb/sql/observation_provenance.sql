SELECT
    v.id AS observation_id,
    p.code AS source_code,
    post.id AS rental_post_id,
    post.platform_post_id AS source_listing_id,
    v.crawl_run_id AS run_id,
    v.observed_at,
    TRY_CAST(json_extract_string(v.source_payload, '$.crawled_at') AS TIMESTAMP) AS source_crawled_at,
    v.ingestion_origin,
    CASE 
        WHEN v.ingestion_origin = 'LIVE_CRAWLER' THEN 'FRESH_SOURCE_OBSERVATION'
        WHEN v.ingestion_origin = 'BRONZE_RECONCILER' THEN 'HISTORICAL_BRONZE_REPLAY'
        ELSE 'UNKNOWN_PROVENANCE'
    END AS provenance_class
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts post ON v.rental_post_id = post.id
JOIN mysql_db.platforms p ON post.platform_id = p.id
