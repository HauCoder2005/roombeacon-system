"""Round-trip and regression tests for location and coordinate extraction."""

import json
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.mappers.bronze_observation_loader import BronzeObservationLoader, compute_observation_content_hash
from roombeacon_crawler.validators.location_validator import LocationValidator
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
from roombeacon_crawler.sources.common_html import LocationCandidate

def test_location_round_trip():
    # A. ListingDetailRaw
    detail = ListingDetailRaw(
        source="test_source",
        listing_id="123",
        detail_url="https://test",
        latitude=10.77,
        longitude=106.69
    )
    assert detail.latitude == 10.77
    assert detail.longitude == 106.69

    # B. RentalBronzeRecord
    record = BronzeMapper.map(card=None, detail=detail, run_id="run_1")
    assert record.latitude == 10.77
    assert record.longitude == 106.69

    # C. serialized listing artifact
    import dataclasses
    serialized = dataclasses.asdict(record)
    assert serialized["latitude"] == 10.77
    assert serialized["longitude"] == 106.69

    # D & E. BronzeObservationLoader
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        with open(path / "listings.json", "w", encoding="utf-8") as f:
            json.dump([serialized], f)
        
        obs_list = BronzeObservationLoader.load_from_bronze_dir(tmpdir, "run_1")
        assert len(obs_list) == 1
        obs = obs_list[0]
        assert obs.latitude == 10.77
        assert obs.longitude == 106.69

    # F. MySQL persistence payload
    connection = MagicMock()
    repo = MySQLPostChildrenRepository(connection=connection)
    repo._persist_address(connection, obs, post_id=1, observation_id=1)
    
    assert connection.execute.called
    call_args = connection.execute.call_args
    params = call_args[0][1]
    assert params["lat"] == 10.77
    assert params["lng"] == 106.69


def test_compute_observation_content_hash_regression():
    base_kwargs = {
        "title_raw": "Test",
        "price_raw": "1000",
        "area_raw": "50",
    }
    
    # Case A: same listing + same lat/lng
    hash1 = compute_observation_content_hash(**base_kwargs, latitude=10.0, longitude=106.0)
    hash2 = compute_observation_content_hash(**base_kwargs, latitude=10.0, longitude=106.0)
    assert hash1 == hash2
    
    # Case B: same listing + latitude changed
    hash3 = compute_observation_content_hash(**base_kwargs, latitude=10.1, longitude=106.0)
    assert hash1 != hash3
    
    # Case C: same listing + longitude changed
    hash4 = compute_observation_content_hash(**base_kwargs, latitude=10.0, longitude=106.1)
    assert hash1 != hash4


def test_coordinate_validation_regression():
    # Valid
    assert LocationValidator.validate_coordinates(10.77, 106.69) == (10.77, 106.69)
    # Partial
    assert LocationValidator.validate_coordinates(10.77, None) == (None, None)
    assert LocationValidator.validate_coordinates(None, 106.69) == (None, None)
    # NaN/Inf
    assert LocationValidator.validate_coordinates(float("nan"), 106.69) == (None, None)
    assert LocationValidator.validate_coordinates(10.77, float("inf")) == (None, None)
    # 0,0
    assert LocationValidator.validate_coordinates(0, 0) == (None, None)
    # Swapped
    assert LocationValidator.validate_coordinates(106.69, 10.77) == (None, None)


def test_database_integrity_regression():
    connection = MagicMock()
    repo = MySQLPostChildrenRepository(connection=connection)
    
    # Valid pair
    obs_valid = MagicMock(address_raw="Test", latitude=10.77, longitude=106.69)
    repo._persist_address(connection, obs_valid, 1, 1)
    assert connection.execute.call_count == 1
    connection.execute.reset_mock()
    
    # Partial pair
    obs_partial = MagicMock(address_raw="Test", latitude=10.77, longitude=None)
    repo._persist_address(connection, obs_partial, 1, 1)
    # partial becomes null, but address exists, so it still inserts with lat=None, lng=None
    assert connection.execute.call_count == 1
    params = connection.execute.call_args[0][1]
    assert params["lat"] is None
    assert params["lng"] is None
    connection.execute.reset_mock()
    
    # NULL/NULL without address returns early
    obs_null = MagicMock(address_raw=None, latitude=None, longitude=None)
    repo._persist_address(connection, obs_null, 1, 1)
    assert connection.execute.call_count == 0


def test_map_candidate_regression():
    cand = LocationCandidate(
        address="123 Test",
        latitude=10.77,
        longitude=106.69,
        source_url="https://test"
    )
    assert cand.address == "123 Test"
    assert cand.latitude == 10.77
    assert cand.longitude == 106.69
    assert cand.source_url == "https://test"
