from fastapi.testclient import TestClient

from app import __version__
from app.main import app

client = TestClient(app)


def test_health_returns_200_with_json_status_payload() -> None:
    """Phase 1, item 1.7: GET /health returns 200 with a JSON status payload."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "tawi-backend"
    assert payload["version"] == __version__
    assert payload["environment"] in {"local", "ci", "staging", "production"}


def test_health_is_stable_across_repeated_calls() -> None:
    payloads = [client.get("/health").json() for _ in range(5)]

    assert all(payload == payloads[0] for payload in payloads)


def test_unknown_route_returns_404() -> None:
    assert client.get("/does-not-exist").status_code == 404
