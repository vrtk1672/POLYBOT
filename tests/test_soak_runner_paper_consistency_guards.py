from __future__ import annotations

from scripts.run_4h_technical_paper_soak import evaluate_stop_condition


def test_runner_stops_when_positions_increase_without_fills() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 3,
        "paper_orders": 3,
        "paper_fills": 3,
        "paper_positions": 3,
        "paper_trade_ledger": 6,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 3,
        "paper_orders": 6,
        "paper_fills": 3,
        "paper_positions": 6,
        "paper_trade_ledger": 6,
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) == "PAPER_POSITIONS_INCREASED_WITHOUT_FILLS"


def test_runner_stops_on_lineage_status_red() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 1,
        "paper_trade_ledger": 1,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "positions_without_fills_count": 1,
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) == "PAPER_POSITIONS_WITHOUT_FILLS"


def test_runner_allows_stable_quarantined_legacy_rows() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 3,
        "raw_positions_without_open_ledger_count": 3,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 3,
        "raw_positions_without_open_ledger_count": 3,
        "paper_lineage_consistency_status": "OK",
        "paper_lineage_readiness_status": "OK",
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) is None


def test_runner_stops_if_quarantine_count_increases() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 4,
        "paper_lineage_consistency_status": "OK",
        "paper_lineage_readiness_status": "OK",
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) == "PAPER_QUARANTINE_COUNT_INCREASED"


def test_runner_stops_if_raw_positions_without_fills_increase() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 3,
        "raw_positions_without_open_ledger_count": 3,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 4,
        "raw_positions_without_open_ledger_count": 3,
        "paper_lineage_consistency_status": "OK",
        "paper_lineage_readiness_status": "OK",
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) == "RAW_PAPER_POSITIONS_WITHOUT_FILLS_INCREASED"


def test_runner_stops_if_raw_positions_without_open_ledger_increase() -> None:
    baseline = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 3,
        "raw_positions_without_open_ledger_count": 3,
    }
    sample = {
        "endpoint_errors": [],
        "live_orders": 0,
        "real_orders": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 1,
        "paper_orders": 1,
        "paper_fills": 1,
        "paper_positions": 4,
        "paper_trade_ledger": 2,
        "quarantined_paper_positions_count": 3,
        "raw_positions_without_fills_count": 3,
        "raw_positions_without_open_ledger_count": 4,
        "paper_lineage_consistency_status": "OK",
        "paper_lineage_readiness_status": "OK",
        "runtime_health": "OK",
    }

    assert evaluate_stop_condition(sample, baseline) == "RAW_PAPER_POSITIONS_WITHOUT_OPEN_LEDGER_INCREASED"
