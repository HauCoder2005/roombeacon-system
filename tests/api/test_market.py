"""Market summary and daily trend endpoints."""

from tests.api.conftest import BINH_THANH


def test_market_summary(client):
    body = client.get("/api/v1/market/summary").json()

    assert body["meta"]["resource"] == "market_summary"
    assert body["data"] == {
        "scope": {"type": "city", "district": None},
        "listing_count": 132494,
        "priced_listing_count": 110000,
        "district_count": 55,
        "price": {"currency": "VND", "median": 4000000, "p25": 3000000, "p75": 5500000},
        "data_from": "2026-09-21T03:00:00Z",
        "data_until": "2026-10-02T08:00:00Z",
    }


def test_market_summary_for_a_district_and_unknown_district(client):
    body = client.get("/api/v1/market/summary", params={"district_id": BINH_THANH}).json()
    assert body["data"]["scope"] == {"type": "district", "district": {"id": BINH_THANH, "name": "Quận Bình Thạnh"}}
    assert client.get("/api/v1/market/summary", params={"district_id": "ffffffffffffffff"}).status_code == 404


def test_market_daily_series_and_date_validation(client):
    body = client.get("/api/v1/market/daily", params={"date_from": "2026-09-24"}).json()

    assert body["data"] == [
        {"date": "2026-09-24", "listings_observed": 12000, "new_listings": 800, "price_changes": 150, "median_price": 4000000}
    ]
    assert body["meta"]["filters"] == {"date_from": "2026-09-24"}
    assert client.get("/api/v1/market/daily", params={"date_from": "2026-10-05", "date_to": "2026-10-01"}).status_code == 422
    assert client.get("/api/v1/market/daily", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code == 422
