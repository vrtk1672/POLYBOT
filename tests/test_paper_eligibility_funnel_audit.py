from app.services.decision_funnel_diversity import summarize_market_side_diversity


def test_funnel_audit_reports_all_stages_by_market_side():
    stages = {
        "mesh_reviewed": [
            {"market_id": "691547", "side": "YES"},
            {"market_id": "597967", "side": "NO"},
        ],
        "policy_review": [
            {"market_id": "691547", "side": "YES"},
            {"market_id": "597967", "side": "NO", "policy_blockers_json": ["thesis_watch_not_observation_policy_eligible"]},
        ],
    }

    audit = {stage: summarize_market_side_diversity(rows) for stage, rows in stages.items()}

    assert audit["mesh_reviewed"]["unique_market_sides"] == 2
    assert audit["policy_review"]["unique_market_sides"] == 2
    assert audit["policy_review"]["blockers_by_market_side"]["597967:NO"]["thesis_watch_not_observation_policy_eligible"] == 1


def test_non_dominant_mesh_candidate_appears_in_funnel():
    rows = [
        {"market_id": "691547", "side": "YES"},
        {"market_id": "597967", "side": "NO"},
    ]

    summary = summarize_market_side_diversity(rows)

    assert {"market_id": "597967", "side": "NO", "count": 1} in summary["top_market_sides"]
