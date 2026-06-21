from app.services.proactive_candidate_generation import _empty_market_fields as proactive_empty_fields
from app.services.research_priority_watchlist import ResearchPriorityWatchlistService
from app.services.trade_opportunity_score import score_actionability_item


def test_trade_opportunity_score_exposes_research_priority_metadata():
    score = score_actionability_item(
        {
            "candidate_id": "candidate_1",
            "market_id": "market_1",
            "side": "YES",
            "token_id": "token_yes",
            "edge_state": "EDGE_SUPPORTED",
            "source_backed": True,
            "risk_usable": True,
            "candidate_event_scope": "CANDIDATE_SCOPED",
            "candidate_event_link_state": "LINKED_TO_CANDIDATE",
            "orderbook_freshness_state": "FRESH",
            "thesis_id": "thesis_1",
            "trade_thesis_type": "MISPRICING_REVERSION",
            "exit_intent": "PRICE_TARGET_EXIT",
            "expected_hold_time_hours": 48,
            "exit_readiness_state": "EXIT_READY",
            "risk_gate_state": "RISK_REVIEW",
            "capital_gate_state": "CAPITAL_WATCH",
            "research_watchlist_id": "watch_1",
            "research_priority_band": "HIGH",
            "research_priority_score": 72.5,
            "priority_reasons": ["RECENT_STRONG_EVENT_LINKS"],
            "watchlist_scheduler_state": "NOT_DUE",
        }
    )
    assert score["research_watchlist_id"] == "watch_1"
    assert score["research_priority_band"] == "HIGH"
    assert score["research_priority_score"] == 72.5
    assert score["research_priority_reasons"] == ["RECENT_STRONG_EVENT_LINKS"]
    assert score["decision_band"] != "FULL_PAPER_CERTIFICATION"


def test_research_priority_empty_market_fields_are_safe_visibility_only():
    fields = ResearchPriorityWatchlistService(connection_factory=None).fields_for_market(market_id=None)
    assert fields["research_watchlist_id"] is None
    assert fields["research_priority_band"] is None
    assert fields["watchlist_reason"] is None


def test_proactive_empty_fields_do_not_claim_priority():
    fields = proactive_empty_fields()
    assert "source_market_priority_band" not in fields or fields.get("source_market_priority_band") is None
