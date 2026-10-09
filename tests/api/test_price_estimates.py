"""POST /api/v1/price-estimates and GET /api/v1/price-estimates/model."""

from tests.api.conftest import BINH_THANH, GO_VAP, QUAN_3, WARD_25


def test_estimate_for_a_ward_returns_range_market_and_disclaimer(client, price_model):
    response = client.post("/api/v1/price-estimates", json={"area_m2": 25, "district_id": BINH_THANH, "ward_id": WARD_25})
    body = response.json()

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = body["data"]
    assert data["estimate"] == 4000000
    assert data["range"] == {"low": 3200000, "high": 4800000, "coverage": 0.5}
    assert data["inputs_used"] == {
        "area_m2": 25.0, "district": "Quận Bình Thạnh", "ward": "Phường 25",
        "source_policy": "development_modal_source:phongtro123",
    }
    assert data["market"]["scope"] == "ward" and data["market"]["median"] == 4200000
    assert data["warnings"] == []
    assert data["model"] == {"model_id": "roombeacon-price-lgbm-f4-raw-test", "readiness": "experimental"}
    assert "tham khảo" in data["disclaimer"]
    assert price_model.inputs[-1].source_code is None


def test_estimate_without_ward_uses_the_district(client):
    data = client.post("/api/v1/price-estimates", json={"area_m2": 40, "district_id": GO_VAP}).json()["data"]

    assert data["inputs_used"]["ward"] is None
    assert data["market"]["scope"] == "district"


def test_estimate_warnings_cover_area_price_and_unknown_locations(client):
    small = client.post("/api/v1/price-estimates", json={"area_m2": 10, "district_id": BINH_THANH}).json()["data"]
    big = client.post("/api/v1/price-estimates", json={"area_m2": 60, "district_id": BINH_THANH}).json()["data"]
    unknown_ward = client.post(
        "/api/v1/price-estimates", json={"area_m2": 25, "district_id": BINH_THANH, "ward_id": "aa00000000000002"}
    ).json()["data"]

    assert {"area_outside_typical_range", "low_price_segment_less_accurate"} <= set(small["warnings"])
    assert {"area_outside_typical_range", "high_price_segment_less_accurate"} <= set(big["warnings"])
    assert "ward_unknown_to_model" in unknown_ward["warnings"]


def test_estimate_validation(client):
    def post(payload):
        return client.post("/api/v1/price-estimates", json=payload)

    assert post({"area_m2": 2, "district_id": BINH_THANH}).status_code == 422
    assert post({"area_m2": 25}).status_code == 422
    assert post({"area_m2": 25, "district_id": BINH_THANH, "price": 1}).status_code == 422
    assert post({"area_m2": 25, "district_id": "ffffffffffffffff"}).status_code == 404
    mismatch = post({"area_m2": 25, "district_id": QUAN_3, "ward_id": WARD_25})
    assert mismatch.status_code == 422 and mismatch.json()["errors"][0]["field"] == "ward_id"
    assert client.post("/api/v1/price-estimates", content="not json", headers={"Content-Type": "application/json"}).status_code == 422


def test_model_info_and_outage(client, price_model):
    info = client.get("/api/v1/price-estimates/model").json()["data"]

    assert info["model_id"] == "roombeacon-price-lgbm-f4-raw-test"
    assert info["test_metrics"] == {"mae": 916127, "median_ae": 623718, "r2": 0.205}
    assert info["reliable_price_range"] == {"low": 3000000, "high": 5500000}
    assert info["readiness"] == "experimental"

    price_model.unavailable = True
    outage = client.post("/api/v1/price-estimates", json={"area_m2": 25, "district_id": BINH_THANH})
    assert outage.status_code == 503
    assert outage.headers["Retry-After"] == "30"


def test_estimates_require_an_api_key(settings, repository):
    from fastapi.testclient import TestClient
    from tests.api.conftest import build_app

    with TestClient(build_app(settings, repository)) as anonymous:
        assert anonymous.post("/api/v1/price-estimates", json={"area_m2": 25, "district_id": BINH_THANH}).status_code == 401
