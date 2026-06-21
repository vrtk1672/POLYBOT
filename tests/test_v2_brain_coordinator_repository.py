from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")


def _brain_output(brain: str, output_type: str, recommendation: str, **extra) -> dict[str, object]:
    payload = {
        "brain": brain,
        "output_type": output_type,
        "recommendation": recommendation,
        "status": "ACTIVE",
        **extra,
    }
    return BrainOutputService().create_brain_output(payload)


def test_create_decision_persists_inputs_and_conflicts(postgres_test_schema) -> None:
    _clear()
    opportunity = _brain_output("opportunity", "OPPORTUNITY_HINT", "OPPORTUNITY_HINT", market_id="m1", confidence=0.7)
    risk = _brain_output("risk", "RISK_WARNING", "CAUTION", market_id="m1", confidence=0.8, risk_flags=["risk_high"])

    created = BrainCoordinatorService().coordinate_outputs(
        [str(opportunity["brain_output_id"]), str(risk["brain_output_id"])],
        market_id="m1",
    )

    assert created["final_state"] == "RISK_BLOCKED"
    assert created["execution_allowed"] is False
    assert len(created["inputs"]) == 2
    assert len(created["conflicts"]) == 1

    fetched = BrainCoordinatorService().get_decision(created["coordinator_decision_id"])
    assert fetched is not None
    assert fetched["inputs"][0]["coordinator_decision_id"] == created["coordinator_decision_id"]
    assert fetched["conflicts"][0]["conflict_key"] == "opportunity_positive_vs_risk_high"


def test_list_recent_by_market_and_position(postgres_test_schema) -> None:
    _clear()
    output = _brain_output("memory", "MEMORY_NOTE", "WATCH", market_id="m-list", position_id="p-list")
    BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    service = BrainCoordinatorService()
    assert len(service.list_recent_decisions()) == 1
    assert len(service.list_decisions_by_market("m-list")) == 1
    assert len(service.list_decisions_by_position("p-list")) == 1


def test_summary_counts_and_execution_allowed_zero(postgres_test_schema) -> None:
    _clear()
    output = _brain_output("no_trade", "NO_TRADE_HINT", "NO_TRADE", confidence=0.9)
    BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    summary = BrainCoordinatorService().get_coordinator_summary()

    assert summary["mock_data"] is False
    assert summary["total_decisions_24h"] == 1
    assert summary["no_trade_decisions_24h"] == 1
    assert summary["execution_allowed_count"] == 0
    assert summary["decisions_requiring_governor"] == 1


def test_coordinator_store_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    BrainCoordinatorService().coordinate_outputs([])

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
