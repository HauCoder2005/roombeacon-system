"""Verify latest-post address inheritance without rewriting raw versions."""

from pathlib import Path

import duckdb


def _create_map_geocodes_table(connection):
    """Represent the canonical view's intentional geocode-cache dependency."""
    connection.execute(
        "CREATE TABLE mysql_db.map_geocodes("
        "latitude DOUBLE, longitude DOUBLE, geocoded_address_text VARCHAR, "
        "geocoded_ward VARCHAR, geocoded_district VARCHAR, geocoded_city VARCHAR, "
        "geocode_provider VARCHAR, geocode_precision VARCHAR)"
    )


def test_latest_posts_uses_latest_confirmed_address_with_provenance():
    connection = duckdb.connect()
    connection.execute("ATTACH ':memory:' AS mysql_db")
    _create_map_geocodes_table(connection)
    connection.execute(
        "CREATE TABLE mysql_db.rental_post_versions("
        "id BIGINT, rental_post_id BIGINT, url VARCHAR, title_raw VARCHAR, "
        "observed_at TIMESTAMP, source_payload JSON)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.rental_posts("
        "id BIGINT, platform_id BIGINT, platform_post_id VARCHAR, "
        "first_observed_at TIMESTAMP, last_observed_at TIMESTAMP)"
    )
    connection.execute("CREATE TABLE mysql_db.platforms(id BIGINT, code VARCHAR)")
    connection.execute(
        "CREATE TABLE mysql_db.post_prices("
        "id BIGINT, rental_post_version_id BIGINT, price_amount DOUBLE)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_addresses("
        "id BIGINT, rental_post_id BIGINT, rental_post_version_id BIGINT, "
        "full_address_text VARCHAR, created_at TIMESTAMP)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_details("
        "id BIGINT, rental_post_version_id BIGINT, area_value DOUBLE)"
    )
    connection.execute("INSERT INTO mysql_db.platforms VALUES (1, 'source')")
    connection.execute(
        "INSERT INTO mysql_db.rental_posts VALUES "
        "(10, 1, 'stable-id', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-02')"
    )
    connection.execute(
        "INSERT INTO mysql_db.rental_post_versions VALUES "
        "(100, 10, 'detail', 'title', TIMESTAMP '2026-08-01', NULL), "
        "(101, 10, 'lightweight', 'title', TIMESTAMP '2026-08-02', NULL)"
    )
    connection.execute(
        "INSERT INTO mysql_db.post_addresses VALUES "
        "(1, 10, 100, 'Confirmed address', TIMESTAMP '2026-08-01')"
    )

    analytics_sql = Path("analytics/duckdb/sql/latest_posts.sql").read_text()
    assert not Path("crawler/src/analytics/duckdb/sql/latest_posts.sql").exists()
    connection.execute(f"CREATE VIEW latest_posts AS {analytics_sql}")

    latest_post = connection.execute(
        "SELECT full_address_text, full_address_inherited "
        "FROM latest_posts"
    ).fetchone()
    raw_address_count = connection.execute(
        "SELECT COUNT(*) FROM mysql_db.post_addresses"
    ).fetchone()[0]
    connection.close()

    assert latest_post == ("Confirmed address", True)
    assert raw_address_count == 1


def test_latest_posts_keeps_raw_location_independent_from_confirmed_address():
    connection = duckdb.connect()
    connection.execute("ATTACH ':memory:' AS mysql_db")
    _create_map_geocodes_table(connection)
    connection.execute(
        "CREATE TABLE mysql_db.rental_post_versions("
        "id BIGINT, rental_post_id BIGINT, url VARCHAR, title_raw VARCHAR, "
        "observed_at TIMESTAMP, source_payload JSON)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.rental_posts("
        "id BIGINT, platform_id BIGINT, platform_post_id VARCHAR, "
        "first_observed_at TIMESTAMP, last_observed_at TIMESTAMP)"
    )
    connection.execute("CREATE TABLE mysql_db.platforms(id BIGINT, code VARCHAR)")
    connection.execute(
        "CREATE TABLE mysql_db.post_prices("
        "id BIGINT, rental_post_version_id BIGINT, price_amount DOUBLE)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_addresses("
        "id BIGINT, rental_post_id BIGINT, rental_post_version_id BIGINT, "
        "full_address_text VARCHAR, created_at TIMESTAMP)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_details("
        "id BIGINT, rental_post_version_id BIGINT, area_value DOUBLE)"
    )
    connection.execute("INSERT INTO mysql_db.platforms VALUES (1, 'source')")
    connection.execute(
        "INSERT INTO mysql_db.rental_posts VALUES "
        "(10, 1, 'raw-only', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01'), "
        "(20, 1, 'both', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01'), "
        "(30, 1, 'neither', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01')"
    )
    connection.execute(
        "INSERT INTO mysql_db.rental_post_versions VALUES "
        "(100, 10, 'raw-only', 'title', TIMESTAMP '2026-08-01', "
        " '{\"location_raw\":\"Raw district label\"}'), "
        "(200, 20, 'both', 'title', TIMESTAMP '2026-08-01', "
        " '{\"location_raw\":\"Raw listing location\"}'), "
        "(300, 30, 'neither', 'title', TIMESTAMP '2026-08-01', '{}')"
    )
    connection.execute(
        "INSERT INTO mysql_db.post_addresses VALUES "
        "(1, 20, 200, 'Confirmed street address', TIMESTAMP '2026-08-01')"
    )

    analytics_sql = Path("analytics/duckdb/sql/latest_posts.sql").read_text()
    connection.execute(f"CREATE VIEW latest_posts AS {analytics_sql}")
    actual = connection.execute(
        "SELECT source_listing_id, location_raw, full_address_text "
        "FROM latest_posts ORDER BY source_listing_id"
    ).fetchall()
    connection.close()

    assert actual == [
        ("both", "Raw listing location", "Confirmed street address"),
        ("neither", None, None),
        ("raw-only", "Raw district label", None),
    ]

