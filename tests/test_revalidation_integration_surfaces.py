from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.control_center.paper_actionability import PaperActionabilityService
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from app.services.trade_opportunity_score import score_actionability_item
from targeted_revalidation_helpers import insert_event_link, insert_fresh_orderbook, insert_market, setup_revalidation_tables


def test_targeted_revalidation_endpoints_expose_summary_by_market_and_by_event(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-endpoint")
    insert_event_link("event-endpoint", "market-endpoint")
    insert_fresh_orderbook("market-endpoint")

    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    refresh = client.post("/dashboard/api/v2/control/targeted-market-revalidation/refresh?force=true&limit=10")
    summary = client.get("/dashboard/api/v2/control/targeted-market-revalidation")
    by_market = client.get("/dashboard/api/v2/control/targeted-market-revalidation/by-market?market_id=market-endpoint")
    by_event = client.get("/dashboard/api/v2/control/targeted-market-revalidation/by-event?source_event_id=event-endpoint")

    assert refresh.status_code == 200
    assert summary.status_code == 200
    assert by_market.status_code == 200
    assert by_event.status_code == 200
    counts = summary.json()["counts"]
    assert counts["eligible_links_seen"] >= 1
    assert counts["revalidated_count"] >= 1
    assert by_market.json()["result"]["results"][0]["market_id"] == "market-endpoint"
    assert by_event.json()["result"]["results"][0]["source_event_id"] == "event-endpoint"


def test_score_actionability_and_trace_expose_revalidation_metadata(postgres_test_schema, monkeypatch) -> None:
    setup_revalidation_tables()
    insert_market("market-surface-reval")
    insert_event_link("event-surface-reval", "market-surface-reval")
    insert_fresh_orderbook("market-surface-reval")
    TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)

    fields = PaperActionabilityService()._targeted_revalidation_fields(market_id="market-surface-reval")
    assert fields["latest_targeted_revalidation_state"] == "REVALIDATED"
    assert fields["orderbook_refresh_state_from_revalidation"] == "FRESH"

    score = score_actionability_item(
        {
            "candidate_id": "candidate-reval",
            "market_id": "market-surface-reval",
            "side": "YES",
            "token_id": "market-surface-reval-yes",
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
            **fields,
        }
    )
    assert score["latest_targeted_revalidation_state"] == "REVALIDATED"
    assert score["orderbook_refresh_state_from_revalidation"] == "FRESH"

    class _SourceRefresh:
        def __init__(self, *args, **kwargs):
            pass

        def get_status(self):
            return {"latest_source_refresh_cycle_id": "cycle-1", "source_refresh_orchestrator_state": "ACTIVE"}

    class _Edge:
        def __init__(self, *args, **kwargs):
            pass

        def list_edges(self, *args, **kwargs):
            return {"items": [{"candidate_id": "candidate-reval", "market_id": "market-surface-reval", "side": "YES", "token_id": "market-surface-reval-yes"}]}

    class _Actionability:
        def __init__(self, *args, **kwargs):
            pass

        def list_actionability(self, *args, **kwargs):
            return {"items": [{"candidate_id": "candidate-reval", **fields}]}

    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceRefreshStatusService", _SourceRefresh)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceBackedEdgeControlService", _Edge)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.PaperActionabilityService", _Actionability)

    trace = DecisionPropagationTraceService().get_trace(limit=1)
    assert trace["traces"][0]["revalidation_state"] == "REVALIDATED"
    assert trace["traces"][0]["candidate_generation_later_eligible"] is True
