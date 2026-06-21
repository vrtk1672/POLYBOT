from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.query.whale_query_service import WhaleQueryService
from app.services.whale_scanner import SCANNER_VERSION, ManualWhaleEventItem, WhaleScannerService, main as whale_main


def _item(
    *,
    wallet_address: str,
    market_id: str,
    event_timestamp: datetime,
    side_or_outcome: str | None,
    size: float,
    notional: float | None,
    price: float | None,
    transaction_ref: str | None,
    position_effect: str | None,
    previous_side_or_outcome: str | None = None,
) -> ManualWhaleEventItem:
    return ManualWhaleEventItem(
        wallet_address=wallet_address,
        market_id=market_id,
        event_timestamp=event_timestamp,
        side_or_outcome=side_or_outcome,
        size=size,
        notional=notional,
        price=price,
        transaction_ref=transaction_ref,
        source_type="MANUAL_IMPORT",
        position_effect=position_effect,
        previous_side_or_outcome=previous_side_or_outcome,
        source_payload_json={
            "wallet_address": wallet_address,
            "market_id": market_id,
            "position_effect": position_effect,
            "side_or_outcome": side_or_outcome,
        },
    )


def _wallet(label: str) -> str:
    return f"0x{label}{uuid4().hex[:8]}"


def test_whale_scanner_migrations_create_tables(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    table_names = {row["table_name"] for row in tables}
    assert {"whale_scan_runs", "whale_events", "whale_registry"} <= table_names


def test_successful_whale_scan_run_persists_correctly(postgres_test_schema) -> None:
    wallet_address = _wallet("whaleone")
    service = WhaleScannerService()
    result = service.scan_manual_items(
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-psg-win",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1500.0,
                notional=18000.0,
                price=0.62,
                transaction_ref="tx-1",
                position_effect="OPEN",
            )
        ],
        source_ref="phase5a-test",
    )
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM whale_scan_runs WHERE id = %s LIMIT 1",
            (result.whale_scan_run_id,),
        ).fetchone()
        event_row = conn.execute(
            "SELECT * FROM whale_events WHERE whale_scan_run_id = %s LIMIT 1",
            (result.whale_scan_run_id,),
        ).fetchone()
        registry_row = conn.execute(
            "SELECT * FROM whale_registry WHERE wallet_address = %s LIMIT 1",
            (wallet_address.lower(),),
        ).fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert run_row["scanner_version"] == SCANNER_VERSION
    assert event_row is not None
    assert event_row["wallet_address"] == wallet_address.lower()
    assert event_row["event_direction_class"] == "ENTRY"
    assert event_row["detection_reason_code"] == "position_effect_entry"
    assert registry_row is not None
    assert registry_row["wallet_address"] == wallet_address.lower()
    assert registry_row["registry_status"] == "ACTIVE"
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_classification_behaves_as_expected(postgres_test_schema) -> None:
    entry_wallet = _wallet("entry")
    exit_wallet = _wallet("exit")
    unknown_wallet = _wallet("unknown")
    service = WhaleScannerService()
    result = service.scan_manual_items(
        [
            _item(
                wallet_address=entry_wallet,
                market_id="market-1",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1200.0,
                notional=15000.0,
                price=0.55,
                transaction_ref="tx-entry",
                position_effect="OPEN",
            ),
            _item(
                wallet_address=exit_wallet,
                market_id="market-1",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1400.0,
                notional=16000.0,
                price=0.60,
                transaction_ref="tx-exit",
                position_effect="CLOSE",
            ),
            _item(
                wallet_address=unknown_wallet,
                market_id="market-2",
                event_timestamp=datetime.now(UTC),
                side_or_outcome=None,
                size=1500.0,
                notional=11000.0,
                price=None,
                transaction_ref="tx-unknown",
                position_effect=None,
            ),
        ]
    )
    assert result is not None
    assert result.success_count == 3

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT wallet_address, event_direction_class FROM whale_events ORDER BY created_at ASC"
        ).fetchall()
    by_wallet = {str(row["wallet_address"]): str(row["event_direction_class"]) for row in rows}
    assert by_wallet[entry_wallet.lower()] == "ENTRY"
    assert by_wallet[exit_wallet.lower()] == "EXIT"
    assert by_wallet[unknown_wallet.lower()] == "UNKNOWN"


