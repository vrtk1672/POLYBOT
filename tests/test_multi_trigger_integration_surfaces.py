from __future__ import annotations

from app.control_center.multi_trigger_candidate_generation import MultiTriggerCandidateGenerationControlService
from app.db.config import DatabaseSettings
from app.db.connection import DatabaseConnectionFactory
from app.services.multi_trigger_candidate_generation import MultiTriggerProactiveCandidateGeneratorService, build_seed_from_trigger, evaluate_trigger
from app.services.trade_opportunity_score import score_actionability_item
from test_multi_trigger_candidate_generation import trigger


def test_multi_trigger_control_summary_shape_when_database_unavailable() -> None:
    factory = DatabaseConnectionFactory(DatabaseSettings(database_url=None))
    payload = MultiTriggerCandidateGenerationControlService(connection_factory=factory).get_summary(limit=1)

    assert "data" in payload
    assert payload["source"] in {"multi_trigger_candidate_generation", "multi_trigger_candidate_triggers + proactive_candidate_seeds"}


def test_service_empty_market_fields_are_safe_without_database() -> None:
    factory = DatabaseConnectionFactory(DatabaseSettings(database_url=None))
    fields = MultiTriggerProactiveCandidateGeneratorService(connection_factory=factory).fields_for_market(market_id=None)

    assert fields["multi_trigger_count"] == 0
    assert fields["strongest_trigger_type"] is None


def test_seed_exposes_trigger_metadata_for_downstream_surfaces() -> None:
    item = trigger(trigger_type="ORDERBOOK_PRESSURE", multi_trigger_id="multi_trigger_surface")
    item.update(evaluate_trigger(item))
    seed = build_seed_from_trigger(item)

    assert seed["multi_trigger_id"] == "multi_trigger_surface"
    assert seed["trigger_type"] == "ORDERBOOK_PRESSURE"
    assert seed["trigger_score"] == 82.0
    assert seed["seed_generation_source"] == "MULTI_TRIGGER"


def test_opportunity_score_preserves_trigger_metadata_without_approval_grant() -> None:
    score = score_actionability_item(
        {
            "candidate_id": "candidate_1",
            "market_id": "market_1",
            "side": "YES",
            "token_id": "yes_token",
            "multi_trigger_id": "multi_trigger_score",
            "trigger_type": "MARKET_MOVEMENT",
            "trigger_score": 74.0,
            "trigger_reasons": ["RECENT_MARKET_MOVEMENT"],
            "seed_generation_source": "MULTI_TRIGGER",
            "research_only": True,
            "execution_allowed": False,
            "paper_allowed": False,
            "edge_state": "EDGE_WATCH",
            "risk_decision": "RISK_REVIEW",
            "capital_state": "CAPITAL_WATCH",
            "exit_state": "EXIT_READY",
            "candidate_event_scope": "CANDIDATE_SCOPED",
            "candidate_event_link_state": "LINKED_TO_CANDIDATE",
            "orderbook_freshness_state": "FRESH",
            "trade_thesis_state": "WATCH",
        }
    )

    assert score["multi_trigger_id"] == "multi_trigger_score"
    assert score["trigger_type"] == "MARKET_MOVEMENT"
    assert score["trigger_score"] == 74.0
    assert score["seed_generation_source"] == "MULTI_TRIGGER"
    assert score["execution_authority"] == "NONE_DATA_ONLY"
