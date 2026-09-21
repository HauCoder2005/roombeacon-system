-- Derived map addresses stay separate from the original source address.
WITH candidates AS (
    SELECT p.*,
           g.geocoded_address_text,
           g.geocode_provider,
           g.geocode_precision,
           CASE WHEN g.geocode_provider = 'nominatim'
                THEN '© OpenStreetMap contributors — https://www.openstreetmap.org/copyright'
           END AS geocode_attribution,
           CASE
             WHEN regexp_matches(lower(COALESCE(p.full_address_text, '')),
                  '(đường|duong|hẻm|ngõ|ngách)\s+\S|^\s*[0-9]+[/0-9a-z-]*\s+[a-zà-ỹ]')
               THEN p.full_address_text
             WHEN regexp_matches(lower(COALESCE(p.map_query_raw, '')),
                  '(đường|duong|hẻm|ngõ|ngách)\s+\S|^\s*[0-9]+[/0-9a-z-]*\s+[a-zà-ỹ]')
               THEN p.map_query_raw
             WHEN g.geocode_precision IN ('house', 'street', 'road', 'building', 'apartments', 'residential', 'pedestrian')
                  AND NULLIF(TRIM(g.geocoded_address_text), '') IS NOT NULL
               THEN g.geocoded_address_text
             ELSE COALESCE(p.full_address_text, NULLIF(TRIM(p.map_query_raw), ''),
                           p.location_raw, NULLIF(TRIM(g.geocoded_address_text), ''))
           END AS enriched_address_text
    FROM v_latest_posts p
    LEFT JOIN mysql_db.map_geocodes g
      ON g.latitude = ROUND(p.map_latitude, 6)
     AND g.longitude = ROUND(p.map_longitude, 6)
)
SELECT *,
       CASE
         WHEN enriched_address_text = full_address_text THEN 'source_detail'
         WHEN enriched_address_text = map_query_raw THEN 'map_query'
         WHEN enriched_address_text = geocoded_address_text THEN 'reverse_geocode'
         WHEN enriched_address_text = location_raw THEN 'source_card'
         ELSE 'none'
       END AS enriched_address_source
FROM candidates
