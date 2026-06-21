from fastapi.testclient import TestClient

from app.main import create_app


def test_whale_api_read_endpoints_and_validation():
    client = TestClient(create_app())
    assert client.get("/whales").status_code == 200
    assert client.get("/whales/events/recent").status_code == 200
    assert client.get("/whales/scores/top").status_code == 200
    assert client.get("/whales/market/m1").status_code == 200
    assert client.get("/whales/nobody").status_code == 200
    assert client.post("/whales/scan", json={"limit_per_source": 1}).status_code == 422
    assert client.post("/whales/manual", json={"source_id": "manual", "action_type": "BUY", "size_usd": 12000}).status_code == 422
    response = client.post("/whales/manual", json={"source_id": "manual", "whale_id": "api_w", "action_type": "BUY", "size_usd": 12000, "reason": "test"})
    assert response.status_code in {200, 409}

