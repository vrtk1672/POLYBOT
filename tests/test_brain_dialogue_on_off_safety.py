from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_dialogue_sources


def test_brain_dialogue_is_observational_and_does_not_create_trading_artifacts(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    with DatabaseConnectionFactory().connect() as conn:
        before = _counts(conn)

    BrainDialogueService().materialize_recent(limit_per_source=20)

    with DatabaseConnectionFactory().connect() as conn:
        after = _counts(conn)
    assert after["paper_orders"] == before["paper_orders"]
    assert after["paper_fills"] == before["paper_fills"]
    assert after["paper_positions"] == before["paper_positions"]
    assert after["orders_v2"] == before["orders_v2"]
    assert after["fills_v2"] == before["fills_v2"]
    assert after["positions"] == before["positions"]


def test_system_off_allows_only_system_power_dialogue(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    SystemPowerService().turn_off(actor="test", reason="dialogue_off_safety")

    BrainDialogueService().materialize_recent(limit_per_source=20)

    feed = BrainDialogueService().list_events(limit=100)
    assert feed["events"]
    assert {event["component"] for event in feed["events"]} == {"SystemPower"}


def _counts(conn) -> dict[str, int]:
    return {table: _count(conn, table) for table in ("paper_orders", "paper_fills", "paper_positions", "orders_v2", "fills_v2", "positions")}


def _count(conn, table: str) -> int:
    if not conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
