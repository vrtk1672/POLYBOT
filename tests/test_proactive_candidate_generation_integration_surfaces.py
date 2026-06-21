from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_candidate_generation import ProactiveCandidateGenerationService
from proactive_candidate_generation_helpers import setup_proactive_seed_source
from starlette.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


def test_proactive_candidate_generation_endpoints_expose_summary_and_lookups(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-api", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")
    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)
    with DatabaseConnectionFactory().connect() as conn:
        seed_id = conn.execute("SELECT proactive_candidate_seed_id FROM proactive_candidate_seeds WHERE market_id='market-stage4-api'").fetchone()["proactive_candidate_seed_id"]
    client = _client()

    summary = client.get("/dashboard/api/v2/control/proactive-candidate-generation").json()
    by_market = client.get("/dashboard/api/v2/control/proactive-candidate-generation/by-market", params={"market_id": "market-stage4-api"}).json()
    by_event = client.get("/dashboard/api/v2/control/proactive-candidate-generation/by-event", params={"source_event_id": "event-market-stage4-api"}).json()
    by_seed = client.get("/dashboard/api/v2/control/proactive-candidate-generation/by-seed", params={"proactive_candidate_seed_id": seed_id}).json()

    assert summary["data"]["counts"]["generated_count"] >= 1
    assert by_market["data"]["result"]["results"][0]["market_id"] == "market-stage4-api"
    assert by_event["data"]["result"]["results"][0]["source_event_id"] == "event-market-stage4-api"
    assert by_seed["data"]["result"]["seed"]["proactive_candidate_seed_id"] == seed_id


def test_market_and_revalidation_surfaces_expose_seed_metadata(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-surfaces", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")
    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)
    client = _client()

    market = client.get("/dashboard/api/v2/control/market-universe-memory").json()
    revalidation = client.get("/dashboard/api/v2/control/targeted-market-revalidation").json()

    market_items = market["data"].get("top_high_priority_markets") or market["data"].get("sample_top_high_priority_markets") or market["data"].get("items") or []
    assert any("proactive_candidate_seed_count" in item for item in market_items)
    assert "generated_seed_count" in revalidation["data"]["counts"]


def test_paper_actionability_and_decision_trace_include_safe_seed_fields(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-fields", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")
    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    service = ProactiveCandidateGenerationService()
    fields = service.fields_for_market(market_id="market-stage4-fields")

    assert fields["research_only"] is True
    assert fields["seed_execution_allowed"] is False
    assert fields["seed_paper_allowed"] is False
    assert fields["mesh_handoff_state"] == "SKIPPED"
