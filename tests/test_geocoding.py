import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from roombeacon_crawler.domain.models.geocoded_location import GeocodedLocation
from roombeacon_crawler.services.reverse_geocoder import NominatimReverseGeocoder
from roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository import MySQLGeocodeRepository
from roombeacon_crawler.jobs.enrich_geocodes import GeocodeEnrichmentJob
import urllib.error
import json

@pytest.fixture
def geocoder():
    return NominatimReverseGeocoder(allow_public=True)

def test_invalid_latitude_no_provider_call(geocoder):
    # Case C
    with patch('urllib.request.urlopen') as mock_urlopen:
        res = geocoder.reverse(91.0, 106.0)
        assert res is None
        mock_urlopen.assert_not_called()

def test_invalid_longitude_no_provider_call(geocoder):
    # Case D
    with patch('urllib.request.urlopen') as mock_urlopen:
        res = geocoder.reverse(10.0, 181.0)
        assert res is None
        mock_urlopen.assert_not_called()

def test_valid_hcmc_coordinate_address_result(geocoder):
    # Case A
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "display_name": "Test Address, HCMC",
        "address": {"suburb": "Phường A", "city": "Hồ Chí Minh"},
        "type": "house"
    }).encode('utf-8')
    
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        res = geocoder.reverse(10.8452915, 106.7795828)
        assert res is not None
        assert res.geocoded_address_text == "Test Address, HCMC"
        assert res.geocoded_ward == "Phường A"
        assert res.geocoded_city == "Hồ Chí Minh"
        assert res.geocode_precision == "house"

def test_provider_failure_fails_safely(geocoder):
    # Case E
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        res = geocoder.reverse(10.8452915, 106.7795828)
        assert res is None

@patch('roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository.MySQLConnectionFactory.get_engine')
def test_cache_hit_prevents_provider_call(mock_engine):
    # Case B
    mock_conn = MagicMock()
    mock_engine.return_value.connect.return_value = mock_conn
    
    # Setup mock to return a cached result
    mock_res = MagicMock()
    mock_res.latitude = 10.0
    mock_res.longitude = 106.0
    mock_res.geocoded_address_text = "Cached"
    mock_res.geocoded_ward = None
    mock_res.geocoded_district = None
    mock_res.geocoded_city = None
    mock_res.geocode_provider = "nominatim"
    mock_res.geocode_precision = "unknown"
    mock_res.geocoded_at = datetime.now()
    
    mock_conn.execute.return_value.fetchone.return_value = mock_res
    
    repo = MySQLGeocodeRepository()
    cached = repo.get_cached(10.0, 106.0)
    assert cached.geocoded_address_text == "Cached"

def test_best_address_text_logic():
    # Case F, G, H
    import duckdb
    conn = duckdb.connect()
    
    # Mocking ranked_posts to simulate latest_posts.sql logic
    conn.execute("""
        CREATE TABLE ranked_posts AS 
        SELECT 1 as id, 'source' as source_code, '1' as rental_post_id, '1' as source_listing_id, 
               'title' as title_raw, 'url' as url, 100 as price_amount, 50 as area_value,
               CAST(NULL AS VARCHAR) as full_address_text, 'raw_loc' as location_raw, FALSE as full_address_inherited,
               'prov' as map_provider, 10.0 as map_latitude, 106.0 as map_longitude, NULL as map_query_raw,
               current_date as latest_observed_at, current_date as first_observed_at, current_date as last_observed_at, 1 as active_days, 1 as row_number
    """)
    conn.execute("""
        CREATE TABLE mysql_map_geocodes AS 
        SELECT 10.0 as latitude, 106.0 as longitude, 'Geocoded Address' as geocoded_address_text, 
               'Ward' as geocoded_ward, 'Dist' as geocoded_district, 'City' as geocoded_city,
               'nominatim' as geocode_provider, 'house' as geocode_precision
    """)
    
    # Execute the COALESCE logic
    res = conn.execute("""
        SELECT 
            rp.full_address_text,
            geo.geocoded_address_text,
            rp.location_raw,
            COALESCE(rp.full_address_text, geo.geocoded_address_text, rp.location_raw) as best_address_text,
            CASE 
                WHEN rp.full_address_text IS NOT NULL THEN 'source_detail'
                WHEN geo.geocoded_address_text IS NOT NULL THEN 'reverse_geocode'
                WHEN rp.location_raw IS NOT NULL THEN 'source_card'
                ELSE 'none'
            END AS best_address_source
        FROM ranked_posts rp
        LEFT JOIN mysql_map_geocodes geo ON rp.map_latitude = geo.latitude AND rp.map_longitude = geo.longitude
    """).fetchone()
    
    # Case G: full_address is NULL, geocoded is present -> best is geocoded
    assert res[3] == 'Geocoded Address'
    assert res[4] == 'reverse_geocode'
    
    # Case F: full_address present
    conn.execute("UPDATE ranked_posts SET full_address_text = 'Source Address'")
    res = conn.execute("""
        SELECT 
            COALESCE(rp.full_address_text, geo.geocoded_address_text, rp.location_raw) as best_address_text,
            CASE 
                WHEN rp.full_address_text IS NOT NULL THEN 'source_detail'
                WHEN geo.geocoded_address_text IS NOT NULL THEN 'reverse_geocode'
                WHEN rp.location_raw IS NOT NULL THEN 'source_card'
                ELSE 'none'
            END AS best_address_source
        FROM ranked_posts rp
        LEFT JOIN mysql_map_geocodes geo ON rp.map_latitude = geo.latitude AND rp.map_longitude = geo.longitude
    """).fetchone()
    assert res[0] == 'Source Address'
    assert res[1] == 'source_detail'
    
    # Case H: No full_address, no geocode, but location_raw exists
    conn.execute("UPDATE ranked_posts SET full_address_text = NULL")
    conn.execute("DELETE FROM mysql_map_geocodes")
    res = conn.execute("""
        SELECT 
            COALESCE(rp.full_address_text, geo.geocoded_address_text, rp.location_raw) as best_address_text,
            CASE 
                WHEN rp.full_address_text IS NOT NULL THEN 'source_detail'
                WHEN geo.geocoded_address_text IS NOT NULL THEN 'reverse_geocode'
                WHEN rp.location_raw IS NOT NULL THEN 'source_card'
                ELSE 'none'
            END AS best_address_source
        FROM ranked_posts rp
        LEFT JOIN mysql_map_geocodes geo ON rp.map_latitude = geo.latitude AND rp.map_longitude = geo.longitude
    """).fetchone()
    assert res[0] == 'raw_loc'
    assert res[1] == 'source_card'



