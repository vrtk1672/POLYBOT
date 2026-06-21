from __future__ import annotations

from app.services.ai_mesh_intelligence import (
    build_candidate_context,
    build_candidate_insights,
    deterministic_candidate_insight,
    _deterministic_schema_fallback,
)


def test_schema_fallback_is_marked_deterministic_and_non_ai() -> None:
    fallback = _deterministic_schema_fallback("THESIS", "AI_SCHEMA_INVALID: bad")

    assert fallback["generated_by"] == "DETERMINISTIC_FALLBACK"
    assert fallback["confidence"] == 0.0
    assert fallback["is_execution_authority"] is False


def test_deterministic_candidate_fallback_does_not_create_authority() -> None:
    context = build_candidate_context(
        {
            "market_id": "m1",
            "side": "YES",
            "token_id": "t1",
            "proactive_candidate_seed_id": "seed1",
            "seed_mesh_inquiry_id": "inq1",
            "trigger_type": "PAYOUT_DISCREPANCY",
            "thesis_state": "THESIS_MISSING",
            "exit_state": "EXIT_NOT_READY",
            "policy_blockers_json": ["exit_not_ready"],
        }
    )
    ai = deterministic_candidate_insight(
        context,
        ai_unavailable=False,
        error="AI_INVALID_JSON: bad",
        fallback_reason="model_output_invalid",
    )
    insights = build_candidate_insights(context, ai, run_id="run1")

    assert ai["_generated_by"] == "DETERMINISTIC_FALLBACK"
    assert all(item["metadata_json"]["generated_by"] == "DETERMINISTIC_FALLBACK" for item in insights)
    assert all(item["is_execution_authority"] is False for item in insights)
    assert all(item["metadata_json"]["paper_allowed"] is False for item in insights)
