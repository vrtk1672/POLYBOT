from __future__ import annotations

from app.services.brain_coordinator import BrainCoordinatorService


def _output(brain: str, output_type: str, recommendation: str, **extra) -> dict[str, object]:
    return {
        "brain_output_id": f"brain_output_{brain}_{output_type}_{recommendation}".replace("-", "_").lower(),
        "brain": brain,
        "output_type": output_type,
        "recommendation": recommendation,
        "status": "ACTIVE",
        **extra,
    }


def _decision(outputs: list[dict[str, object]]) -> dict[str, object]:
    decision, _inputs, conflicts = BrainCoordinatorService().apply_coordination_rules(outputs)
    return {**decision.to_api_dict(), "conflicts": [item.model_dump(mode="json") for item in conflicts]}


def test_risk_blocks_opportunity() -> None:
    payload = _decision(
        [
            _output("opportunity", "OPPORTUNITY_HINT", "OPPORTUNITY_HINT", confidence=0.8),
            _output("risk", "RISK_WARNING", "CAUTION", confidence=0.9, risk_flags=["risk_high"]),
        ]
    )

    assert payload["final_state"] == "RISK_BLOCKED"
    assert "OPPORTUNITY_OVERRIDE_RISK" in payload["blocked_actions"]
    assert payload["conflicts"][0]["conflict_key"] == "opportunity_positive_vs_risk_high"


def test_rules_ambiguity_blocks_entry() -> None:
    payload = _decision(
        [
            _output("opportunity", "OPPORTUNITY_HINT", "OPPORTUNITY_HINT"),
            _output("context", "CAUTION", "REVIEW", risk_flags=["resolution_ambiguous"]),
        ]
    )

    assert payload["final_state"] == "PAPER_CANDIDATE_BLOCKED"
    assert "PAPER_ENTRY" in payload["blocked_actions"]
    assert any(item["conflict_key"] == "rules_ambiguous_vs_opportunity_candidate" for item in payload["conflicts"])


def test_capital_insufficiency_limits_action_scope() -> None:
    payload = _decision(
        [
            _output("opportunity", "OPPORTUNITY_HINT", "OPPORTUNITY_HINT"),
            _output("capital", "CAPITAL_NOTE", "INSUFFICIENT_CAPITAL", risk_flags=["insufficient_capital"]),
        ]
    )

    assert payload["final_state"] == "REVIEW_REQUIRED"
    assert "PAPER_ENTRY" in payload["blocked_actions"]
    assert any(item["conflict_key"] == "capital_insufficient_vs_opportunity_candidate" for item in payload["conflicts"])


def test_exit_review_overrides_hold() -> None:
    payload = _decision(
        [
            _output("context", "WATCH", "WATCH"),
            _output("exit", "EXIT_REVIEW_HINT", "REVIEW", urgency=0.9),
        ]
    )

    assert payload["final_state"] == "EXIT_REVIEW_REQUIRED"
    assert "SEND_TO_EXIT_REVIEW" in payload["approved_actions"]
    assert any(item["conflict_key"] == "exit_review_vs_hold" for item in payload["conflicts"])


def test_ai_cannot_override_risk() -> None:
    payload = _decision(
        [
            _output("ai", "AI_ANALYSIS", "POSITIVE_OPPORTUNITY", confidence=0.8),
            _output("risk", "RISK_WARNING", "CAUTION", confidence=0.9, risk_flags=["risk_high"]),
        ]
    )

    assert payload["final_state"] == "RISK_BLOCKED"
    assert any(item["conflict_key"] == "ai_positive_vs_risk_block" for item in payload["conflicts"])


def test_no_trade_is_valid_final_state() -> None:
    payload = _decision([_output("no_trade", "NO_TRADE_HINT", "NO_TRADE", confidence=0.8)])

    assert payload["final_state"] == "NO_TRADE"
    assert "MARK_NO_TRADE" in payload["approved_actions"]
    assert payload["execution_allowed"] is False


def test_insufficient_data_becomes_insufficient_data() -> None:
    payload = _decision([])

    assert payload["final_state"] == "INSUFFICIENT_DATA"
    assert "REQUEST_MORE_DATA" in payload["approved_actions"]
    assert payload["execution_allowed"] is False
