"""District and ward cards carry a cover image from their latest listing with photos."""

from fastapi.testclient import TestClient

from tests.api.conftest import API_KEY, BINH_THANH, QUAN_3, WARD_25, build_app, make_settings


COVER = {"url": "/api/v1/listings/101/images/1", "listing_id": "101"}


def test_district_cards_have_a_cover_image_when_one_exists(client):
    cards = {c["id"]: c for c in client.get("/api/v1/locations/districts").json()["data"]}

    assert cards[BINH_THANH]["cover_image"] == COVER
    assert cards[QUAN_3]["cover_image"] is None
    assert client.get(f"/api/v1/locations/districts/{BINH_THANH}").json()["data"]["cover_image"] == COVER


def test_ward_cards_have_a_cover_image(client):
    wards = {w["id"]: w for w in client.get(f"/api/v1/locations/districts/{BINH_THANH}/wards").json()["data"]}

    assert wards[WARD_25]["cover_image"] == COVER
    assert wards["aa00000000000002"]["cover_image"] is None


def test_cover_images_degrade_to_null(client, images):
    images.unavailable = True
    response = client.get("/api/v1/locations/districts")

    assert response.status_code == 200
    assert all(card["cover_image"] is None for card in response.json()["data"])


def test_cover_images_are_null_when_images_are_disabled(repository):
    with TestClient(build_app(make_settings(images_enabled=False), repository), headers={"X-API-Key": API_KEY}) as client:
        cards = client.get("/api/v1/locations/districts").json()["data"]

    assert all(card["cover_image"] is None for card in cards)
