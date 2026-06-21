from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.control_center.paper_actionability import PaperActionabilityService
from app.services.source_event_memory import SourceEventMemoryService
from app.services.trade_opportunity_score import score_actionability_item
from source_event_memory_helpers import insert_market, insert_news_event, setup_source_event_tables


def test_linker_endpoints_expose_upgraded_metadata(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-btc", title="Will Bitcoin ETF approval happen?", tags=["crypto", "ETF"], keywords=["bitcoin", "etf", "approval"])
    insert_news_event("event-btc", title="BTC ETF approval odds rise", summary="SEC spot ETF decision expected.", direction="YES", confidence=0.0)

    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    refresh = client.post("/dashboard/api/v2/control/source-event-memory/refresh?force=true&window_hours=72&limit=100")
    summary = client.get("/dashboard/api/v2/control/source-event-memory")
    diagnostics = client.get("/dashboard/api/v2/control/source-event-memory/linker-diagnostics")

    assert refresh.status_code == 200
    assert summary.status_code == 200
    assert diagnostics.status_code == 200
    counts = summary.json()["counts"]
    assert "revalidation_eligible_link_count" in counts
    assert "watch_only_link_count" in counts
    assert "token_side_unknown_count" in counts
    assert counts["top_aliases_matched"]
    assert diagnostics.json()["result"]["semantic_system_available"] is False

    source_event_id = summary.json()["sample_top_linked_events"][0]["source_event_id"]
    recall = client.get(f"/dashboard/api/v2/control/source-event-memory/recall?source_event_id={source_event_id}")
    by_market = client.get("/dashboard/api/v2/control/source-event-memory/by-market?market_id=market-btc")

    assert recall.status_code == 200
    link = recall.json()["result"]["linked_markets"][0]
    assert "matched_aliases_json" in link
    assert "confidence_components_json" in link
    assert "token_side_resolution_state" in link
    assert "candidate_actionability_hint" in link
    assert "guardrail_reason" in link
    assert by_market.status_code == 200
    assert by_market.json()["result"]["events"][0]["candidate_actionability_hint"] in {"REVALIDATION_ELIGIBLE", "WATCH_ONLY"}


def test_score_actionability_and_trace_expose_upgraded_recall_metadata(postgres_test_schema, monkeypatch) -> None:
    setup_source_event_tables()
    insert_market("market-surface-25", title="Will Ethereum ETF approval happen?", tags=["crypto", "ETF"], keywords=["ethereum", "etf", "approval"])
    insert_news_event("event-surface-25", title="ETH ETF approval decision nears", summary="SEC ruling expected.", direction="YES", confidence=0.0)
    SourceEventMemoryService().refresh_events(force=True)

    fields = PaperActionabilityService()._source_event_memory_fields(market_id="market-surface-25")
    assert fields["recent_source_event_count"] == 1
    assert fields["recall_link_state"] in {"DIRECT_LINK", "LIKELY_LINK", "WEAK_LINK", "CONTEXT_ONLY"}
    assert fields["event_link_actionability_hint"] in {"REVALIDATION_ELIGIBLE", "WATCH_ONLY", "CONTEXT_ONLY"}
    assert fields["token_side_resolution_state"]

    score = score_actionability_item(
        {
            "candidate_id": "candidate-surface",
            "market_id": "market-surface-25",
            "side": "YES",
            "token_id": "token",
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
    assert score["event_link_actionability_hint"] == fields["event_link_actionability_hint"]
    assert score["token_side_resolution_state"] == fields["token_side_resolution_state"]

    class _SourceRefresh:
        def __init__(self, *args, **kwargs):
            pass

        def get_status(self):
            return {"latest_source_refresh_cycle_id": "cycle-1", "source_refresh_orchestrator_state": "ACTIVE"}

    class _Edge:
        def __init__(self, *args, **kwargs):
            pass

        def list_edges(self, *args, **kwargs):
            return {"items": [{"candidate_id": "candidate-surface", "market_id": "market-surface-25", "side": "YES", "token_id": "token"}]}

    class _Actionability:
        def __init__(self, *args, **kwargs):
            pass

        def list_actionability(self, *args, **kwargs):
            return {"items": [{"candidate_id": "candidate-surface", **fields}]}

    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceRefreshStatusService", _SourceRefresh)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceBackedEdgeControlService", _Edge)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.PaperActionabilityService", _Actionability)

    trace = DecisionPropagationTraceService().get_trace(limit=1)
    assert trace["traces"][0]["event_link_actionability_hint"] == fields["event_link_actionability_hint"]
    assert trace["traces"][0]["token_side_resolution_state"] == fields["token_side_resolution_state"]


def test_refresh_does_not_create_execution_or_paper_artifacts(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-safe-25", title="Will safe linker stay data only?", keywords=["safe", "linker"])
    insert_news_event("event-safe-25", title="Safe linker data update", market_id="market-safe-25", confidence=0.9)

    result = SourceEventMemoryService().refresh_events(force=True)

    assert result["status"] == "OK"
    assert result["metadata"]["execution_candidates_created"] is False
    assert result["metadata"]["targeted_revalidation_triggered"] is False
