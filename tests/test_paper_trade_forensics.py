from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.main import create_app
from app.services.paper_capital import PaperCapitalService
from app.services.paper_trade_forensics import PaperTradeForensicsService
from app.services.paper_lineage_quarantine import PaperLineageQuarantineService
from app.services.paper_exit_loop import PaperExitLoopService
from test_paper_exit_loop import _Governor, _Power, _prepare, _seed_position
from test_paper_lineage_quarantine import _seed_legacy_position


def test_trade_forensics_endpoint_returns_paper_positions(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper/trade-forensics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["active_count"] == 1
    assert payload["active_trades"][0]["paper_position_id"] == position_id


def test_forensics_links_fill_order_intent_close_and_ledger(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        capital.lock_on_fill(
            conn,
            paper_intent_id=position["payload_json"]["source_intent_id"],
            paper_order_id=position["payload_json"]["paper_order_id"],
            paper_fill_id=position["payload_json"]["paper_fill_id"],
            paper_position_id=position_id,
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
        )
    PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="forensics-close")

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["response_status"] == "OK"
    assert trace["status"] == "CLOSED"
    assert trace["paper_fill_id"].startswith("paper-fill-")
    assert trace["paper_order"] is not None
    assert trace["paper_intent"] is not None
    assert trace["paper_close"]["exit_reason"] == "TAKE_PROFIT"
    assert trace["exit_price"] == 0.6
    assert trace["realized_pnl"] == 1.0
    assert any(row["event_type"] == "OPEN" for row in trace["ledger_rows"]["paper_trade_ledger"])
    assert any(row["event_type"] == "CLOSE" for row in trace["ledger_rows"]["paper_trade_ledger"])


def test_forensics_shows_capital_lock_release_and_position_status(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        capital.lock_on_fill(
            conn,
            paper_intent_id=position["payload_json"]["source_intent_id"],
            paper_order_id=position["payload_json"]["paper_order_id"],
            paper_fill_id=position["payload_json"]["paper_fill_id"],
            paper_position_id=position_id,
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
        )
    PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="forensics-capital")

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["capital_lock_row"]["event_type"] == "CAPITAL_LOCKED_ON_FILL"
    assert trace["capital_release_row"]["event_type"] == "CAPITAL_RELEASED_ON_CLOSE"
    assert trace["active_capital_lock"] == 0.0
    assert trace["expected_exposure"] == 0.0
    assert trace["capital_reconciliation_status"] == "OK"


def test_quarantined_rows_are_shown_separately(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_legacy_position()
    PaperLineageQuarantineService(system_power=_Power(False)).run_quarantine(actor="test")
    client = TestClient(create_app())

    payload = client.get("/dashboard/api/v2/paper/trade-forensics").json()

    assert payload["active_count"] == 0
    assert payload["legacy_quarantined_count"] == 1
    quarantined = payload["legacy_quarantined"][0]
    assert quarantined["paper_position_id"] == position_id
    assert quarantined["quarantine_status"]["status"] == "LEGACY_QUARANTINED"


def test_missing_links_are_reported_not_faked(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_legacy_position()

    trace = PaperTradeForensicsService().get_trade(position_id)
    missing = {(item["table"], item["field"], item["reason"]) for item in trace["missing_links"]}

    assert ("paper_positions", "payload_json.paper_fill_id", "FIELD_EMPTY") in missing
    assert trace["paper_fill"] is None
    assert trace["paper_intent"] is None
    assert trace["paper_order"] is None


def test_trade_forensics_read_only_does_not_mutate_trading_tables(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position()
    before = _counts()

    PaperTradeForensicsService().list_trades()
    PaperTradeForensicsService().get_trade(position_id)

    assert _counts() == before


def _counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_trade_ledger")
        }
