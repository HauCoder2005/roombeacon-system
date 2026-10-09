"""Listing search over a tiny Silver Parquet fixture (DuckDB, no network)."""

from datetime import datetime
import hashlib
import os
import time

import duckdb
import pytest

from roombeacon_api.application.listing_service import ListingFilters
from roombeacon_api.application.pagination import PageRequest
from roombeacon_api.application.sorting import SortSpec
from roombeacon_api.infrastructure.silver_listing_repository import SilverListingRepository


COLUMNS = (
    "rental_post_id BIGINT, source_code VARCHAR, source_listing_id VARCHAR, title_clean VARCHAR, title_raw VARCHAR, url VARCHAR, "
    "price_amount_clean DOUBLE, area_value_clean DOUBLE, district_text_extracted VARCHAR, ward_current VARCHAR, "
    "province_text_extracted VARCHAR, listing_intent VARCHAR, rental_scope VARCHAR, first_observed_at TIMESTAMP, "
    "last_observed_at TIMESTAMP, active_days BIGINT, duplicate_candidate_status VARCHAR, price_model_suitability VARCHAR"
)
ROWS = [
    (1, "phongtro123", "src1", "Phòng gần Lotte Quận 7", None, "https://x/1", 5e6, 30.0, "Quận 7", "Phường Tân Hưng", "Hồ Chí Minh", "RENT", "SINGLE_OR_ORDINARY_UNIT", "2026-09-21 03:00:00", "2026-10-02 08:00:00", 11, "UNIQUE_FINGERPRINT", "SUPPORTED"),
    (2, "mogi", "src2", None, "Căn hộ mini", "https://x/2", 4e6, 25.0, "Quận 7", None, None, "RENT", "SINGLE_OR_ORDINARY_UNIT", "2026-09-22 03:00:00", "2026-10-01 08:00:00", 9, "UNIQUE_FINGERPRINT", "SUPPORTED"),
    (3, "phongtro123", "src3", "Phòng trùng", None, "https://x/3", 4.5e6, 25.0, "Quận 7", "Phường Tân Hưng", None, "RENT", "SINGLE_OR_ORDINARY_UNIT", "2026-09-22 03:00:00", "2026-10-01 08:00:00", 9, "POSSIBLE_DUPLICATE", "SUPPORTED"),
    (4, "phongtro123", "src4", "Phòng Cầu Giấy", None, "https://x/4", 3e6, 20.0, None, None, "Hà Nội", "RENT", "SINGLE_OR_ORDINARY_UNIT", "2026-09-22 03:00:00", "2026-10-01 08:00:00", 9, "UNIQUE_FINGERPRINT", "SUPPORTED"),
    (5, "nhatot", "src5", "Sang nhượng phòng", None, "https://x/5", 2e6, 20.0, "Quận 3", None, "TP.HCM", "TRANSFER", "SINGLE_OR_ORDINARY_UNIT", "2026-09-22 03:00:00", "2026-10-01 08:00:00", 9, "UNIQUE_FINGERPRINT", "SUPPORTED"),
    (6, "phongtro123", "src6", "Giá lỗi", None, "https://x/6", 9e9, 20.0, "Quận 3", None, None, "RENT", "SINGLE_OR_ORDINARY_UNIT", "2026-09-22 03:00:00", "2026-10-01 08:00:00", 9, "UNIQUE_FINGERPRINT", "EXCLUDED"),
]


def _write(path, rows):
    connection = duckdb.connect()
    connection.execute(f"CREATE TABLE t ({COLUMNS})")
    connection.executemany(f"INSERT INTO t VALUES ({', '.join('?' * 18)})", rows)
    connection.execute(f"COPY t TO '{path}' (FORMAT PARQUET)")
    connection.close()


@pytest.fixture
def silver(tmp_path):
    path = tmp_path / "rental_listings.parquet"
    _write(path, ROWS)
    return path


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


DISTRICT_7 = _hash("DISTRICT|Quận 7")
WARD_TAN_HUNG = _hash("WARD|Quận 7|Phường Tân Hưng")


def _search(repo, page=PageRequest(1, 20), sort=SortSpec("last_observed_at", True), **filters):
    return repo.search(ListingFilters(**filters), sort, page)


def test_ids_match_the_warehouse_location_hashes(silver):
    card = SilverListingRepository(silver).get("1")

    assert card.district_id == DISTRICT_7 and card.ward_id == WARD_TAN_HUNG
    assert card.title == "Phòng gần Lotte Quận 7"
    assert card.source_listing_id == "src1"
    assert card.first_observed_at == datetime(2026, 9, 21, 3, 0) or card.first_observed_at.year == 2026


def test_default_search_keeps_supported_rent_in_market_unique_listings(silver):
    page = _search(SilverListingRepository(silver))

    assert sorted(c.id for c in page.items) == ["1", "2"]
    assert page.total == 2


def test_filters_location_price_area_text_and_duplicates(silver):
    repo = SilverListingRepository(silver)

    assert [c.id for c in _search(repo, ward_id=WARD_TAN_HUNG).items] == ["1"]
    assert [c.id for c in _search(repo, district_id=DISTRICT_7, price_max=4_500_000).items] == ["2"]
    assert [c.id for c in _search(repo, area_min=26).items] == ["1"]
    assert [c.id for c in _search(repo, q="LOTTE").items] == ["1"]
    assert [c.id for c in _search(repo, q="căn hộ").items] == ["2"]  # falls back to title_raw
    assert sorted(c.id for c in _search(repo, exclude_duplicates=False).items) == ["1", "2", "3"]
    assert [c.id for c in _search(repo, intent="TRANSFER").items] == ["5"]
    assert [c.id for c in _search(repo, q="'; DROP TABLE t; --").items] == []


def test_sorting_and_pagination(silver):
    repo = SilverListingRepository(silver)
    page = _search(repo, page=PageRequest(1, 1), sort=SortSpec("price", False))

    assert [c.id for c in page.items] == ["2"] and page.total == 2


def test_detail_ignores_search_quality_filters_but_unknown_ids_are_none(silver):
    repo = SilverListingRepository(silver)

    assert repo.get("6").price_suitability == "EXCLUDED"
    assert repo.get("999") is None


def test_unsupported_sort_field_never_reaches_sql(silver):
    with pytest.raises(ValueError):
        _search(SilverListingRepository(silver), sort=SortSpec("1; DROP", False))


def test_latest_listing_with_images_per_location(silver):
    repo = SilverListingRepository(silver)
    pairs = frozenset({("phongtro123", "src1"), ("phongtro123", "src3"), ("mogi", "src2")})

    assert repo.latest_with_images(pairs, "district", [DISTRICT_7, "ffffffffffffffff"]) == {DISTRICT_7: "1"}
    assert repo.latest_with_images(pairs, "ward", [WARD_TAN_HUNG]) == {WARD_TAN_HUNG: "1"}
    assert repo.latest_with_images(frozenset(), "district", [DISTRICT_7]) == {}


def test_reloads_when_silver_is_republished(silver):
    repo = SilverListingRepository(silver)
    assert _search(repo).total == 2

    time.sleep(0.01)
    _write(silver, ROWS[:1])
    os.utime(silver, (time.time() + 5, time.time() + 5))

    assert _search(repo).total == 1
