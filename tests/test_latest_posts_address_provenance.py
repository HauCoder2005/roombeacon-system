"""Verify latest-post address inheritance without rewriting raw versions."""

from pathlib import Path

import duckdb


def test_latest_posts_inherits_stable_enrichment_with_provenance():
    connection = duckdb.connect()
    connection.execute("ATTACH ':memory:' AS mysql_db")
    connection.execute(
        "CREATE TABLE mysql_db.rental_post_versions("
        "id BIGINT, rental_post_id BIGINT, url VARCHAR, title_raw VARCHAR, "
        "observed_at TIMESTAMP)"
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
        "id BIGINT, rental_post_id BIGINT, rental_post_version_id BIGINT, "
        "area_value DOUBLE, created_at TIMESTAMP)"
    )
    connection.execute("INSERT INTO mysql_db.platforms VALUES (1, 'source')")
    connection.execute(
        "INSERT INTO mysql_db.rental_posts VALUES "
        "(10, 1, 'stable-id', TIMESTAMP '2026-08-01', TIMESTAMP '2026-08-02')"
    )
    connection.execute(
        "INSERT INTO mysql_db.rental_post_versions VALUES "
        "(100, 10, 'detail', 'title', TIMESTAMP '2026-08-01'), "
        "(101, 10, 'lightweight', 'title', TIMESTAMP '2026-08-02')"
    )
    connection.execute(
        "INSERT INTO mysql_db.post_addresses VALUES "
        "(1, 10, 100, 'Confirmed address', TIMESTAMP '2026-08-01')"
    )
    connection.execute(
        "INSERT INTO mysql_db.post_details VALUES "
        "(1, 10, 100, 25.0, TIMESTAMP '2026-08-01')"
    )

    analytics_sql = Path("analytics/duckdb/sql/latest_posts.sql").read_text()
    assert not Path("crawler/src/analytics/duckdb/sql/latest_posts.sql").exists()
    connection.execute(f"CREATE VIEW latest_posts AS {analytics_sql}")

    latest_post = connection.execute(
        "SELECT full_address_text, full_address_inherited, "
        "area_value, area_inherited "
        "FROM latest_posts"
    ).fetchone()
    latest_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('latest_posts')").fetchall()
    }
    raw_address_count = connection.execute(
        "SELECT COUNT(*) FROM mysql_db.post_addresses"
    ).fetchone()[0]
    connection.close()

    assert latest_post == ("Confirmed address", True, 25.0, True)
    assert {
        "source_code",
        "rental_post_id",
        "source_listing_id",
        "title_raw",
        "url",
        "price_amount",
        "area_value",
        "area_inherited",
        "location_raw",
        "latest_observed_at",
    } <= latest_columns
    assert raw_address_count == 1
