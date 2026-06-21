from __future__ import annotations

from app.control_center.paper_simulation import PaperSimulationActionRequest, PaperSimulationControlService
from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService, _strict_actionability_blockers, _strict_actionability_by_candidate
from app.services.system_power import SystemPowerService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate, table_exists


def test_strict_actionability_guard_blocks_ineligible_paper_on_candidate() -> None:
    rows = [{"eligibility_id": "candidate-strict", "market_id": "market-paper", "side": "YES"}]

    items = _strict_actionability_by_candidate(
        _FakePaperActionability(qualified=False),
        rows,
        connection_factory=DatabaseConnectionFactory(),
    )
    blockers = _strict_actionability_blockers(rows[0], items["candidate-strict"])

    assert "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED" in blockers
    assert "RISK_REVIEW" in blockers


def test_strict_actionability_guard_allows_qualified_paper_on_candidate() -> None:
    rows = [{"eligibility_id": "candidate-strict-ok", "market_id": "market-paper", "side": "YES"}]

    items = _strict_actionability_by_candidate(
        _FakePaperActionability(qualified=True),
        rows,
        connection_factory=DatabaseConnectionFactory(),
    )
    blockers = _strict_actionability_blockers(rows[0], items["candidate-strict-ok"])

    assert blockers == set()


def test_paper_simulation_off_blocks_paper_intent_creation(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="paper_off_boundary")
    seed_eligible_candidate("paper-off-boundary")

    result = PaperIntentGateService().build_intents(limit=10, write_intents=True, write_no_trade=True)

    assert result["status"] == "BLOCKED"
    assert result["paper_intents_created"] == 0
    assert result["paper_intents_updated"] == 0
    assert result["error_summary"] == "PAPER_SIMULATION_OFF_NO_INTENT_CREATED"
    assert any(
        "PAPER_SIMULATION_OFF_NO_INTENT_CREATED" in record["blockers"]
        for record in result["no_trade_records"]
    )
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_intents") == 0
        assert _count(conn, "no_trade_log") >= 1


def test_paper_simulation_on_allows_canonical_paper_intent_creation(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="paper_on_boundary")
    PaperSimulationControlService().enable(PaperSimulationActionRequest(actor="test", reason="unit paper on"))
    seed_eligible_candidate("paper-on-boundary")

    result = PaperIntentGateService(paper_actionability=_FakePaperActionability(qualified=True)).build_intents(limit=10, write_intents=True, write_no_trade=True)

    assert result["status"] == "OK"
    assert result["paper_intents_created"] == 1
    assert result["orders_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT paper_only, live, execution_allowed FROM paper_intents").fetchone()
    assert row["paper_only"] is True
    assert row["live"] is False
    assert row["execution_allowed"] is False


def test_paper_simulation_on_still_blocks_without_strict_actionability(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    SystemPowerService().turn_on(actor="test", reason="paper_on_strict_boundary")
    PaperSimulationControlService().enable(PaperSimulationActionRequest(actor="test", reason="unit paper on strict"))
    seed_eligible_candidate("paper-on-not-strict")

    result = PaperIntentGateService(paper_actionability=_FakePaperActionability(qualified=False)).build_intents(limit=10, write_intents=True, write_no_trade=True)

    assert result["status"] == "OK"
    assert result["paper_intents_created"] == 0
    assert result["paper_intents_updated"] == 0
    assert any(
        "STRICT_PAPER_ACTIONABILITY_NOT_QUALIFIED" in record["blockers"]
        for record in result["no_trade_records"]
    )
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_intents") == 0
        assert _count(conn, "no_trade_log") >= 1


class _FakePaperActionability:
    def __init__(self, *, qualified: bool) -> None:
        self.qualified = qualified

    def list_actionability(self, *, limit: int = 50, offset: int = 0, candidate_id: str | None = None) -> dict:
        item = _strict_item(candidate_id or "candidate", qualified=self.qualified)
        return {"data": {"items": [item]}}


def _strict_item(candidate_id: str, *, qualified: bool) -> dict:
    return {
        "candidate_id": candidate_id,
        "market_id": "market-paper",
        "side": "YES",
        "token_id": "token-yes",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED" if qualified else "NOT_ACTIONABLE_RISK_REVIEW",
        "paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED" if qualified else "NOT_ACTIONABLE_RISK_REVIEW",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "risk_gate_state": "RISK_SUPPORT" if qualified else "RISK_REVIEW",
        "capital_gate_state": "CAPITAL_OK",
        "exit_gate_state": "EXIT_READY",
        "exit_readiness_state": "EXIT_READY",
        "source_refresh_cycle_id": "cycle-test",
        "thesis_id": "thesis-test",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "MISPRICING_REVERSION_WINDOW",
        "joined_trade_thesis": {
            "thesis_id": "thesis-test",
            "candidate_id": candidate_id,
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "cycle-test",
            "status": "THESIS_SUPPORTED",
        },
        "risk_capital_gate_trace": {"classification": "PASSED"},
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {"actionability_class": "ACTIONABLE_SMALL_PAPER", "allow_paper_intent": True, "critical_blockers": []},
        "stale_gate_selected": False,
        "stale_sources_blocking": [],
        "blockers": [] if qualified else ["RISK_REVIEW"],
    }


def _count(conn, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
