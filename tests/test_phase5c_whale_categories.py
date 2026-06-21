from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.query.whale_category_query_service import WhaleCategoryQueryService
from app.services.whale_categories import CATEGORIZER_VERSION, WhaleCategoryRunResult, WhaleCategoryService, main as category_main
from app.services.whale_profiling import WhaleProfilingService
from app.services.whale_scanner import ManualWhaleEventItem, WhaleScannerService


def _wallet(label: str) -> str:
    return f"0x{label}{uuid4().hex[:8]}"


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
        },
    )


def _seed_profile(wallet_address: str, items: list[ManualWhaleEventItem]) -> None:
    scanner = WhaleScannerService()
    scan_result = scanner.scan_manual_items(items, source_ref=f"seed-{wallet_address}")
    assert scan_result is not None
    profiler = WhaleProfilingService()
    profile_result = profiler.profile_wallets([wallet_address], source_type="seed_profile")
    assert profile_result is not None


def test_whale_categories_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"whale_category_runs", "whale_categories"} <= table_names


def test_successful_whale_categorization_run_persists_correctly(postgres_test_schema) -> None:
    wallet_address = _wallet("smart")
    now = datetime.now(UTC)
    _seed_profile(
        wallet_address,
        [
            _item(wallet_address=wallet_address, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=9), side_or_outcome="YES", size=1850.0, notional=23000.0, price=0.60, transaction_ref="t1", position_effect="OPEN"),
            _item(wallet_address=wallet_address, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=1800.0, notional=22000.0, price=0.61, transaction_ref="t2", position_effect="INCREASE"),
            _item(wallet_address=wallet_address, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=3), side_or_outcome="YES", size=1750.0, notional=21500.0, price=0.62, transaction_ref="t3", position_effect="CLOSE"),
        ],
    )

    service = WhaleCategoryService()
    result = service.categorize_wallets([wallet_address], source_type="phase5c_test", source_ref="phase5c")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM whale_category_runs WHERE id = %s LIMIT 1",
            (result.whale_category_run_id,),
        ).fetchone()
        category_row = conn.execute(
            "SELECT * FROM whale_categories WHERE whale_category_run_id = %s LIMIT 1",
            (result.whale_category_run_id,),
        ).fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert run_row["categorizer_version"] == CATEGORIZER_VERSION
    assert category_row is not None
    assert category_row["wallet_address"] == wallet_address.lower()
    assert category_row["primary_category"] in {"SMART_WHALE", "SPORTS_SPECIALIST", "COPY_WORTHY"}
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_primary_secondary_assignment_behaves_as_expected(postgres_test_schema) -> None:
    sports_wallet = _wallet("sports")
    noisy_wallet = _wallet("noisy")
    late_wallet = _wallet("late")
    now = datetime.now(UTC)

    _seed_profile(
        sports_wallet,
        [
            _item(wallet_address=sports_wallet, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=8), side_or_outcome="YES", size=1800.0, notional=22000.0, price=0.60, transaction_ref="s1", position_effect="OPEN"),
            _item(wallet_address=sports_wallet, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=5), side_or_outcome="YES", size=1750.0, notional=21000.0, price=0.61, transaction_ref="s2", position_effect="INCREASE"),
            _item(wallet_address=sports_wallet, market_id="sports-psg-win", event_timestamp=now - timedelta(hours=2), side_or_outcome="YES", size=1700.0, notional=20500.0, price=0.62, transaction_ref="s3", position_effect="CLOSE"),
        ],
    )
    _seed_profile(
        noisy_wallet,
        [
            _item(wallet_address=noisy_wallet, market_id="politics-election-1", event_timestamp=now - timedelta(hours=10), side_or_outcome=None, size=1300.0, notional=15000.0, price=None, transaction_ref="n1", position_effect=None),
            _item(wallet_address=noisy_wallet, market_id="politics-election-2", event_timestamp=now - timedelta(hours=6), side_or_outcome="NO", size=1350.0, notional=15500.0, price=0.54, transaction_ref="n2", position_effect="REVERSE", previous_side_or_outcome="YES"),
            _item(wallet_address=noisy_wallet, market_id="politics-election-3", event_timestamp=now - timedelta(hours=1), side_or_outcome=None, size=1400.0, notional=16000.0, price=None, transaction_ref="n3", position_effect=None),
        ],
    )
    _seed_profile(
        late_wallet,
        [
            _item(wallet_address=late_wallet, market_id="general-market-1", event_timestamp=now - timedelta(hours=18), side_or_outcome="YES", size=1500.0, notional=19000.0, price=0.55, transaction_ref="l1", position_effect="OPEN"),
            _item(wallet_address=late_wallet, market_id="general-market-2", event_timestamp=now - timedelta(hours=7), side_or_outcome="YES", size=1525.0, notional=19200.0, price=0.56, transaction_ref="l2", position_effect="OPEN"),
            _item(wallet_address=late_wallet, market_id="general-market-3", event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=1550.0, notional=19400.0, price=0.57, transaction_ref="l3", position_effect="OPEN"),
        ],
    )

    service = WhaleCategoryService()
    result = service.categorize_wallets([sports_wallet, noisy_wallet, late_wallet], source_type="phase5c_test")
    assert result is not None

    queries = WhaleCategoryQueryService()
    sports_category = queries.get_whale_category_details(wallet_address=sports_wallet.lower())
    noisy_category = queries.get_whale_category_details(wallet_address=noisy_wallet.lower())
    late_category = queries.get_whale_category_details(wallet_address=late_wallet.lower())
    assert sports_category is not None
    assert noisy_category is not None
    assert late_category is not None

    assert sports_category["primary_category"] in {"SPORTS_SPECIALIST", "SMART_WHALE", "COPY_WORTHY"}
    assert "sports_specialization" in sports_category["category_reason_codes_json"] or "SPORTS_SPECIALIST" in sports_category["secondary_categories_json"]
    assert noisy_category["primary_category"] == "NOISY_WHALE"
    assert "high_noise" in noisy_category["category_reason_codes_json"]
    assert late_category["primary_category"] in {"LATE_CHASER", "UNCLASSIFIED"}


