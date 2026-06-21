from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.social_routes import create_social_router
from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.source_registry import SocialSourceRegistry
from fastapi import FastAPI


def test_social_api_endpoints_and_manual_processing(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL))
    MarketRegistry().upsert_market(MarketRegistry().normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    app = FastAPI()
    app.include_router(create_social_router(connection_factory=factory))
    client = TestClient(app)
    assert client.post("/social/manual", json={"source_id": "manual", "platform": "manual", "reason": "x"}).status_code == 422
    response = client.post("/social/manual", json={"source_id": "manual", "platform": "manual", "text": "BTC is moving fast #BTC", "category": "crypto", "reason": "test"})
    assert response.status_code == 200
    assert client.get("/social/recent").json()["count"] >= 1
    assert client.get("/social/sources").json()["count"] >= 1
    assert client.get("/social/hype/top").status_code == 200
    assert client.get("/social/narratives").status_code == 200
    assert client.get("/social/market/btc-market").status_code == 200
    assert client.post("/social/collect", json={"limit_per_source": 1}).status_code == 422
