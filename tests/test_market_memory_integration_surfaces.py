from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.control_center.paper_actionability import PaperActionabilityService
from app.services.trade_opportunity_score import score_actionability_item
from market_memory_helpers import insert_market, setup_market_tables


def test_market_universe_memory_endpoint_returns_counts_and_samples(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("endpoint-m")
    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    refresh = client.post("/dashboard/api/v2/control/market-universe-memory/refresh?force=true")
    summary = client.get("/dashboard/api/v2/control/market-universe-memory")

    assert refresh.status_code == 200
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["counts"]["total_markets"] >= 1
    assert "top_high_priority_markets" in payload


def test_actionability_market_memory_lookup_fields(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("field-m", yes_token_id="field-yes")
    from app.services.market_universe_memory import MarketUniverseMemoryService

    MarketUniverseMemoryService().refresh_universe(force=True)
    fields = PaperActionabilityService()._market_memory_fields(market_id="field-m", token_id="field-yes")
    assert fields["market_memory_status"] == "ACTIVE"
    assert fields["token_verification_state"] == "TOKENS_VERIFIED"


def test_score_exposes_market_memory_fields() -> None:
    item = {
        "candidate_id": "c",
        "market_id": "m",
        "side": "YES",
        "token_id": "t",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "risk_gate_state": "RISK_REVIEW",
        "exit_gate_state": "EXIT_READY",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "joined_trade_thesis": {"status": "THESIS_SUPPORTED"},
        "thesis_id": "thesis",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48,
        "risk_capital_gate_trace": {"risk_capital_policy_state": "CAPITAL_WATCH"},
        "market_memory_id": "market_memory_abc",
        "market_memory_status": "ACTIVE",
        "market_memory_freshness": "FRESH",
        "market_identity_verification_state": "VERIFIED",
        "token_verification_state": "TOKENS_VERIFIED",
    }

    score = score_actionability_item(item)

    assert score["market_memory_id"] == "market_memory_abc"
    assert score["market_memory_status"] == "ACTIVE"
    assert score["token_verification_state"] == "TOKENS_VERIFIED"


def test_decision_trace_exposes_market_memory_fields(monkeypatch) -> None:
    class _SourceRefresh:
        def __init__(self, *args, **kwargs):
            pass

        def get_status(self):
            return {"latest_source_refresh_cycle_id": "cycle-1", "source_refresh_orchestrator_state": "ACTIVE"}

    class _Edge:
        def __init__(self, *args, **kwargs):
            pass

        def list_edges(self, *args, **kwargs):
            return {"items": [{"candidate_id": "c", "market_id": "m", "side": "YES", "token_id": "t", "source_refresh_cycle_id": "cycle-1"}]}

    class _Actionability:
        def __init__(self, *args, **kwargs):
            pass

        def list_actionability(self, *args, **kwargs):
            return {
                "items": [
                    {
                        "candidate_id": "c",
                        "market_memory_id": "market_memory_abc",
                        "market_memory_status": "ACTIVE",
                        "market_memory_freshness": "FRESH",
                        "market_identity_verification_state": "VERIFIED",
                        "token_verification_state": "TOKENS_VERIFIED",
                    }
                ]
            }

    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceRefreshStatusService", _SourceRefresh)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceBackedEdgeControlService", _Edge)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.PaperActionabilityService", _Actionability)

    trace = DecisionPropagationTraceService().get_trace(limit=1)

    assert trace["traces"][0]["market_memory_id"] == "market_memory_abc"
    assert trace["traces"][0]["token_verification_state"] == "TOKENS_VERIFIED"
