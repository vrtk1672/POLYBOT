from __future__ import annotations

from app.services.ai_mesh_intelligence import build_candidate_context, build_candidate_insights


def test_ai_exit_and_invalidation_suggestions_are_advisory_only() -> None:
    context = build_candidate_context(
        {
            "market_id": "m4",
            "condition_id": "c4",
            "side": "YES",
            "token_id": "t4",
            "proactive_candidate_seed_id": "seed4",
            "seed_mesh_inquiry_id": "inq4",
            "trigger_type": "MARKET_MOVEMENT_TRIGGER",
            "thesis_state": "THESIS_WATCH",
            "exit_state": "EXIT_NOT_READY",
        }
    )
    ai = {
        "_model_provider": "OLLAMA",
        "_model_name": "qwen3:4b",
        "summary": "Momentum thesis needs a time stop and invalidation.",
        "direction_hint": "YES",
        "direction_confidence": 0.58,
        "thesis_type": "MOMENTUM_CONTINUATION",
        "thesis_confidence": 0.61,
        "expected_hold_time_seconds": 14400,
        "time_stop_seconds": 14400,
        "invalidation_condition": "Invalidate if price gives back the trigger move.",
        "missing_evidence": ["independent_confirmation"],
        "why_not": ["THESIS_WATCH"],
        "recommended_mesh_action": "BUILD_THESIS",
        "confidence": 0.61,
    }
    insights = build_candidate_insights(context, ai, run_id="run4")
    exit_insight = next(item for item in insights if item["insight_type"] == "EXIT_PLAN")
    invalidation = next(item for item in insights if item["insight_type"] == "INVALIDATION")

    assert exit_insight["time_stop_seconds"] == 14400
    assert invalidation["invalidation_condition"] == "Invalidate if price gives back the trigger move."
    assert exit_insight["is_execution_authority"] is False
    assert invalidation["metadata_json"]["does_not_override_hard_blockers"] is True
