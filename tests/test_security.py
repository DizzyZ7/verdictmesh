import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from verdictmesh.config import Settings
from verdictmesh.security import install_security_middleware

VALID_KEY = "a" * 32


def make_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_security_middleware(app, settings)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/private")
    def private() -> dict[str, str]:
        return {"status": "protected"}

    return app


def test_authentication_is_optional_in_development() -> None:
    client = TestClient(make_app(Settings(app_env="development")))

    response = client.get("/private")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_protected_route_rejects_missing_and_invalid_keys() -> None:
    settings = Settings(app_env="test", operator_api_key=VALID_KEY)
    client = TestClient(make_app(settings))

    missing = client.get("/private")
    invalid = client.get("/private", headers={"X-API-Key": "wrong-key"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "ApiKey"


def test_protected_route_accepts_configured_key_and_preserves_request_id() -> None:
    settings = Settings(app_env="test", operator_api_key=VALID_KEY)
    client = TestClient(make_app(settings))

    response = client.get(
        "/private",
        headers={"X-API-Key": VALID_KEY, "X-Request-ID": "test-request-id"},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request-id"


def test_health_and_docs_remain_public() -> None:
    settings = Settings(app_env="test", operator_api_key=VALID_KEY)
    client = TestClient(make_app(settings))

    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_protected_environments_require_operator_key(environment: str) -> None:
    with pytest.raises(ValidationError, match="OPERATOR_API_KEY is required"):
        Settings(app_env=environment)


def test_operator_key_has_minimum_length() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(app_env="development", operator_api_key="too-short")
