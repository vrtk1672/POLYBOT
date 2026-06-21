from __future__ import annotations

import scripts.run_overnight_observation as overnight_runner
from scripts.run_overnight_observation import evaluate_stop_condition, preflight_check, safety_counts


def _baseline() -> dict[str, int]:
    return {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents": 6,
        "paper_orders": 9,
        "paper_fills": 6,
        "paper_positions": 9,
        "paper_trade_ledger": 12,
    }


def _sample(**overrides):
    sample = {
        "endpoint_errors": [],
        "mock_data_endpoints": [],
        "live_orders": 0,
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "lineage_status": "OK",
        "active_positions_without_fills": 0,
        "capital_reconciliation_status": "OK",
        "paper_positions": 9,
        "paper_fills": 6,
    }
    sample.update(overrides)
    return sample


def test_overnight_runner_hard_stops_on_live_orders() -> None:
    reason = evaluate_stop_condition(_sample(live_orders=1), _baseline())

    assert reason == "LIVE_ORDERS_PRESENT"


def test_overnight_runner_hard_stops_on_real_order_delta() -> None:
    reason = evaluate_stop_condition(_sample(real_orders_current=2), _baseline())

    assert reason == "REAL_ORDERS_DELTA"


def test_overnight_runner_hard_stops_on_paper_lineage_red() -> None:
    reason = evaluate_stop_condition(_sample(lineage_status="RED"), _baseline())

    assert reason == "PAPER_LINEAGE_RED"


def test_overnight_runner_hard_stops_on_active_positions_without_fills() -> None:
    reason = evaluate_stop_condition(_sample(active_positions_without_fills=1), _baseline())

    assert reason == "ACTIVE_POSITIONS_WITHOUT_FILLS"


def test_overnight_runner_hard_stops_on_mock_dashboard_data() -> None:
    reason = evaluate_stop_condition(_sample(mock_data_endpoints=["/dashboard/api/v2/paper"]), _baseline())

    assert reason == "FAKE_OR_MOCK_DASHBOARD_DATA"


def test_overnight_runner_hard_stops_on_repeated_provider_failures() -> None:
    reason = evaluate_stop_condition(_sample(), _baseline(), repeated_provider_failures=3)

    assert reason == "PROVIDER_LOOP_FAILING_REPEATEDLY"


def test_overnight_runner_allows_safe_yellow_ai_provider_failures() -> None:
    reason = evaluate_stop_condition(
        _sample(unsafe_degraded_sources=[]),
        _baseline(),
        repeated_provider_failures=0,
    )

    assert reason is None


def test_overnight_runner_treats_legacy_news_provider_as_safe_yellow() -> None:
    assert "news_provider" in overnight_runner.SAFE_YELLOW_DEGRADED_SOURCES


def test_overnight_runner_treats_openai_quota_as_safe_yellow_ai() -> None:
    assert "OPENAI_QUOTA_EXCEEDED" in overnight_runner.SAFE_YELLOW_AI_REASONS


def test_ai_required_false_allows_observation_safe_yellow(monkeypatch) -> None:
    monkeypatch.delenv("AI_REQUIRED", raising=False)

    def fake_get_json(_base_url: str, endpoint: str) -> dict:
        return _preflight_payload(endpoint, ai_latest="AI_CONTEXT_UNAVAILABLE")

    monkeypatch.setattr(overnight_runner, "get_json", fake_get_json)

    result = preflight_check("http://example.test")

    assert result["status"] == "YELLOW"
    assert result["blockers"] == []
    assert any("SAFE_YELLOW_AI_DEGRADED" in warning for warning in result["warnings"])


def test_ai_required_true_blocks_observation_when_all_providers_fail(monkeypatch) -> None:
    monkeypatch.setenv("AI_REQUIRED", "true")

    def fake_get_json(_base_url: str, endpoint: str) -> dict:
        return _preflight_payload(endpoint, ai_latest="AI_CONTEXT_UNAVAILABLE")

    monkeypatch.setattr(overnight_runner, "get_json", fake_get_json)

    result = preflight_check("http://example.test")

    assert result["status"] == "RED"
    assert any(str(blocker).startswith("AI_REQUIRED_BUT_DEGRADED") for blocker in result["blockers"])


def test_preflight_accepts_safe_stopped_when_system_power_off(monkeypatch) -> None:
    monkeypatch.delenv("AI_REQUIRED", raising=False)

    def fake_get_json(_base_url: str, endpoint: str) -> dict:
        return _preflight_payload(endpoint, ai_latest="OK", runtime_status="SAFE_STOPPED")

    monkeypatch.setattr(overnight_runner, "get_json", fake_get_json)

    result = preflight_check("http://example.test")

    assert result["status"] == "GREEN"
    assert "RUNTIME_HEALTH_NOT_OK" not in result["blockers"]


def test_safety_counts_tracks_no_trading_mutation_baseline() -> None:
    paper = {
        "real_orders_current": 1,
        "orders_v2": 1,
        "fills_v2": 1,
        "canonical_positions": 0,
        "paper_intents_total": 6,
        "paper_orders_total": 9,
        "paper_fills_total": 6,
        "paper_positions_total": 9,
        "paper_trade_ledger": 12,
    }

    assert safety_counts(paper) == _baseline()


def _preflight_payload(endpoint: str, *, ai_latest: str, runtime_status: str = "OK") -> dict:
    if endpoint == "/healthz":
        return {"status": "ok", "ready": True}
    if endpoint == "/runtime/health":
        if runtime_status == "SAFE_STOPPED":
            return {"overall_status": "SAFE_STOPPED", "system_power": "OFF", "runtime_work_allowed": False}
        return {"status": runtime_status}
    if endpoint == "/system/power":
        return {"power": "OFF", "runtime_work_allowed": False}
    if endpoint == "/dashboard/api/v2/source-status":
        return {"mock_data": False, "status": "OK", "degraded_sources": []}
    if endpoint == "/dashboard/api/v2/ai-context-router":
        if ai_latest == "OK":
            return {
                "mock_data": False,
                "latest_status": "OK",
                "ollama_status": {"status": "OK", "reason": None},
                "openai_status": {"status": "NOT_ATTEMPTED", "reason": None},
                "anthropic_status": {"status": "NOT_ATTEMPTED", "reason": None},
                "latest_runs": [],
            }
        return {
            "mock_data": False,
            "latest_status": ai_latest,
            "ollama_status": {"status": "FAILED", "reason": "OLLAMA_TIMEOUT"},
            "openai_status": {"status": "FAILED", "reason": "OPENAI_RATE_LIMITED"},
            "anthropic_status": {"status": "FAILED", "reason": "ANTHROPIC_DEGRADED"},
            "latest_runs": [],
        }
    if endpoint == "/dashboard/api/v2/paper":
        return {
            "mock_data": False,
            "live_orders": 0,
            "live_enabled": False,
            "shadow_enabled": False,
            "paper_lineage_consistency_status": "OK",
            "capital_reconciliation_status": "OK",
            "real_orders_current": 1,
            "orders_v2": 1,
            "fills_v2": 1,
            "canonical_positions": 0,
            "paper_intents_total": 6,
            "paper_orders_total": 9,
            "paper_fills_total": 6,
            "paper_positions_total": 9,
            "paper_trade_ledger": 12,
        }
    if endpoint == "/dashboard/api/v2/paper/soak-readiness":
        return {"mock_data": False, "safety_status": "GREEN"}
    if endpoint == "/dashboard/api/v2/overnight/status":
        return {"mock_data": False, "status": "OK"}
    raise AssertionError(endpoint)
