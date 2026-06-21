from __future__ import annotations

from app.services.ai_mesh_intelligence import build_candidate_context, build_candidate_insights, deterministic_candidate_insight


def test_ai_can_suggest_non_news_thesis_and_hold_time_without_execution_permission() -> None:
    context = build_candidate_context(
        {
            "market_id": "m2",
            "side": "NO",
            "token_id": "t2",
            "proactive_candidate_seed_id": "seed2",
            "seed_mesh_inquiry_id": "inq2",
            "trigger_type": "PAYOUT_DISCREPANCY_TRIGGER",
            "thesis_state": "THESIS_MISSING",
            "exit_state": "EXIT_NOT_READY",
            "policy_blockers_json": ["thesis_not_supported", "exit_not_ready"],
        }
    )
    ai = deterministic_candidate_insight(context, ai_unavailable=False)
    insights = build_candidate_insights(context, ai, run_id="run2")
    thesis = next(item for item in insights if item["insight_type"] == "TRADE_THESIS")
    hold = next(item for item in insights if item["insight_type"] == "HOLD_TIME")

    assert thesis["thesis_type"] == "NO_VALID_THESIS"
    assert hold["expected_hold_time_seconds"] == 48 * 3600
    assert thesis["metadata_json"]["paper_allowed"] is False
    assert "thesis_not_supported" in thesis["why_not_json"]


def test_ai_can_return_no_valid_thesis_when_evidence_missing() -> None:
    context = build_candidate_context(
        {
            "market_id": "m3",
            "side": "SIDE_UNKNOWN",
            "token_id": None,
            "proactive_candidate_seed_id": "seed3",
            "seed_mesh_inquiry_id": "inq3",
            "trigger_type": "UNKNOWN",
            "thesis_state": "THESIS_MISSING",
            "exit_state": "EXIT_NOT_READY",
        }
    )
    ai = deterministic_candidate_insight(context, ai_unavailable=False)
    insights = build_candidate_insights(context, ai, run_id="run3")

    assert any(item["thesis_type"] == "NO_VALID_THESIS" for item in insights)
    assert any("token_id" in item["missing_evidence_json"] for item in insights)
    assert all(item["direction_hint"] == "UNKNOWN" for item in insights)
