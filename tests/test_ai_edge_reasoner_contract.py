from __future__ import annotations

from app.services.ai_edge_reasoner import validate_ai_edge_review


def test_ai_edge_review_rejects_invented_source_ids() -> None:
    result = validate_ai_edge_review(
        {
            "edge_state": "EDGE_SUPPORTED",
            "summary": "Looks supported.",
            "cited_source_record_ids": ["news_impact_scores:known", "made_up:source"],
        },
        allowed_source_ids={"news_impact_scores:known"},
    )

    assert result["status"] == "REJECTED"
    assert result["blocker"] == "AI_INVENTED_SOURCE_IDS"


def test_ai_edge_review_rejects_invented_probability() -> None:
    result = validate_ai_edge_review(
        {
            "edge_state": "EDGE_SUPPORTED",
            "summary": "Looks supported.",
            "cited_source_record_ids": ["news_impact_scores:known"],
            "fair_probability_estimate": 0.72,
        },
        allowed_source_ids={"news_impact_scores:known"},
    )

    assert result["status"] == "REJECTED"
    assert result["blocker"] == "AI_INVENTED_PROBABILITY"


def test_ai_edge_review_rejects_malformed_output() -> None:
    result = validate_ai_edge_review("not json", allowed_source_ids=set())

    assert result["status"] == "UNAVAILABLE"
    assert result["ai_review_status"] == "AI_REVIEW_MALFORMED"
