from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_live_and_uniform_validation_errors() -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "test-request"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"
    invalid = client.post("/api/v1/demo/tasks", json={"document": {"type": "wrong"}})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["request_id"] == invalid.headers["X-Request-ID"]
    assert client.get("/api/v1/unknown").json()["error"]["code"] == "http_404"
