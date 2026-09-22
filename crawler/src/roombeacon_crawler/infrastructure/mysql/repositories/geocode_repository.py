from contextlib import contextmanager

from sqlalchemy import text
from roombeacon_crawler.domain.models.geocoded_location import GeocodedLocation
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

class MySQLGeocodeRepository:
    def __init__(self, connection=None):
        self.connection = connection

    @contextmanager
    def _connection(self):
        from sqlalchemy.engine.base import Engine
        if isinstance(self.connection, Engine):
            conn = self.connection.connect()
            close_it = True
        elif self.connection is not None:
            conn = self.connection
            close_it = False
        else:
            conn = MySQLConnectionFactory.get_engine().connect()
            close_it = True
            
        try:
            yield conn
        finally:
            if close_it:
                conn.close()

    def ensure_table(self):
        with self._connection() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS map_geocodes (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    latitude DECIMAL(9, 6) NOT NULL,
                    longitude DECIMAL(9, 6) NOT NULL,
                    geocoded_address_text VARCHAR(1000),
                    geocoded_ward VARCHAR(255),
                    geocoded_district VARCHAR(255),
                    geocoded_city VARCHAR(255),
                    geocode_provider VARCHAR(50),
                    geocode_precision VARCHAR(50),
                    geocoded_at TIMESTAMP NOT NULL,
                    UNIQUE KEY uk_coords (latitude, longitude)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS map_geocode_retries (
                    latitude DECIMAL(9,6) NOT NULL,
                    longitude DECIMAL(9,6) NOT NULL,
                    retry_after DATETIME NOT NULL,
                    PRIMARY KEY (latitude, longitude)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()

    def get_cached(self, latitude: float, longitude: float) -> GeocodedLocation | None:
        with self._connection() as conn:
            res = conn.execute(text("""
                SELECT latitude, longitude, geocoded_address_text, geocoded_ward, 
                       geocoded_district, geocoded_city, geocode_provider, 
                       geocode_precision, geocoded_at
                FROM map_geocodes
                WHERE latitude = ROUND(:lat, 6)
                  AND longitude = ROUND(:lon, 6)
                LIMIT 1
            """), {"lat": latitude, "lon": longitude}).fetchone()
        
            if res:
                return GeocodedLocation(
                    latitude=float(res.latitude),
                    longitude=float(res.longitude),
                    geocoded_address_text=res.geocoded_address_text,
                    geocoded_ward=res.geocoded_ward,
                    geocoded_district=res.geocoded_district,
                    geocoded_city=res.geocoded_city,
                    geocode_provider=res.geocode_provider,
                    geocode_precision=res.geocode_precision,
                    geocoded_at=res.geocoded_at
                )
            return None

    def save(self, loc: GeocodedLocation):
        with self._connection() as conn:
            conn.execute(text("""
                INSERT INTO map_geocodes (
                    latitude, longitude, geocoded_address_text, geocoded_ward,
                    geocoded_district, geocoded_city, geocode_provider,
                    geocode_precision, geocoded_at
                ) VALUES (
                    ROUND(:lat, 6), ROUND(:lon, 6), :addr, :ward, :dist, :city, :prov, :prec, :at
                )
                ON DUPLICATE KEY UPDATE
                    geocoded_address_text = VALUES(geocoded_address_text),
                    geocoded_ward = VALUES(geocoded_ward),
                    geocoded_district = VALUES(geocoded_district),
                    geocoded_city = VALUES(geocoded_city),
                    geocode_provider = VALUES(geocode_provider),
                    geocode_precision = VALUES(geocode_precision),
                    geocoded_at = VALUES(geocoded_at)
            """), {
                "lat": loc.latitude, "lon": loc.longitude,
                "addr": loc.geocoded_address_text,
                "ward": loc.geocoded_ward, "dist": loc.geocoded_district,
                "city": loc.geocoded_city, "prov": loc.geocode_provider,
                "prec": loc.geocode_precision, "at": loc.geocoded_at
            })
            conn.commit()

    @contextmanager
    def enrichment_lock(self):
        """Serialize batches, including manually launched batches, on this database."""
        with self._connection() as conn:
            acquired = conn.execute(text("SELECT GET_LOCK('roombeacon_geocoding', 0)")).scalar() == 1
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute(text("SELECT RELEASE_LOCK('roombeacon_geocoding')"))

    def pending_coordinates(self, limit: int):
        with self._connection() as conn:
            return conn.execute(text("""
                WITH latest AS (
                    SELECT v.source_payload, p.platform_id,
                           ROW_NUMBER() OVER (PARTITION BY v.rental_post_id
                               ORDER BY v.observed_at DESC, v.id DESC) AS rn
                    FROM rental_post_versions v
                    JOIN rental_posts p ON p.id = v.rental_post_id
                ), points AS (
                    SELECT pl.code,
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(l.source_payload, '$.map_location.latitude')) AS DECIMAL(12,8)) AS lat,
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(l.source_payload, '$.map_location.longitude')) AS DECIMAL(12,8)) AS lon
                    FROM latest l JOIN platforms pl ON pl.id = l.platform_id
                    WHERE l.rn = 1
                      AND JSON_TYPE(JSON_EXTRACT(l.source_payload, '$.map_location.latitude')) IN ('DOUBLE', 'INTEGER', 'DECIMAL')
                      AND JSON_TYPE(JSON_EXTRACT(l.source_payload, '$.map_location.longitude')) IN ('DOUBLE', 'INTEGER', 'DECIMAL')
                )
                SELECT DISTINCT ROUND(p.lat, 6) AS lat, ROUND(p.lon, 6) AS lon
                FROM points p
                WHERE p.lat BETWEEN -90 AND 90 AND p.lon BETWEEN -180 AND 180
                  AND NOT (p.code = 'cafeland' AND p.lat = 10.876248 AND p.lon = 106.660338)
                  AND NOT (p.code = 'nhatrovn' AND p.lat = 10.6979911 AND p.lon = 106.7168188)
                  AND NOT EXISTS (SELECT 1 FROM map_geocodes g
                      WHERE g.latitude = ROUND(p.lat, 6) AND g.longitude = ROUND(p.lon, 6))
                  AND NOT EXISTS (SELECT 1 FROM map_geocode_retries r
                      WHERE r.latitude = ROUND(p.lat, 6) AND r.longitude = ROUND(p.lon, 6)
                        AND r.retry_after > UTC_TIMESTAMP())
                ORDER BY lat, lon LIMIT :limit
            """), {"limit": limit}).fetchall()

    def defer_failure(self, latitude: float, longitude: float):
        """Do not let an unresolved coordinate consume every scheduled batch."""
        with self._connection() as conn:
            conn.execute(text("""
                INSERT INTO map_geocode_retries (latitude, longitude, retry_after)
                VALUES (ROUND(:lat, 6), ROUND(:lon, 6), UTC_TIMESTAMP() + INTERVAL 1 DAY)
                ON DUPLICATE KEY UPDATE retry_after = VALUES(retry_after)
            """), {"lat": latitude, "lon": longitude})
            conn.commit()
