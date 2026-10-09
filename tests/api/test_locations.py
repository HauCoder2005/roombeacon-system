"""Location card endpoints: envelope, pagination, sorting, 200/300/301/304/404/422."""

from tests.api.conftest import BINH_THANH, QUAN_3, SNAPSHOT


ENVELOPE_KEYS = {"success", "code", "status", "message", "data", "errors", "meta", "links"}
META_KEYS = {
    "request_id", "timestamp", "api_version", "method", "path", "duration_ms",
    "resource", "data_snapshot", "cache", "pagination", "sort", "filters",
}


def test_district_list_returns_card_envelope_with_pagination(client):
    response = client.get("/api/v1/locations/districts", params={"per_page": 2})
    body = response.json()

    assert response.status_code == 200
    assert set(body) == ENVELOPE_KEYS
    assert set(body["meta"]) == META_KEYS
    assert body["success"] is True and body["code"] == 200 and body["status"] == "OK"
    assert body["errors"] is None
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert body["meta"]["resource"] == "district"
    assert body["meta"]["data_snapshot"]["snapshot_id"] == SNAPSHOT.snapshot_id
    assert body["meta"]["pagination"] == {
        "page": 1, "per_page": 2, "total_items": 4, "total_pages": 2, "has_next": True, "has_prev": False,
    }
    assert body["meta"]["sort"] == ["-listing_count"]
    assert body["links"]["next"] == "/api/v1/locations/districts?page=2&per_page=2&sort=-listing_count"
    assert body["links"]["prev"] is None

    card = body["data"][0]
    assert card["type"] == "district" and card["name"] == "Quận Gò Vấp"
    assert isinstance(card["id"], str)
    assert card["stats"] == {"listing_count": 7300, "priced_listing_count": 7000, "ward_count": 16}
    assert card["price"]["currency"] == "VND"
    assert card["price"]["median"] == 3_500_000
    assert card["links"]["wards"] == f"/api/v1/locations/districts/{card['id']}/wards"


def test_district_search_and_ascending_sort(client):
    body = client.get("/api/v1/locations/districts", params={"q": "quận", "sort": "median_price"}).json()

    assert [d["name"] for d in body["data"]] == ["Quận Gò Vấp", "Quận Bình Thạnh", "Quận 3"]
    assert body["meta"]["filters"] == {"q": "quận"}


def test_missing_price_is_null_not_zero(client):
    body = client.get("/api/v1/locations/districts", params={"q": "cần giờ"}).json()

    assert body["data"][0]["price"]["median"] is None


def test_unknown_sort_field_is_rejected(client):
    response = client.get("/api/v1/locations/districts", params={"sort": "password"})
    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False and body["status"] == "VALIDATION_ERROR" and body["data"] is None
    assert body["errors"][0]["field"] == "sort"


def test_per_page_and_deep_pagination_are_bounded(client):
    assert client.get("/api/v1/locations/districts", params={"per_page": 101}).status_code == 422
    assert client.get("/api/v1/locations/districts", params={"page": 0}).status_code == 422
    deep = client.get("/api/v1/locations/districts", params={"page": 102, "per_page": 100})
    assert deep.status_code == 422
    assert deep.json()["errors"][0]["field"] == "page"


def test_district_detail_found_missing_and_malformed(client):
    found = client.get(f"/api/v1/locations/districts/{BINH_THANH}")
    assert found.status_code == 200
    assert found.json()["data"]["name"] == "Quận Bình Thạnh"
    assert found.json()["meta"]["pagination"] is None

    missing = client.get("/api/v1/locations/districts/ffffffffffffffff")
    assert missing.status_code == 404
    assert missing.json()["status"] == "NOT_FOUND"

    malformed = client.get("/api/v1/locations/districts/1%20OR%201=1")
    assert malformed.status_code == 422


def test_wards_of_a_district_are_paginated_cards(client):
    response = client.get(f"/api/v1/locations/districts/{QUAN_3}/wards", params={"sort": "name"})
    body = response.json()

    assert response.status_code == 200
    assert [w["name"] for w in body["data"]] == ["Phường 1", "Phường Võ Thị Sáu"]
    assert body["data"][0]["district"] == {"id": QUAN_3, "name": "Quận 3"}
    assert body["meta"]["resource"] == "ward"
    assert client.get("/api/v1/locations/districts/ffffffffffffffff/wards").status_code == 404


def test_resolve_returns_200_for_one_match(client):
    response = client.get("/api/v1/locations/resolve", params={"ward": "phường 25"})

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Phường 25"


def test_resolve_returns_300_with_choices_for_ambiguous_ward(client):
    response = client.get("/api/v1/locations/resolve", params={"ward": "Phường 1"})
    body = response.json()

    assert response.status_code == 300
    assert body["success"] is False and body["status"] == "MULTIPLE_CHOICES"
    assert [c["district"]["name"] for c in body["data"]["choices"]] == ["Quận Bình Thạnh", "Quận 3", "Quận Gò Vấp"]


def test_resolve_narrows_by_district_and_404s_when_nothing_matches(client):
    narrowed = client.get("/api/v1/locations/resolve", params={"ward": "Phường 1", "district_id": QUAN_3})
    assert narrowed.status_code == 200
    assert narrowed.json()["data"]["district"]["id"] == QUAN_3

    assert client.get("/api/v1/locations/resolve", params={"ward": "Phường Không Có"}).status_code == 404
    assert client.get("/api/v1/locations/resolve").status_code == 422


def test_unchanged_resource_returns_304_without_body(client):
    first = client.get("/api/v1/locations/districts")
    etag = first.headers["ETag"]
    assert first.json()["meta"]["cache"]["etag"] == etag

    second = client.get("/api/v1/locations/districts", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["ETag"] == etag
    assert second.headers["X-Request-ID"]

    other_page = client.get("/api/v1/locations/districts?page=2", headers={"If-None-Match": etag})
    assert other_page.status_code == 200


def test_unversioned_path_is_permanently_redirected(client):
    response = client.get("/api/locations/districts?page=2", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["Location"] == "/api/v1/locations/districts?page=2"
    assert response.json()["status"] == "MOVED_PERMANENTLY"
    assert response.json()["links"] == {"location": "/api/v1/locations/districts?page=2"}


def test_unknown_route_uses_the_envelope(client):
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    assert set(response.json()) == ENVELOPE_KEYS
