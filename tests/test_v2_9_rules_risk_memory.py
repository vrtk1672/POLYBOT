from app.market_memory.rules_risk_memory_builder import RulesRiskMemoryBuilder


def test_rules_risk_memory_stores_wording_risk_and_resolution_delay():
    memory = RulesRiskMemoryBuilder().build(
        [
            {
                "wording_risk": 0.8,
                "dispute_risk": 0.5,
                "resolution_clarity": 0.3,
                "ambiguous_terms_json": ["reported", "around"],
                "edge_cases_json": ["deadline unclear"],
                "recommendation": "NO_TRADE",
            }
        ],
        market_id="m1",
        market_family="politics",
    )

    assert memory.avg_wording_risk == 0.8
    assert memory.avg_dispute_risk == 0.5
    assert memory.avg_resolution_clarity == 0.3
    assert memory.ambiguous_terms_count == 2
    assert memory.edge_case_count == 1
    assert memory.rules_block_rate == 1.0
    assert memory.rules_risk_score > 0.5


def test_rules_risk_memory_missing_rules_is_insufficient_data():
    memory = RulesRiskMemoryBuilder().build([], market_family="legal")

    assert memory.observations_count == 0
    assert memory.rules_risk_score == 0
    assert memory.confidence == 0
    assert memory.summary["insufficient_data"] is True
