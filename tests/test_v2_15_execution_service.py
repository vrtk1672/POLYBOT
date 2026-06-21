from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.execution_v2.service import ExecutionV2Service
from test_v2_15_fixtures import approved_payload


def test_precheck_blocks_missing_risk_and_exit_plan():
    service = ExecutionV2Service(connection_factory=DatabaseConnectionFactory())
    payload = approved_payload()
    payload["risk_decision"] = {}
    result = service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id=None, manual_input=payload)
    assert not result["allowed"]
    assert "missing_risk_approval" in result["precheck"]["block_reasons"]
    assert "missing_exit_plan" in result["precheck"]["block_reasons"]


def test_runtime_mode_rules_and_live_not_certified():
    service = ExecutionV2Service(connection_factory=DatabaseConnectionFactory())
    assert "data_only_blocks_persisted_execution" in service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id="exit", manual_input=approved_payload(runtime_mode="DATA_ONLY"))["precheck"]["block_reasons"]
    assert service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id="exit", manual_input=approved_payload(runtime_mode="PAPER"))["allowed"]
    assert service.precheck(market_id="m1", execution_mode="SHADOW_PLAN", exit_plan_id="exit", manual_input=approved_payload(runtime_mode="SHADOW_LIVE"))["allowed"]
    assert "live_not_certified" in service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id="exit", manual_input=approved_payload(runtime_mode="SMALL_LIVE"))["precheck"]["block_reasons"]


def test_slippage_and_missing_bid_ask_block():
    service = ExecutionV2Service(connection_factory=DatabaseConnectionFactory())
    payload = approved_payload(slippage=500)
    assert "slippage_too_high" in service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id="exit", manual_input=payload)["precheck"]["block_reasons"]
    payload = approved_payload()
    payload["orderbook"]["best_bid"] = 0
    assert "missing_bid_ask" in service.precheck(market_id="m1", execution_mode="PAPER_SIM", exit_plan_id="exit", manual_input=payload)["precheck"]["block_reasons"]


def test_dry_run_writes_nothing_no_db():
    service = ExecutionV2Service(connection_factory=DatabaseConnectionFactory())
    result = service.paper_simulate(market_id="m1", exit_plan_id="exit", dry_run=True, manual_input=approved_payload())
    assert result["written"] is False
    assert result["dry_run"] is True


@pytest.mark.skipif(not DatabaseConnectionFactory().enabled, reason="DB not configured")
def test_service_persists_internal_paper_rows_db():
    service = ExecutionV2Service(connection_factory=DatabaseConnectionFactory())
    result = service.paper_simulate(market_id="v2_15_db_service", exit_plan_id="exit_placeholder_smoke", dry_run=False, manual_input=approved_payload(runtime_mode="PAPER"))
    assert result["written"] is True
    assert result["order"]["execution_mode"] == "PAPER_SIM"
    assert result["fills"]