def test_registry_upsert_works_across_multiple_events_for_same_wallet(postgres_test_schema) -> None:
    wallet_address = _wallet("repeat")
    service = WhaleScannerService()
    first_seen = datetime.now(UTC) - timedelta(hours=1)
    second_seen = datetime.now(UTC)
    result = service.scan_manual_items(
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=first_seen,
                side_or_outcome="YES",
                size=1300.0,
                notional=17000.0,
                price=0.63,
                transaction_ref="tx-1",
                position_effect="OPEN",
            ),
            _item(
                wallet_address=wallet_address,
                market_id="market-2",
                event_timestamp=second_seen,
                side_or_outcome="NO",
                size=1400.0,
                notional=17500.0,
                price=0.59,
                transaction_ref="tx-2",
                position_effect="REVERSE",
                previous_side_or_outcome="YES",
            ),
        ]
    )
    assert result is not None
    assert result.success_count == 2

    queries = WhaleQueryService()
    registry = queries.get_whale_registry_entry(wallet_address.lower())
    assert registry is not None
    assert registry["total_events"] == 2
    assert registry["last_market_id"] == "market-2"
    assert registry["last_event_direction_class"] == "REVERSAL_CANDIDATE"
    assert registry["registry_status"] == "WATCHLIST"


def test_bad_input_is_handled_honestly(postgres_test_schema) -> None:
    wallet_address = _wallet("toosmall")
    service = WhaleScannerService()
    result = service.scan_manual_items(
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=10.0,
                notional=50.0,
                price=0.51,
                transaction_ref="tx-small",
                position_effect="OPEN",
            )
        ]
    )
    assert result is not None
    assert result.status == "COMPLETED_WITH_ERRORS"
    assert result.failure_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM whale_events WHERE wallet_address = %s",
            (wallet_address.lower(),),
        ).fetchall()
        registry_rows = conn.execute(
            "SELECT * FROM whale_registry WHERE wallet_address = %s",
            (wallet_address.lower(),),
        ).fetchall()
    assert rows == []
    assert registry_rows == []


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    wallet_address = _wallet("query")
    service = WhaleScannerService()
    result = service.scan_manual_items(
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1550.0,
                notional=19000.0,
                price=0.66,
                transaction_ref="tx-query",
                position_effect="OPEN",
            )
        ]
    )
    assert result is not None

    queries = WhaleQueryService()
    summary = queries.get_whale_scan_run_summary(result.whale_scan_run_id)
    assert summary is not None
    assert summary["event_count"] == 1
    assert summary["direction_counts"]["ENTRY"] == 1

    rows = queries.list_whale_events_for_run(result.whale_scan_run_id)
    assert len(rows) == 1
    event_id = str(rows[0]["id"])
    details = queries.get_whale_event_details(event_id)
    assert details is not None
    assert details["transaction_ref"] == "tx-query"

    by_wallet = queries.list_whale_events_for_wallet(wallet_address.lower(), limit=5)
    assert len(by_wallet) == 1

    registry = queries.get_whale_registry_entry(wallet_address.lower())
    assert registry is not None

    active_rows = queries.list_active_whale_registry(limit=5)
    assert any(str(row["wallet_address"]) == wallet_address.lower() for row in active_rows)


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    run_migrations()
    input_path = tmp_path / "whales.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "wallet_address": "0xCLI",
                    "market_id": "market-1",
                    "event_timestamp": "2026-04-19T10:00:00Z",
                    "side_or_outcome": "YES",
                    "size": 1500.0,
                    "notional": 19000.0,
                    "price": 0.61,
                    "transaction_ref": "tx-cli",
                    "position_effect": "OPEN",
                    "source_payload_json": {"seeded": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    called: dict[str, object] = {}

    class FakeWhaleScannerService:
        def scan_manual_items(self, items, *, source_ref: str | None = None):  # noqa: ANN001
            called["item_count"] = len(items)
            called["source_ref"] = source_ref
            return type(
                "Result",
                (),
                {
                    "whale_scan_run_id": "whale-run-cli-test",
                    "status": "COMPLETED",
                    "input_count": len(items),
                    "success_count": len(items),
                    "failure_count": 0,
                },
            )()

    monkeypatch.setattr("app.services.whale_scanner.WhaleScannerService", FakeWhaleScannerService)

    exit_code = whale_main(["--manual-import-json", str(input_path), "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["item_count"] == 1
    assert called["source_ref"] == "cli-test"
    assert "whale-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    wallet_address = _wallet("safe")
    service = WhaleScannerService()
    service.scan_manual_items(
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1400.0,
                notional=18000.0,
                price=0.64,
                transaction_ref="tx-safe",
                position_effect="OPEN",
            )
        ]
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