def test_category_confidence_and_reason_codes_persist_correctly(postgres_test_schema) -> None:
    wallet_address = _wallet("copy")
    now = datetime.now(UTC)
    _seed_profile(
        wallet_address,
        [
            _item(wallet_address=wallet_address, market_id="politics-vote-1", event_timestamp=now - timedelta(hours=9), side_or_outcome="YES", size=1800.0, notional=22000.0, price=0.60, transaction_ref="c1", position_effect="OPEN"),
            _item(wallet_address=wallet_address, market_id="politics-vote-1", event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=1825.0, notional=22500.0, price=0.61, transaction_ref="c2", position_effect="INCREASE"),
            _item(wallet_address=wallet_address, market_id="politics-vote-1", event_timestamp=now - timedelta(hours=3), side_or_outcome="YES", size=1780.0, notional=22100.0, price=0.62, transaction_ref="c3", position_effect="CLOSE"),
        ],
    )

    service = WhaleCategoryService()
    result = service.categorize_wallets([wallet_address], source_type="phase5c_test")
    assert result is not None

    queries = WhaleCategoryQueryService()
    category = queries.get_whale_category_details(wallet_address=wallet_address.lower())
    assert category is not None
    assert float(category["category_confidence"]) > 0.5
    assert len(category["category_reason_codes_json"]) >= 1
    assert category["category_reason_text"]


def test_honest_handling_of_sparse_or_ambiguous_wallets(postgres_test_schema) -> None:
    wallet_address = _wallet("sparse")
    _seed_profile(
        wallet_address,
        [
            _item(wallet_address=wallet_address, market_id="market-sparse", event_timestamp=datetime.now(UTC), side_or_outcome="YES", size=1500.0, notional=18000.0, price=0.64, transaction_ref="tx-sparse", position_effect="OPEN")
        ],
    )

    service = WhaleCategoryService()
    result = service.categorize_wallets([wallet_address], source_type="phase5c_test")
    assert result is not None

    queries = WhaleCategoryQueryService()
    category = queries.get_whale_category_details(wallet_address=wallet_address.lower())
    assert category is not None
    assert category["primary_category"] == "UNCLASSIFIED"
    assert "sparse_history" in category["category_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    wallet_address = _wallet("query")
    now = datetime.now(UTC)
    _seed_profile(
        wallet_address,
        [
            _item(wallet_address=wallet_address, market_id="sports-query-market", event_timestamp=now - timedelta(hours=4), side_or_outcome="YES", size=1600.0, notional=21000.0, price=0.60, transaction_ref="q1", position_effect="OPEN"),
            _item(wallet_address=wallet_address, market_id="sports-query-market", event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=1550.0, notional=20500.0, price=0.61, transaction_ref="q2", position_effect="CLOSE"),
        ],
    )

    service = WhaleCategoryService()
    result = service.categorize_wallets([wallet_address], source_type="phase5c_test")
    assert result is not None

    queries = WhaleCategoryQueryService()
    summary = queries.get_whale_category_run_summary(result.whale_category_run_id)
    assert summary is not None
    assert summary["category_count"] == 1

    rows = queries.list_whale_categories_for_run(result.whale_category_run_id)
    assert len(rows) == 1
    category_id = str(rows[0]["id"])
    details = queries.get_whale_category_details(whale_category_id=category_id)
    assert details is not None
    assert details["wallet_address"] == wallet_address.lower()

    by_primary = queries.list_whale_categories_by_primary(str(details["primary_category"]), limit=50)
    assert any(str(row["wallet_address"]) == wallet_address.lower() for row in by_primary)

    comparison = queries.compare_whale_category_to_profile(wallet_address.lower())
    assert comparison is not None
    assert comparison["category"] is not None
    assert comparison["profile"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeWhaleCategoryService:
        def categorize_wallets(self, wallet_addresses, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["wallet_addresses"] = wallet_addresses
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return WhaleCategoryRunResult(
                whale_category_run_id="category-run-cli-test",
                status="COMPLETED",
                input_count=len(wallet_addresses),
                success_count=len(wallet_addresses),
                failure_count=0,
            )

        def categorize_active_wallets(self, *, limit: int = 100, source_ref: str | None = None):  # noqa: ANN001
            called["limit"] = limit
            called["source_ref"] = source_ref
            return WhaleCategoryRunResult(
                whale_category_run_id="category-run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.whale_categories.WhaleCategoryService", FakeWhaleCategoryService)

    exit_code = category_main(["--wallet-addresses", "0xabc", "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["wallet_addresses"] == ["0xabc"]
    assert called["source_ref"] == "cli-test"
    assert "category-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    wallet_address = _wallet("safe")
    now = datetime.now(UTC)
    _seed_profile(
        wallet_address,
        [
            _item(wallet_address=wallet_address, market_id="sports-safe-market", event_timestamp=now - timedelta(hours=4), side_or_outcome="YES", size=1600.0, notional=21000.0, price=0.60, transaction_ref="s1", position_effect="OPEN"),
            _item(wallet_address=wallet_address, market_id="sports-safe-market", event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=1550.0, notional=20500.0, price=0.61, transaction_ref="s2", position_effect="CLOSE"),
        ],
    )

    service = WhaleCategoryService()
    service.categorize_wallets([wallet_address], source_type="phase5c_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
