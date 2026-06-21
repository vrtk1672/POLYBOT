from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.market_neuron_routes import create_market_neuron_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema):
    run_migrations()
    app = FastAPI()
    app.include_router(create_market_neuron_router(connection_factory=DatabaseConnectionFactory()))
    return TestClient(app)


def test_market_neuron_api_endpoints_and_manual_analyze(postgres_test_schema):
    client = _client(postgres_test_schema)
    assert client.get("/market-neuron/health").status_code == 200
    assert client.get("/market-neuron/signals/recent").status_code == 200
    assert client.get("/market-neuron/blocked/recent").status_code == 200
    assert client.get("/market-neuron/top").status_code == 200
    missing_reason = client.post("/market-neuron/analyze", json={"market_id": "mapi"})
    assert missing_reason.status_code == 422
    response = client.post(
        "/market-neuron/analyze",
        json={
            "market_id": "mapi",
            "token_id": "yes",
            "side": "YES",
            "raw_market_snapshot": {"current_price_yes": 0.5, "data_completeness_score": 1.0},
            "raw_orderbook": {"bids": [[0.49, 1000]], "asks": [[0.51, 1000]]},
            "reason": "test",
        },
    )
    assert response.status_code == 200
    assert response.json()["market_id"] == "mapi"
    detail = client.get("/market-neuron/market/mapi").json()
    assert detail["market_signal"]["market_id"] == "mapi"