def test_latest_posts_exposes_map_location():
    connection = duckdb.connect()
    connection.execute("ATTACH ':memory:' AS mysql_db")
    _create_map_geocodes_table(connection)
    connection.execute(
        "CREATE TABLE mysql_db.rental_post_versions("
        "id BIGINT, rental_post_id BIGINT, url VARCHAR, title_raw VARCHAR, "
        "observed_at TIMESTAMP, source_payload JSON)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.rental_posts("
        "id BIGINT, platform_id BIGINT, platform_post_id VARCHAR, "
        "first_observed_at TIMESTAMP, last_observed_at TIMESTAMP)"
    )
    connection.execute("CREATE TABLE mysql_db.platforms(id BIGINT, code VARCHAR)")
    connection.execute(
        "CREATE TABLE mysql_db.post_prices("
        "id BIGINT, rental_post_version_id BIGINT, price_amount DOUBLE)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_addresses("
        "id BIGINT, rental_post_id BIGINT, rental_post_version_id BIGINT, "
        "full_address_text VARCHAR, created_at TIMESTAMP)"
    )
    connection.execute(
        "CREATE TABLE mysql_db.post_details("
        "id BIGINT, rental_post_version_id BIGINT, area_value DOUBLE)"
    )
    connection.execute("INSERT INTO mysql_db.platforms VALUES (1, 'source')")
    connection.execute(
        "INSERT INTO mysql_db.rental_posts VALUES "
        "(10, 1, 'with-map', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01'), "
        "(20, 1, 'without-map', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01'), "
        "(30, 2, 'cafeland-map', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-01')"
    )
    connection.execute("INSERT INTO mysql_db.platforms VALUES (2, 'cafeland')")
    connection.execute(
        "INSERT INTO mysql_db.rental_post_versions VALUES "
        "(100, 10, 'with-map', 'title', TIMESTAMP '2026-08-01', "
        " '{\"location_raw\":\"Raw district label\", \"map_location\": {\"provider\": \"google_maps_embed\", \"latitude\": 10.123, \"longitude\": 106.456}}'), "
        "(200, 20, 'without-map', 'title', TIMESTAMP '2026-08-01', "
        " '{\"location_raw\":\"Raw listing location\"}'), "
        "(300, 30, 'cafeland-map', 'title', TIMESTAMP '2026-08-01', "
        " '{\"map_location\": {\"provider\": \"google_maps_embed\", \"latitude\": 10.876248, \"longitude\": 106.660338}}')"
    )

    analytics_sql = Path("analytics/duckdb/sql/latest_posts.sql").read_text()
    connection.execute(f"CREATE VIEW latest_posts AS {analytics_sql}")
    actual = connection.execute(
        "SELECT source_listing_id, map_provider, map_latitude, map_longitude "
        "FROM latest_posts ORDER BY source_listing_id"
    ).fetchall()
    connection.close()

    assert actual == [
        ("cafeland-map", "google_maps_embed", None, None),
        ("with-map", "google_maps_embed", 10.123, 106.456),
        ("without-map", None, None, None),
    ]


def test_only_observed_template_coordinates_are_quarantined():
    """Evaluate the production CASE expressions against source and coordinate pairs."""
    import json
    sql = Path('analytics/duckdb/sql/latest_posts.sql').read_text()
    start = sql.index('        CASE WHEN (')
    end = sql.index("        json_extract_string(version.source_payload, '$.map_location.query_raw')", start)
    expressions = sql[start:end].strip().rstrip(',')
    with duckdb.connect() as conn:
        for source, lat, lon, expected in (
            ('cafeland', 10.876248, 106.660338, (None, None)),
            ('cafeland', 10.8452915, 106.7795828, (10.8452915, 106.7795828)),
            ('nhatrovn', 10.6979911, 106.7168188, (None, None)),
            ('mogi', 10.6979911, 106.7168188, (10.6979911, 106.7168188)),
        ):
            payload = json.dumps({'map_location': {'latitude': lat, 'longitude': lon}})
            actual = conn.execute(f'SELECT {expressions} FROM (SELECT ? AS code) platform CROSS JOIN (SELECT ?::JSON AS source_payload) version', [source, payload]).fetchone()
            assert actual == expected
