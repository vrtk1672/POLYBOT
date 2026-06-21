from __future__ import annotations

import json

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.candidate_eligibility_recovery import CandidateEligibilityRecoveryService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import seed_paper_eligibility_chain, table_exists


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "candidate_eligibility_recovery_runs",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_fills",
            "paper_position_events",
            "paper_positions",
            "paper_order_events",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intent_runs",
            "no_trade_runs",
            "paper_intents",
            "no_trade_log",
            "paper_eligibility_runs",
            "paper_eligibility_candidates",
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "thesis_profile_evidence_items",
            "thesis_profiles",
            "signal_market_links",
            "neuron_signals",
            "coordinator_decision_inputs",
            "runtime_coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_outputs",
            "orderbook_snapshots",
            "markets_v2",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="candidate_recovery_prepare")


def _set_matched_side(signal_id: str, side: str = "YES", confidence: float = 0.95) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE signal_market_links
            SET link_evidence_json = %s,
                link_confidence = %s,
                confidence = %s,
                link_status = 'confirmed',
                is_review_required = false
            WHERE signal_id = %s
            """,
            (Jsonb({"matched_side": side}), confidence, confidence, signal_id),
        )


def test_system_off_blocks_candidate_eligibility_recovery(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("off", side=None)
    _set_matched_side(str(ids["signal_id"]))
    PaperEligibilityService().evaluate_candidates(limit=10)
    SystemPowerService().turn_off(actor="test", reason="candidate_recovery_off")

    result = CandidateEligibilityRecoveryService().run_recovery(cycle_id="off-cycle", limit=10)

    assert result["status"] == "BLOCKED"
    assert result["error_message"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        thesis = conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id = %s", (ids["thesis_id"],)).fetchone()
        assert thesis["side"] is None
        assert _count(conn, "paper_intents") == 0


def test_recovery_recovers_side_recomputes_readiness_and_creates_safe_paper_artifacts(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("recover", side=None)
    _set_matched_side(str(ids["signal_id"]), side="YES")
    before = PaperEligibilityService().evaluate_candidates(limit=10)
    assert before["eligible_count"] == 0
    assert before["blocked_count"] == 1

    result = CandidateEligibilityRecoveryService().run_recovery(cycle_id="recover-cycle", limit=10)

    assert result["status"] == "OK"
    assert result["sides_recovered"] == 1
    assert result["eligible_after"] >= 1
    assert result["paper_intents_after"] >= 1
    assert result["paper_orders_delta"] >= 1
    assert result["paper_fills_delta"] >= 1
    assert result["paper_positions_delta"] >= 1
    assert result["live_orders_delta"] == 0
    assert result["real_orders_delta"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        thesis = conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id = %s", (ids["thesis_id"],)).fetchone()
        candidate = conn.execute("SELECT status, side FROM paper_eligibility_candidates").fetchone()
        intent = conn.execute("SELECT side, intended_price, evidence FROM paper_intents").fetchone()
    assert thesis["side"] == "YES"
    assert candidate["status"] == "ELIGIBLE"
    assert candidate["side"] == "YES"
    assert intent["side"] == "YES"
    assert float(intent["intended_price"]) > 0
    assert float(intent["evidence"]["quantity"]) > 0


def test_recovery_does_not_default_ambiguous_side(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("ambiguous", side=None)
    # Strong binding exists, but no deterministic matched_side exists.
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE signal_market_links SET link_evidence_json = %s WHERE signal_id = %s",
            (Jsonb({"matched_side": "UNKNOWN"}), ids["signal_id"]),
        )

    result = CandidateEligibilityRecoveryService().run_recovery(cycle_id="ambiguous-cycle", limit=10)

    assert result["status"] == "OK"
    assert result["sides_recovered"] == 0
    assert result["eligible_after"] == 0
    assert result["paper_intents_after"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        thesis = conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id = %s", (ids["thesis_id"],)).fetchone()
        candidate = conn.execute("SELECT status, eligibility_blockers FROM paper_eligibility_candidates").fetchone()
    assert thesis["side"] is None
    assert candidate["status"] == "BLOCKED"
    assert "MISSING_SIDE" in candidate["eligibility_blockers"]


def test_recovery_rejects_weak_side_evidence(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("weak-side", side=None)
    _set_matched_side(str(ids["signal_id"]), side="NO", confidence=0.4)

    result = CandidateEligibilityRecoveryService().run_recovery(cycle_id="weak-side-cycle", limit=10)

    assert result["sides_recovered"] == 0
    assert result["eligible_after"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT side FROM thesis_profiles WHERE thesis_id = %s", (ids["thesis_id"],)).fetchone()["side"] is None


def test_recovery_is_idempotent_for_same_cycle(postgres_test_schema) -> None:
    _prepare()
    ids = seed_paper_eligibility_chain("idempotent", side=None)
    _set_matched_side(str(ids["signal_id"]), side="YES")

    first = CandidateEligibilityRecoveryService().run_recovery(cycle_id="idem-cycle", limit=10)
    second = CandidateEligibilityRecoveryService().run_recovery(cycle_id="idem-cycle", limit=10)

    assert first["paper_intents_after"] >= 1
    assert second["idempotent"] is True
    with DatabaseConnectionFactory().connect() as conn:
        intent_count = _count(conn, "paper_intents")
        order_count = _count(conn, "paper_orders")
        fill_count = _count(conn, "paper_fills")
        position_count = _count(conn, "paper_positions")
    assert intent_count == first["paper_intents_after"]
    assert order_count == first["paper_orders_delta"]
    assert fill_count == first["paper_fills_delta"]
    assert position_count == first["paper_positions_delta"]


def _count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
