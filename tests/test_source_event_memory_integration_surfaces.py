from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.control_center.paper_actionability import PaperActionabilityService
from app.services.source_event_memory import SourceEventMemoryService
from app.services.trade_opportunity_score import score_actionability_item
from source_event_memory_helpers import insert_market, insert_news_event, setup_source_event_tables


def test_source_event_memory_endpoints_return_counts_and_samples(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-endpoint", title="Will endpoint source event link?", keywords=["endpoint", "source"])
    insert_news_event("event-endpoint", title="Endpoint source event link", market_id="market-endpoint", confidence=0.9)

    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    refresh = client.post("/dashboard/api/v2/control/source-event-memory/refresh?force=true&window_hours=72&limit=100")
    summary = client.get("/dashboard/api/v2/control/source-event-memory")

    assert refresh.status_code == 200
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["counts"]["total_source_events"] >= 1
    assert payload["counts"]["link_type_counts"]["DIRECT_LINK"] >= 1
    assert payload["sample_direct_links"]


def test_recall_and_by_market_endpoints_expose_link_truth(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-recall", title="Will recall endpoint work?", keywords=["recall", "endpoint"])
    insert_news_event("event-recall", title="Recall endpoint work", market_id="market-recall", direction="YES", confidence=0.9)
    SourceEventMemoryService().refresh_events(force=True)
    service = SourceEventMemoryService()
    summary = service.summary()
    source_event_id = summary["sample_top_linked_events"][0]["source_event_id"]

    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    recall = client.get(f"/dashboard/api/v2/control/source-event-memory/recall?source_event_id={source_event_id}")
    by_market = client.get("/dashboard/api/v2/control/source-event-memory/by-market?market_id=market-recall")

    assert recall.status_code == 200
    assert recall.json()["result"]["linked_markets"][0]["market_id"] == "market-recall"
    assert by_market.status_code == 200
    assert by_market.json()["result"]["events"][0]["linked_market_id"] == "market-recall"


def test_actionability_score_and_trace_expose_source_event_memory_fields(postgres_test_schema, monkeypatch) -> None:
    setup_source_event_tables()
    insert_market("market-surface", title="Will surface fields appear?", keywords=["surface", "fields"])
    insert_news_event("event-surface", title="Surface fields appear", market_id="market-surface", direction="YES", confidence=0.9)
    SourceEventMemoryService().refresh_events(force=True)

    fields = PaperActionabilityService()._source_event_memory_fields(market_id="market-surface")
    assert fields["recent_source_event_count"] == 1
    assert fields["strongest_event_link_type"] == "DIRECT_LINK"

    score = score_actionability_item(
        {
            "candidate_id": "c",
            "market_id": "market-surface",
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
            **fields,
        }
    )
    assert score["recent_source_event_count"] == 1
    assert score["strongest_event_link_type"] == "DIRECT_LINK"

    class _SourceRefresh:
        def __init__(self, *args, **kwargs):
            pass

        def get_status(self):
            return {"latest_source_refresh_cycle_id": "cycle-1", "source_refresh_orchestrator_state": "ACTIVE"}

    class _Edge:
        def __init__(self, *args, **kwargs):
            pass

        def list_edges(self, *args, **kwargs):
            return {"items": [{"candidate_id": "c", "market_id": "market-surface", "side": "YES", "token_id": "t"}]}

    class _Actionability:
        def __init__(self, *args, **kwargs):
            pass

        def list_actionability(self, *args, **kwargs):
            return {"items": [{"candidate_id": "c", **fields}]}

    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceRefreshStatusService", _SourceRefresh)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceBackedEdgeControlService", _Edge)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.PaperActionabilityService", _Actionability)

    trace = DecisionPropagationTraceService().get_trace(limit=1)
    assert trace["traces"][0]["recent_source_event_count"] == 1
    assert trace["traces"][0]["strongest_event_link_type"] == "DIRECT_LINK"