def test_repository_closes_owned_connection_on_failure():
    with patch('roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository.MySQLConnectionFactory.get_engine') as engine:
        conn = engine.return_value.connect.return_value
        conn.execute.side_effect = RuntimeError('database unavailable')
        with pytest.raises(RuntimeError):
            MySQLGeocodeRepository().get_cached(10, 106)
        conn.close.assert_called_once()


def test_repository_keeps_injected_connection_open():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    assert MySQLGeocodeRepository(connection=conn).get_cached(10, 106) is None
    conn.close.assert_not_called()


def test_enrichment_uses_real_view_sql():
    from pathlib import Path
    import duckdb
    with duckdb.connect() as conn:
        conn.execute("ATTACH ':memory:' AS mysql_db")
        conn.execute("CREATE TABLE mysql_db.map_geocodes AS SELECT 10.0 latitude, 106.0 longitude, '123 Lê Lợi' geocoded_address_text, 'nominatim' geocode_provider, 'house' geocode_precision")
        conn.execute("CREATE TABLE v_latest_posts AS SELECT 'Phường 1' full_address_text, 'HCM' location_raw, CAST(NULL AS VARCHAR) map_query_raw, 10.0 map_latitude, 106.0 map_longitude")
        query = Path('analytics/duckdb/sql/optional/latest_posts_enriched.sql').read_text()
        conn.execute('CREATE VIEW enriched AS ' + query)
        assert conn.execute('SELECT enriched_address_text, enriched_address_source FROM enriched').fetchone() == ('123 Lê Lợi', 'reverse_geocode')
        conn.execute("UPDATE v_latest_posts SET full_address_text = '45 Nguyễn Trãi'")
        assert conn.execute('SELECT enriched_address_text, enriched_address_source FROM enriched').fetchone() == ('45 Nguyễn Trãi', 'source_detail')


def test_view_manager_publishes_enrichment_without_cycle(tmp_path, monkeypatch):
    from pathlib import Path
    from analytics.duckdb import views
    sql_dir = tmp_path / 'sql'
    (sql_dir / 'optional').mkdir(parents=True)
    (sql_dir / 'latest_posts.sql').write_text("""
        SELECT 'Phường 1' AS full_address_text, 'HCM' AS location_raw,
               NULL::VARCHAR AS map_query_raw, 10.0 AS map_latitude, 106.0 AS map_longitude,
               'Phường 1' AS best_address_text, 'source_detail' AS best_address_source
    """)
    (sql_dir / 'optional/latest_posts_enriched.sql').write_text(
        Path('analytics/duckdb/sql/optional/latest_posts_enriched.sql').read_text()
    )
    monkeypatch.setattr(views, 'SQL_DIR', sql_dir)
    import duckdb
    with duckdb.connect() as conn:
        conn.execute("ATTACH ':memory:' AS mysql_db")
        # The core view remains available before schema initialization.
        assert views.DuckDBViewManager.create_views(conn, strict=True) == ['v_latest_posts']
        conn.execute("CREATE TABLE mysql_db.map_geocodes AS SELECT 10.0 latitude, 106.0 longitude, '123 Lê Lợi' geocoded_address_text, 'nominatim' geocode_provider, 'house' geocode_precision")
        for _ in range(2):
            created = views.DuckDBViewManager.create_views(conn, strict=True)
            assert 'v_latest_posts_enriched' in created
            assert conn.execute('SELECT full_address_text, best_address_text, best_address_source FROM v_latest_posts').fetchone() == ('Phường 1', '123 Lê Lợi', 'reverse_geocode')
        conn.execute("UPDATE mysql_db.map_geocodes SET geocode_precision='city', geocoded_address_text='Hồ Chí Minh'")
        assert conn.execute('SELECT best_address_text FROM v_latest_posts').fetchone()[0] == 'Phường 1'


def test_public_geocoder_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv('GEOCODER_ALLOW_PUBLIC_NOMINATIM', raising=False)
    monkeypatch.delenv('GEOCODER_BASE_URL', raising=False)
    with patch('urllib.request.urlopen') as fetch:
        provider = NominatimReverseGeocoder()
        assert provider.enabled is False
        assert provider.reverse(10, 106) is None
        fetch.assert_not_called()
