from app.services.paper_observation_policy import (
    OBSERVATION_POLICY_BLOCKED,
    OBSERVATION_POLICY_INCOMPLETE,
    build_policy_review,
    default_observation_limits,
    ledger_separation_readiness,
)
from test_paper_observation_policy_review import _row


def test_risk_and_capital_blocks_block_observation_policy():
    risk = build_policy_review(_row(risk_state="RISK_BLOCKED"))
    capital = build_policy_review(_row(capital_state="CAPITAL_BLOCK"))

    assert risk["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "risk_hard_blocked" in risk["policy_blockers_json"]
    assert capital["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "capital_hard_blocked" in capital["policy_blockers_json"]


def test_stale_orderbook_and_token_mismatch_block_observation_policy():
    stale = build_policy_review(_row(orderbook_refresh_state="STALE"))
    mismatch = build_policy_review(_row(token_side_resolution_state="TOKEN_SIDE_CONFLICT"))

    assert stale["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "orderbook_not_fresh" in stale["policy_blockers_json"]
    assert mismatch["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "token_side_not_verified" in mismatch["policy_blockers_json"]


def test_missing_exit_or_lifecycle_hard_block_prevents_policy_pass():
    missing_exit = build_policy_review(_row(exit_state="UNKNOWN"))
    lifecycle = build_policy_review(_row(lifecycle_state="BLOCKED"))

    assert missing_exit["observation_policy_state"] == OBSERVATION_POLICY_INCOMPLETE
    assert "exit_not_ready" in missing_exit["policy_blockers_json"]
    assert lifecycle["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "lifecycle_hard_blocked" in lifecycle["policy_blockers_json"]


def test_policy_limits_and_ledger_readiness_do_not_enable_execution():
    limits = default_observation_limits()
    ledger = ledger_separation_readiness()

    assert limits["max_total_open_observation_positions"] == 1
    assert limits["excluded_from_full_paper_certification"] is True
    assert ledger["ready_for_observation_execution"] is False
    assert ledger["paper_ledger_has_observation_mode_columns"] is False
