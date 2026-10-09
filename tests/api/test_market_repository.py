"""ClickHouse adapters for price history and market series: bound parameters only."""

from datetime import date, datetime

from roombeacon_api.application.pagination import PageRequest
from roombeacon_api.infrastructure.market_repository import ClickHouseHistoryRepository, ClickHouseMarketRepository
from tests.api.test_repository import FakeClient


def test_history_binds_the_listing_id_and_paginates():
    client = FakeClient(responses=[[(2,)], [(datetime(2026, 9, 21), 3.8e6, 25.0, False, True)]])
    page = ClickHouseHistoryRepository(client, "roombeacon_dw").price_history("101", PageRequest(1, 50))

    count_sql, count_params = client.queries[0]
    data_sql, data_params = client.queries[1]
    assert count_params == {"listing_id": 101}
    assert data_params == {"listing_id": 101, "limit": 50, "offset": 0}
    assert "{listing_id:Int64}" in data_sql and "101" not in data_sql
    assert page.total == 2 and page.items[0].price == 3.8e6


def test_market_summary_filters_district_by_bound_id():
    client = FakeClient(responses=[[(10, 8, 1, 4e6, 3e6, 5e6, datetime(2026, 9, 20), datetime(2026, 10, 3))]])
    summary = ClickHouseMarketRepository(client, "roombeacon_dw").summary("0a1b2c3d4e5f6071")

    sql, params = client.queries[0]
    assert params == {"district_id": "0a1b2c3d4e5f6071"}
    assert "{district_id:String}" in sql
    assert summary.listing_count == 10 and summary.median == 4e6


def test_market_daily_binds_dates():
    client = FakeClient(responses=[[(date(2026, 9, 23), 14967, 962, 2694, 3.9e6)]])
    days = ClickHouseMarketRepository(client, "roombeacon_dw").daily(None, date(2026, 9, 23), date(2026, 9, 30))

    sql, params = client.queries[0]
    assert params == {"district_id": "", "date_from": "2026-09-23", "date_to": "2026-09-30"}
    assert days[0].new_listings == 962
