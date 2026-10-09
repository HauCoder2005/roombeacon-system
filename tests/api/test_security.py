"""Auth, rate limiting, headers, error hygiene and settings for the API."""

import hashlib
import logging

import pytest
from fastapi.testclient import TestClient

from roombeacon_api.config import ApiConfigError, ApiSettings, Secret
from tests.api.conftest import API_KEY, build_app, make_settings


def _client(settings, repository, **headers) -> TestClient:
    return TestClient(build_app(settings, repository), headers=headers, raise_server_exceptions=False)


def test_missing_or_wrong_api_key_is_401_without_hinting_which(settings, repository):
    with _client(settings, repository) as anonymous:
        missing = anonymous.get("/api/v1/locations/districts")
        wrong = anonymous.get("/api/v1/locations/districts", headers={"X-API-Key": "nope"})

    for response in (missing, wrong):
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "ApiKey"
        assert response.json()["status"] == "UNAUTHORIZED"
    assert missing.json()["message"] == wrong.json()["message"]
    assert repository.calls == []


def test_health_is_public_and_ready_checks_the_warehouse(settings, repository):
    with _client(settings, repository) as anonymous:
        assert anonymous.get("/health").status_code == 200
        assert anonymous.get("/ready").status_code == 200
        repository.unavailable = True
        not_ready = anonymous.get("/ready")

    assert not_ready.status_code == 503
    assert not_ready.headers["Retry-After"] == "30"


def test_security_headers_on_every_response(client):
    for response in (client.get("/api/v1/locations/districts"), client.get("/api/v1/nope")):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert "server" not in {k.lower() for k in response.headers}


def test_rate_limit_returns_429_with_retry_after(repository):
    with _client(make_settings(rate_limit_per_minute=3), repository, **{"X-API-Key": API_KEY}) as limited:
        statuses = [limited.get("/api/v1/locations/districts") for _ in range(4)]

    assert [r.status_code for r in statuses] == [200, 200, 200, 429]
    assert statuses[0].headers["X-RateLimit-Limit"] == "3"
    assert statuses[2].headers["X-RateLimit-Remaining"] == "0"
    blocked = statuses[3]
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["status"] == "RATE_LIMITED"


def test_rate_limit_also_throttles_anonymous_key_guessing(repository):
    with _client(make_settings(rate_limit_per_minute=2), repository) as anonymous:
        statuses = [anonymous.get("/api/v1/locations/districts", headers={"X-API-Key": f"guess-{i}"}).status_code for i in range(3)]

    assert statuses == [401, 401, 429]


def test_untrusted_host_is_rejected(settings, repository):
    with TestClient(build_app(settings, repository), base_url="http://evil.example") as other:
        assert other.get("/health").status_code == 400


def test_unexpected_error_is_500_without_leaking_details(client, repository, caplog):
    repository.explode = RuntimeError("dsn=clickhouse://admin:hunter2@db")
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/v1/locations/districts")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "INTERNAL_ERROR" and body["data"] is None
    assert "hunter2" not in response.text and "Traceback" not in response.text
    assert "hunter2" not in caplog.text
    assert body["meta"]["request_id"] in caplog.text


def test_dependency_outage_is_503(client, repository):
    repository.unavailable = True
    response = client.get("/api/v1/locations/districts")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert response.json()["status"] == "SERVICE_UNAVAILABLE"


def test_request_id_is_echoed_only_when_safe(client):
    safe = client.get("/health", headers={"X-Request-ID": "abc-123_DEF"})
    unsafe = client.get("/health", headers={"X-Request-ID": "x" * 200})

    assert safe.headers["X-Request-ID"] == "abc-123_DEF"
    assert unsafe.headers["X-Request-ID"] != "x" * 200
    assert len(unsafe.headers["X-Request-ID"]) <= 64


def test_docs_are_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_settings_from_env_require_keys_and_hide_secrets():
    env = {
        "API_KEY_SHA256": hashlib.sha256(b"k").hexdigest(),
        "WAREHOUSE_READER_USER": "reader",
        "WAREHOUSE_READER_PASSWORD": "s3cret-value",
    }
    settings = ApiSettings.from_env(env)

    assert settings.auth_enabled and settings.rate_limit_per_minute == 60
    assert settings.clickhouse.host == "127.0.0.1" and settings.clickhouse.database == "roombeacon_dw"
    assert "s3cret-value" not in repr(settings)
    assert repr(Secret("x")) == "Secret('***')"

    with pytest.raises(ApiConfigError):
        ApiSettings.from_env({**env, "API_KEY_SHA256": ""})
    with pytest.raises(ApiConfigError):
        ApiSettings.from_env({**env, "API_KEY_SHA256": "not-a-hash"})
    with pytest.raises(ApiConfigError):
        ApiSettings.from_env({**env, "WAREHOUSE_READER_PASSWORD": ""})
    with pytest.raises(ApiConfigError):
        ApiSettings.from_env({**env, "API_RATE_LIMIT_PER_MINUTE": "0"})


def test_docs_when_enabled_offer_an_api_key_authorize_button(repository):
    with _client(make_settings(docs_enabled=True), repository) as anonymous:
        docs = anonymous.get("/docs")
        schema = anonymous.get("/openapi.json").json()

    assert docs.status_code == 200
    assert schema["components"]["securitySchemes"]["ApiKeyAuth"] == {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    assert {"ApiKeyAuth": []} in schema["paths"]["/api/v1/locations/districts"]["get"]["security"]
