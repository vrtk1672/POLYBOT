from __future__ import annotations

from app.services.decision_funnel_diversity import summarize_market_side_diversity, top_non_selected_market_sides


def test_diversity_audit_reports_market_side_concentration_and_blockers() -> None:
    rows = [
        {"market_id": "691547", "side": "YES", "blockers_json": ["DUPLICATE_OPEN_PAPER_EXPOSURE"]},
        {"market_id": "691547", "side": "YES", "blockers_json": ["DUPLICATE_OPEN_PAPER_EXPOSURE"]},
        {"market_id": "597967", "side": "NO", "blockers_json": ["THESIS_WATCH"]},
    ]

    summary = summarize_market_side_diversity(rows)

    assert summary["unique_market_sides"] == 2
    assert summary["concentration_score"] == 0.6667
    assert summary["blockers_by_market_side"]["691547:YES"]["DUPLICATE_OPEN_PAPER_EXPOSURE"] == 2


def test_top_non_selected_candidates_preserve_exact_blockers() -> None:
    rows = [
        {"market_id": "691547", "side": "YES", "opportunity_score": 62, "blockers": []},
        {"market_id": "597967", "side": "NO", "opportunity_score": 58, "blockers": ["THESIS_WATCH"]},
    ]

    result = top_non_selected_market_sides(rows, {("691547", "YES")})

    assert result == [{"market_id": "597967", "side": "NO", "score": 58, "blockers": ["THESIS_WATCH"]}]
