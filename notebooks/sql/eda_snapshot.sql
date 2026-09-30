-- One latest-state read; evidence is restricted to contributing versions.
-- Match BOTH listing identity and observation time, then use the canonical ID
-- tie-break. Child rows use the same latest-ID rule as v_latest_posts.
WITH latest AS MATERIALIZED (
    SELECT * FROM v_latest_posts
), versions AS (
    SELECT l.rental_post_id, v.id AS observation_id,
           COUNT(*) OVER (PARTITION BY l.rental_post_id) AS version_time_matches,
           ROW_NUMBER() OVER (
               PARTITION BY l.rental_post_id ORDER BY v.id DESC
           ) AS version_rank
    FROM latest l
    JOIN mysql_db.rental_post_versions v
      ON v.rental_post_id = l.rental_post_id
     AND v.observed_at = l.latest_observed_at
), selected AS (
    SELECT * FROM versions WHERE version_rank = 1
), prices AS (
    SELECT p.id, p.rental_post_id, p.rental_post_version_id,
           p.price_raw, p.price_amount, p.currency, p.period, ROW_NUMBER() OVER (
        PARTITION BY p.rental_post_version_id ORDER BY p.id DESC
    ) AS child_rank
    FROM mysql_db.post_prices p
    JOIN selected v ON v.observation_id = p.rental_post_version_id
), areas AS (
    SELECT d.rental_post_version_id, d.rental_post_id, d.id,
           d.area_raw, d.area_value,
           ROW_NUMBER() OVER (
               PARTITION BY d.rental_post_version_id ORDER BY d.id DESC
           ) AS child_rank
    FROM mysql_db.post_details d
    JOIN selected v ON v.observation_id = d.rental_post_version_id
)
SELECT l.*, v.observation_id AS evidence_observation_id,
       v.version_time_matches AS evidence_version_time_matches,
       p.id AS evidence_price_id, p.price_raw, p.currency, p.period,
       d.id AS evidence_area_id, d.area_raw,
       (v.observation_id IS NOT NULL
        AND (p.id IS NULL OR p.rental_post_id = l.rental_post_id)
        AND p.price_amount IS NOT DISTINCT FROM l.price_amount
       ) AS price_lineage_aligned,
       (v.observation_id IS NOT NULL
        AND (d.id IS NULL OR d.rental_post_id = l.rental_post_id)
        AND d.area_value IS NOT DISTINCT FROM l.area_value
       ) AS area_lineage_aligned
FROM latest l
LEFT JOIN selected v ON v.rental_post_id = l.rental_post_id
LEFT JOIN prices p ON p.rental_post_version_id = v.observation_id AND p.child_rank = 1
LEFT JOIN areas d ON d.rental_post_version_id = v.observation_id AND d.child_rank = 1
ORDER BY l.rental_post_id
