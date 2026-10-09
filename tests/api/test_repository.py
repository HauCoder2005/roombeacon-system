"""ClickHouse adapter: bound parameters, whitelisted ordering, error translation."""

import pytest

from roombeacon_api.application.pagination import PageRequest
from roombeacon_api.application.sorting import SortSpec
from roombeacon_api.domain.errors import DependencyUnavailableError
from roombeacon_api.infrastructure.location_repository import ClickHouseLocationRepository


class FakeResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.queries = []

    def query(self, sql, parameters=None):
        self.queries.append((sql, dict(parameters or {})))
        if self.error:
            raise self.error
        return FakeResult(self.responses.pop(0) if self.responses else [])


DISTRICT_ROW = ("0a1b2c3d4e5f6071", "Quận 3", 4100, 3900, 12, 5.5e6, 4.4e6, 6.6e6, 220000.0, 25.0)


def test_search_text_is_bound_never_interpolated():
    client = FakeClient(responses=[[(1,)], [DISTRICT_ROW]])
    repository = ClickHouseLocationRepository(client, "roombeacon_dw")

    page = repository.list_districts("'; DROP TABLE x --", SortSpec("listing_count", True), PageRequest(2, 10))

    for sql, parameters in client.queries:
        assert "DROP" not in sql
        assert parameters["q"] == "'; DROP TABLE x --"
        assert "{q:String}" in sql
    data_sql, data_parameters = client.queries[1]
    assert data_parameters["limit"] == 10 and data_parameters["offset"] == 10
    assert "ORDER BY listing_count DESC, id ASC" in data_sql
    assert page.total == 1
    assert page.items[0].name == "Quận 3" and page.items[0].price.median == 5.5e6


def test_nan_and_null_aggregates_become_none():
    row = ("0a1b2c3d4e5f6071", "Huyện Cần Giờ", 12, 0, 2, float("nan"), None, float("nan"), None, None)
    client = FakeClient(responses=[[row]])
    card = ClickHouseLocationRepository(client, "roombeacon_dw").get_district("0a1b2c3d4e5f6071")

    assert card.price.median is None and card.price.p25 is None


def test_unknown_sort_field_cannot_reach_sql():
    repository = ClickHouseLocationRepository(FakeClient(), "roombeacon_dw")

    with pytest.raises(ValueError):
        repository.list_districts("", SortSpec("1; DROP", False), PageRequest(1, 10))


def test_database_name_must_be_an_identifier():
    with pytest.raises(ValueError):
        ClickHouseLocationRepository(FakeClient(), "dw`; DROP")


def test_driver_errors_become_dependency_unavailable():
    repository = ClickHouseLocationRepository(FakeClient(error=ConnectionError("refused password=x")), "roombeacon_dw")

    with pytest.raises(DependencyUnavailableError) as raised:
        repository.ping()
    assert "password" not in str(raised.value)


def test_resolve_query_binds_ward_and_district():
    client = FakeClient(responses=[[]])
    ClickHouseLocationRepository(client, "roombeacon_dw").find_wards("Phường 1", "0a1b2c3d4e5f6071", 21)

    sql, parameters = client.queries[0]
    assert parameters == {"ward": "Phường 1", "district_id": "0a1b2c3d4e5f6071", "limit": 21}
    assert "Phường" not in sql
