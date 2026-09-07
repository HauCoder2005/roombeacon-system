-- Latest-state dataset used only by the RoomBeacon EDA notebooks.
--
-- v_latest_posts is the authoritative DuckDB analytical view: it already
-- resolves one latest row per rental_post_id. This query deliberately does
-- not rebuild the Bronze joins, and it does not request coordinate fields.
--
-- The aliases below keep the notebook's analytical field names stable while
-- preserving values directly from the canonical DuckDB columns.

SELECT
    source_code AS source,
    rental_post_id,
    source_listing_id AS listing_id,
    title_raw,
    url,
    price_amount AS price,
    area_value AS area,
    area_inherited,
    full_address_text AS address,
    full_address_inherited,
    observed_at,
    first_observed_at,
    last_observed_at,
    active_days
FROM v_latest_posts
ORDER BY last_observed_at DESC;
