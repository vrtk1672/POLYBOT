from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.opportunity.service import OpportunityService


def _manual():
    return {
        "context_output": {"run_id": "context_test", "strength": 0.9, "confidence": 0.9, "already_priced_in_score": 0.1, "urgency_score": 0.7},
        "capital_output": {"run_id": "capital_test", "capital_allowed": True, "allocation_confidence": 0.9, "capital_recycling_score": 0.7},
        "market_signal": {"technical_score": 0.8, "data_completeness_score": 1.0, "technical_blocked": False},
        "orderbook_signal": {"has_bid_ask": True, "spread_bps": 80, "depth_2c": 500},
        "liquidity_signal": {"entry_liquidity_score": 0.8, "exit_liquidity_score": 0.8, "exit_quality_score": 0.85, "expected_slippage_bps": 70, "max_safe_size_usd": 1000},
        "time_signal": {"time_efficiency_score": 0.7, "lockup_penalty_score": 0.1},
        "fee_reward_signal": {"reward_score": 0.2, "friction_score": 0.1, "net_edge_after_costs": 0.7},
        "market_memory": {"memory_confidence": 0.8, "wording_risk_avg": 0.1, "whale_memory": {"whale_score": 0.8, "confidence": 0.8}},
        "data_completeness_score": 1.0,
    }


def test_service_persists_runs_scores_inputs_flags_and_events(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    service = OpportunityService(connection_factory=factory)

    result = service.score_market("opp_m1", manual_input=_manual())

    assert result["written"] is True
    run_id = result["result"]["run_id"]
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM opportunity_runs").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM opportunity_scores_v2").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM opportunity_signal_inputs").fetchone()["count"] > 0
        assert conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type = 'opportunity.score.created'").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM opportunity_scores_v2 WHERE run_id=%s", (run_id,)).fetchone()["count"] == 1


def test_service_handles_missing_brain_outputs_honestly(postgres_test_schema):
    run_migrations()
    result = OpportunityService(connection_factory=DatabaseConnectionFactory()).score_market("missing", dry_run=True)

    score = result["result"]["score"]
    assert result["written"] is False
    assert score["insufficient_data"] is True
    assert "missing_context_output" in score["insufficient_data_reasons"]


def test_service_capital_not_allowed_blocks(postgres_test_schema):
    run_migrations()
    manual = _manual()
    manual["capital_output"] = {"capital_allowed": False, "block_reason": "cash_reserve_too_low"}
    result = OpportunityService(connection_factory=DatabaseConnectionFactory()).score_market("blocked", dry_run=True, manual_input=manual)

    assert result["result"]["score"]["score_band"] == "BLOCKED"
    assert "capital_not_allowed" in result["result"]["score"]["no_trade_reasons"]

