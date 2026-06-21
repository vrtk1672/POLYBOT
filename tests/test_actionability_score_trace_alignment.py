from __future__ import annotations

from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.services.trade_opportunity_score import attach_opportunity_score
from tests_support_strict_actionability import qualified_actionability_item


def test_score_exposes_same_selected_event_and_orderbook_as_actionability() -> None:
    item = attach_opportunity_score(
        qualified_actionability_item(
            event_id="event-1",
            selected_candidate_event_id="event-1",
            selected_orderbook_snapshot_id="ob-1",
            candidate_trusted_orderbook_state="TRUSTED_FRESH_FOR_CANDIDATE",
        )
    )

    score = item["opportunity_score"]
    assert score["selected_candidate_event_id"] == item["selected_candidate_event_id"]
    assert score["selected_orderbook_snapshot_id"] == item["selected_orderbook_snapshot_id"]
    assert score["candidate_event_scope"] == item["candidate_event_scope"]
    assert score["candidate_event_link_state"] == item["candidate_event_link_state"]
    assert score["orderbook_freshness_state"] == item["candidate_trusted_orderbook_state"]


def test_decision_trace_carries_selected_actionability_evidence(monkeypatch) -> None:
    edge = {
        "candidate_id": "candidate-1",
        "market_id": "market-1",
        "side": "YES",
        "token_id": "token-yes",
        "source_refresh_cycle_id": "cycle-1",
        "edge_state": "EDGE_SUPPORTED",
    }
    action = attach_opportunity_score(
        qualified_actionability_item(
            event_id="event-1",
            selected_candidate_event_id="event-1",
            correlation_id="corr-1",
            selected_orderbook_snapshot_id="ob-1",
            orderbook_snapshot_id="ob-1",
        )
    )

    class _SourceRefresh:
        def __init__(self, **_kwargs):
            pass

        def get_status(self):
            return {"latest_source_refresh_cycle_id": "cycle-1", "source_refresh_orchestrator_state": "ACTIVE"}

    class _Edges:
        def __init__(self, **_kwargs):
            pass

        def list_edges(self, **_kwargs):
            return {"items": [edge]}

    class _Actionability:
        def __init__(self, **_kwargs):
            pass

        def list_actionability(self, **_kwargs):
            return {"items": [action]}

    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceRefreshStatusService", _SourceRefresh)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.SourceBackedEdgeControlService", _Edges)
    monkeypatch.setattr("app.control_center.decision_propagation_trace.PaperActionabilityService", _Actionability)

    trace = DecisionPropagationTraceService().get_trace()["traces"][0]

    assert trace["selected_candidate_event_id"] == "event-1"
    assert trace["selected_event_correlation_id"] == "corr-1"
    assert trace["selected_candidate_event_scope"] == "CANDIDATE_SCOPED"
    assert trace["selected_candidate_event_link_state"] == "LINKED_TO_CANDIDATE"
    assert trace["selected_orderbook_snapshot_id"] == "ob-1"
    assert trace["score_actionability_cycle_consistent"] is True
