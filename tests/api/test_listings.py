"""Listing search, detail (with market comparison and model valuation) and price history."""

from tests.api.conftest import BINH_THANH, GO_VAP, WARD_25


def test_search_returns_listing_cards_with_pagination_and_valuation(client):
    response = client.get("/api/v1/listings", params={"per_page": 2})
    body = response.json()

    assert response.status_code == 200
    assert body["meta"]["resource"] == "listing"
    assert body["meta"]["pagination"]["total_items"] == 5
    assert body["meta"]["sort"] == ["-last_observed_at"]
    assert body["links"]["next"].startswith("/api/v1/listings?page=2&per_page=2")
    card = body["data"][0]
    assert set(card) == {
        "id", "type", "title", "source", "source_url", "price", "area_m2", "price_per_m2",
        "location", "intent", "scope", "first_observed_at", "last_observed_at", "active_days",
        "quality", "valuation", "links",
    }
    assert card["type"] == "listing" and isinstance(card["id"], str)
    assert card["links"]["self"] == f"/api/v1/listings/{card['id']}"


def test_search_filters_are_parsed_and_passed_through(client, listings):
    response = client.get(
        "/api/v1/listings",
        params={"district_id": BINH_THANH, "price_min": 3_000_000, "price_max": 6_000_000, "area_min": 20, "q": "phòng", "sort": "price"},
    )
    body = response.json()

    assert response.status_code == 200
    assert [c["id"] for c in body["data"]] == ["101"]
    assert body["meta"]["filters"] == {
        "district_id": BINH_THANH, "q": "phòng", "price_min": 3000000, "price_max": 6000000, "area_min": 20.0,
    }
    assert listings.last_filters.intent == "RENT" and listings.last_filters.exclude_duplicates is True


def test_invalid_listing_filters_are_422(client):
    assert client.get("/api/v1/listings", params={"price_min": 5_000_000, "price_max": 1_000_000}).json()["errors"][0]["field"] == "price_min"
    assert client.get("/api/v1/listings", params={"area_min": -1}).status_code == 422
    assert client.get("/api/v1/listings", params={"sort": "title"}).status_code == 422
    assert client.get("/api/v1/listings", params={"district_id": "nope"}).status_code == 422
    assert client.get("/api/v1/listings", params={"intent": "STEAL"}).status_code == 422


def test_contact_numbers_never_leave_the_api(client):
    card = client.get("/api/v1/listings/101").json()["data"]

    assert "0912" not in card["title"] and "***" in card["title"]
    assert card["source_url"] is None


def test_listing_card_formats_money_location_and_valuation(client):
    card = client.get("/api/v1/listings/101").json()["data"]

    assert card["price"] == {"currency": "VND", "amount": 3500000, "period": "month"}
    assert card["area_m2"] == 25.0 and card["price_per_m2"] == 140000
    assert card["location"] == {
        "level": "WARD", "district": {"id": BINH_THANH, "name": "Quận Bình Thạnh"}, "ward": {"id": WARD_25, "name": "Phường 25"},
    }
    # Fake model: 25 m2 * 160k * 1.1 (own source) = 4.4M; listing asks 3.5M -> about 20% below.
    assert card["valuation"] == {"estimate": 4400000, "delta_pct": -20.5, "label": "BELOW_ESTIMATE"}


def test_valuation_is_null_when_area_or_price_is_missing(client):
    assert client.get("/api/v1/listings/105").json()["data"]["valuation"] is None


def test_detail_compares_with_the_ward_or_district_market(client):
    ward_level = client.get("/api/v1/listings/101").json()
    district_level = client.get("/api/v1/listings/104").json()

    assert ward_level["meta"]["resource"] == "listing"
    assert ward_level["data"]["market"] == {
        "scope": "ward", "name": "Phường 25", "median": 4200000, "p25": 3360000, "p75": 5040000,
        "listing_count": 900, "position": "WITHIN_P25_P75",
    }
    assert district_level["data"]["market"]["scope"] == "district"
    assert district_level["data"]["market"]["name"] == "Quận Gò Vấp"


def test_detail_404_and_malformed_id(client):
    assert client.get("/api/v1/listings/999999").status_code == 404
    assert client.get("/api/v1/listings/12ab").status_code == 422


def test_price_history_is_paginated(client):
    body = client.get("/api/v1/listings/101/price-history").json()

    assert body["meta"]["resource"] == "price_point"
    assert body["data"] == [
        {"observed_at": "2026-09-21T03:00:00Z", "price": 3800000, "area_m2": 25.0, "is_price_change": False, "is_content_change": True},
        {"observed_at": "2026-09-28T00:00:00Z", "price": 3500000, "area_m2": 25.0, "is_price_change": True, "is_content_change": True},
    ]
    assert client.get("/api/v1/listings/999999/price-history").status_code == 404


def test_model_outage_does_not_break_search(client, price_model):
    price_model.unavailable = True
    response = client.get("/api/v1/listings", params={"district_id": GO_VAP})

    assert response.status_code == 200
    assert response.json()["data"][0]["valuation"] is None
