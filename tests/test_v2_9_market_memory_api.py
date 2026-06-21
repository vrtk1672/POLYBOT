from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.market_memory_routes import create_market_memory_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.market_neuron.service import MarketNeuronService


def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_market_memory_router(connection_factory=factory))
    return TestClient(app), factory


def test_market_memory_api_endpoints_and_rebuild(postgres_test_schema):
    client, factory = _client(postgres_test_schema)
    MarketNeuronService(connection_factory=factory).analyze_market(
        "mapi",
        token_id="yes",
        side="YES",
        raw_market_snapshot={"current_price_yes": 0.5, "data_completeness_score": 1.0},
        raw_orderbook={"bids": [[0.49, 1000]], "asks": [[0.51, 1000]]},
    )

    assert client.get("/market-memory/health").status_code == 200
    for path in (
        "/market-memory/recent",
        "/market-memory/engines",
        "/market-memory/sources",
        "/market-memory/whales",
        "/market-memory/slippage",
        "/market-memory/rules-risk",
        "/market-memory/no-trade",
    ):
        assert client.get(path).status_code == 200

    dry = client.post("/market-memory/rebuild", json={"market_id": "mapi", "dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["written"] is False

    write = client.post("/market-memory/rebuild", json={"market_id": "mapi", "dry_run": False})
    assert write.status_code == 200
    assert write.json()["written"] is True
    assert client.get("/market-memory/market/mapi").json()["market_memory"]["market_id"] == "mapi"
    assert client.get("/market-memory/family/UNKNOWN").status_code == 200
