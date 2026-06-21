from __future__ import annotations

from app.services.ai_mesh_intelligence import build_event_context, build_event_insights, deterministic_event_insight


def test_ai_event_intelligence_proposes_recall_keywords_not_market_ids() -> None:
    context = build_event_context(
        {
            "source_event_id": "event-1",
            "title": "SEC delays decision on spot Ethereum ETF",
            "summary": "Regulator decision window changes for crypto ETF approval.",
            "source_type": "NEWS",
        }
    )
    ai = deterministic_event_insight(context, ai_unavailable=False)
    insights = build_event_insights(context, ai, run_id="run-event")
    recall = next(item for item in insights if item["insight_type"] == "MARKET_RECALL")

    assert recall["source_event_id"] == "event-1"
    assert recall["is_execution_authority"] is False
    assert recall["related_markets_json"] == []
    assert "SEC" in recall["entities_json"] or "Ethereum" in recall["entities_json"]


def test_ai_unavailable_degrades_safely_for_events() -> None:
    context = build_event_context({"source_event_id": "event-2", "summary": "Short event"})
    ai = deterministic_event_insight(context, ai_unavailable=True)
    insights = build_event_insights(context, ai, run_id="run-event")

    assert all(item["model_provider"] == "NONE" for item in insights)
    assert all("AI_UNAVAILABLE" in item["why_not_json"] for item in insights)
    assert all(item["recommended_mesh_action"] in {"WATCH_ONLY", "NO_ACTION"} for item in insights)
