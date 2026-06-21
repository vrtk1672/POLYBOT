from __future__ import annotations

from scripts.run_active_30m_observation import evaluate_stop_condition, secrets_exposed


def _sample(**paper_overrides):
    paper = {
        "live_orders": 0,
        "live_enabled": False,
        "shadow_enabled": False,
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_orders": 9,
        "paper_fills": 6,
        "paper_positions": 9,
        "paper_lineage": "OK",
        "capital_reconciliation": "OK",
        "active_positions_without_fills": 0,
    }
    paper.update(paper_overrides)
    return {"mock_data_endpoints": [], "secret_exposed": False, "paper": paper}


def test_active_runner_hard_stops_on_live_orders() -> None:
    baseline = _sample()
    sample = _sample(live_orders=1)

    assert evaluate_stop_condition(sample, baseline, repeated_api_failures=0, repeated_cycle_failures=0) == "LIVE_ORDERS_PRESENT"


def test_active_runner_allows_paper_position_with_matching_fill_and_order() -> None:
    baseline = _sample()
    sample = _sample(paper_orders=10, paper_fills=7, paper_positions=10)

    assert evaluate_stop_condition(sample, baseline, repeated_api_failures=0, repeated_cycle_failures=0) is None


def test_active_runner_blocks_paper_position_without_fill() -> None:
    baseline = _sample()
    sample = _sample(paper_orders=10, paper_fills=6, paper_positions=10)

    assert evaluate_stop_condition(sample, baseline, repeated_api_failures=0, repeated_cycle_failures=0) == "PAPER_POSITION_CREATED_WITHOUT_FILL"


def test_active_runner_blocks_real_order_delta() -> None:
    baseline = _sample()
    sample = _sample(orders_v2=2)

    assert evaluate_stop_condition(sample, baseline, repeated_api_failures=0, repeated_cycle_failures=0) == "ORDERS_V2_UNEXPECTED_DELTA"


def test_secret_detector_allows_risk_identifiers_but_blocks_key_shapes() -> None:
    assert secrets_exposed({"consumer_name": "smoke-risk-organ"}) is False
    assert secrets_exposed({"value": "sk-proj-1234567890abcdef"}) is True
