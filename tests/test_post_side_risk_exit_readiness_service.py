from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_eligibility import PaperEligibilityService
from app.services.post_side_risk_exit_readiness import PostSideRiskExitReadinessService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import seed_paper_eligibility_chain, table_exists


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "post_side_risk_exit_recovery_runs",
            "candidate_eligibility_recovery_runs",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_fills",
            "paper_positions",
            "paper_orders",
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
            "neuron_signal_bindings",
            "neuron_signals",
            "coordinator_decisions",
            "brain_outputs",
            "orderbook_snapshots",
            "markets_v2",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="post_side_prepare")


def _seed_post_side_candidate(suffix: str, *, orderbook: bool = True, side: str | None = "YES") -> dict[str, str | None]:
    ids = seed_paper_eligibility_chain(
        suffix,
        side=side,
        orderbook=orderbook,
        risk_approved=False,
        exit_status="BLOCKED",
        paper_exit_ready=False,
        thesis_status="BLOCKED",
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE thesis_profiles
            SET missing_evidence = %s,
                evidence = evidence || %s,
                status = 'BLOCKED'
            WHERE thesis_id = %s
            """,
            (
                Jsonb(["MISSING_MARKET_LINK"]),
                Jsonb({"final_state": "NO_TRADE", "risk_flags": ["MISSING_MARKET_LINK"]}),
                ids["thesis_id"],
            ),
        )
        conn.execute(
            """
            UPDATE signal_market_links
            SET matched_side = %s,
                side_source = 'token_id',
                side_confidence = 0.95,
                link_evidence_json = link_evidence_json || %s,
                link_confidence = 0.95,
                confidence = 0.95,
                link_status = 'confirmed',
                is_review_required = false
            WHERE signal_id = %s
            """,
            (side, Jsonb({"matched_side": side}), ids["signal_id"]),
        )
    PaperEligibilityService().evaluate_candidates(limit=10)
    return ids


def test_system_off_blocks_post_side_readiness(postgres_test_schema) -> None:
    _prepare()
    _seed_post_side_candidate("off")
    SystemPowerService().turn_off(actor="test", reason="post_side_off")

    result = PostSideRiskExitReadinessService().run_recovery(cycle_id="off-cycle", limit=10)

    assert result["status"] == "BLOCKED"
    assert result["error_message"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "post_side_risk_exit_recovery_runs") == 1
        assert _count(conn, "paper_intents") == 0


def test_candidate_with_side_but_missing_orderbook_remains_blocked(postgres_test_schema) -> None:
    _prepare()
    _seed_post_side_candidate("missing-orderbook", orderbook=False)

    result = PostSideRiskExitReadinessService().run_recovery(cycle_id="missing-orderbook-cycle", limit=10)

    assert result["status"] == "OK"
    assert result["risk_approved_after"] == 0
    assert result["exit_ready_after"] == 0
    assert result["eligible_after"] == 0
    trace = result["metadata"]["trace_after"][0]
    assert trace["exact_next_blocker"] in {"THESIS_NOT_COMPLETE", "MISSING_FRESH_ORDERBOOK"}
    with DatabaseConnectionFactory().connect() as conn:
        thesis = conn.execute("SELECT status, missing_evidence FROM thesis_profiles").fetchone()
        assert thesis["status"] == "INCOMPLETE"
        assert "MISSING_FRESH_ORDERBOOK" in thesis["missing_evidence"]


def test_candidate_with_side_fresh_orderbook_and_binding_reaches_risk_exit_eligibility(postgres_test_schema) -> None:
    _prepare()
    _seed_post_side_candidate("ready")

    result = PostSideRiskExitReadinessService().run_recovery(cycle_id="ready-cycle", limit=10)

    assert result["status"] == "OK"
    assert result["thesis_recovered"] == 1
    assert result["risk_approved_after"] == 1
    assert result["exit_ready_after"] == 1
    assert result["eligible_after"] == 1
    assert result["paper_intents_after"] == 0
    assert result["paper_positions_delta"] == 0
    assert result["live_orders_delta"] == 0
    assert result["real_orders_delta"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        thesis = conn.execute("SELECT status, side, missing_evidence FROM thesis_profiles").fetchone()
        risk = conn.execute(
            """
            SELECT decision, risk_approved, blockers
            FROM risk_decisions
            WHERE risk_decision_id = 'risk_thesis-ready'
            """
        ).fetchone()
        exit_plan = conn.execute(
            """
            SELECT status, paper_exit_ready, target_exit, stop_loss
            FROM exit_plans
            WHERE risk_decision_ref = 'risk_thesis-ready'
            """
        ).fetchone()
        candidate = conn.execute(
            """
            SELECT status, side, risk_approved, exit_ready
            FROM paper_eligibility_candidates
            WHERE risk_decision_id = 'risk_thesis-ready'
            """
        ).fetchone()
    assert thesis["status"] == "COMPLETE"
    assert thesis["side"] == "YES"
    assert thesis["missing_evidence"] == []
    assert risk["decision"] == "APPROVE"
    assert risk["risk_approved"] is True
    assert risk["blockers"] == []
    assert exit_plan["status"] == "COMPLETE"
    assert exit_plan["paper_exit_ready"] is True
    assert exit_plan["target_exit"] is not None
    assert exit_plan["stop_loss"] is not None
    assert candidate["status"] == "ELIGIBLE"
    assert candidate["side"] == "YES"
    assert candidate["risk_approved"] is True
    assert candidate["exit_ready"] is True


def test_post_side_recovery_is_idempotent_for_cycle(postgres_test_schema) -> None:
    _prepare()
    _seed_post_side_candidate("idempotent")

    first = PostSideRiskExitReadinessService().run_recovery(cycle_id="idem-cycle", limit=10)
    second = PostSideRiskExitReadinessService().run_recovery(cycle_id="idem-cycle", limit=10)

    assert first["status"] == "OK"
    assert second["idempotent"] is True
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "post_side_risk_exit_recovery_runs") == 1
        assert _count(conn, "paper_intents") == 0


def _count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
