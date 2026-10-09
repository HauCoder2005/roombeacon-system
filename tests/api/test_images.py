"""Listing images served from MinIO through the API (feature-flagged)."""

from fastapi.testclient import TestClient

from tests.api.conftest import API_KEY, JPEG, build_app, make_settings


def test_cards_carry_an_image_summary(client):
    cards = {c["id"]: c for c in client.get("/api/v1/listings", params={"per_page": 100}).json()["data"]}

    assert cards["101"]["images"] == {"count": 2, "cover": "/api/v1/listings/101/images/1"}
    assert cards["103"]["images"] == {"count": 0, "cover": None}


def test_image_list_and_bytes(client):
    listing = client.get("/api/v1/listings/101/images").json()
    assert listing["meta"]["resource"] == "image"
    assert listing["data"] == [
        {"position": 1, "url": "/api/v1/listings/101/images/1"},
        {"position": 2, "url": "/api/v1/listings/101/images/2"},
    ]

    image = client.get("/api/v1/listings/101/images/2")
    assert image.status_code == 200
    assert image.content == JPEG
    assert image.headers["Content-Type"] == "image/jpeg"
    assert image.headers["ETag"] == '"etag2"'
    assert "max-age=86400" in image.headers["Cache-Control"]
    assert image.headers["X-Content-Type-Options"] == "nosniff"


def test_missing_wrong_type_and_malformed_images(client):
    assert client.get("/api/v1/listings/101/images/9").status_code == 404
    assert client.get("/api/v1/listings/102/images/1").status_code == 404  # stored object is not an image
    assert client.get("/api/v1/listings/999999/images").status_code == 404
    assert client.get("/api/v1/listings/101/images/x").status_code == 422
    assert client.get("/api/v1/listings/101/images/1", headers={"X-API-Key": "wrong"}).status_code == 401


def test_store_outage_degrades_cards_but_fails_image_routes(client, images):
    images.unavailable = True

    card = client.get("/api/v1/listings/101").json()["data"]
    assert card["images"] is None
    assert client.get("/api/v1/listings/101/images").status_code == 503


def test_images_disabled_by_flag(repository):
    app = build_app(make_settings(images_enabled=False), repository)
    with TestClient(app, headers={"X-API-Key": API_KEY}) as client:
        assert client.get("/api/v1/listings/101").json()["data"]["images"] is None
        assert client.get("/api/v1/listings/101/images").status_code == 404
        assert client.get("/api/v1/listings/101/images/1").status_code == 404


def test_images_have_their_own_larger_rate_limit(repository):
    app = build_app(make_settings(rate_limit_per_minute=2), repository)
    with TestClient(app, headers={"X-API-Key": API_KEY}) as client:
        image_codes = [client.get("/api/v1/listings/101/images/1").status_code for _ in range(5)]
        api_codes = [client.get("/api/v1/listings").status_code for _ in range(3)]

    assert image_codes == [200] * 5
    assert api_codes == [200, 200, 429]
