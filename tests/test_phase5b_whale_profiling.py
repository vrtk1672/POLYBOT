from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.query.whale_profile_query_service import WhaleProfileQueryService
from app.services.whale_profiling import PROFILER_VERSION, WhaleProfileRunResult, WhaleProfilingService, main as profiling_main
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
            "side_or_outcome": side_or_outcome,
        },
    )


def _seed_wallet_events(wallet_address: str, items: list[ManualWhaleEventItem]) -> None:
    service = WhaleScannerService()
    result = service.scan_manual_items(items, source_ref=f"seed-{wallet_address}")
    assert result is not None


def test_whale_profiling_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"whale_profile_runs", "whale_profiles"} <= table_names


def test_successful_whale_profiling_run_persists_correctly(postgres_test_schema) -> None:
    wallet_address = _wallet("profile")
    now = datetime.now(UTC)
    _seed_wallet_events(
        wallet_address,
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=now - timedelta(hours=3),
                side_or_outcome="YES",
                size=1500.0,
                notional=20000.0,
                price=0.60,
                transaction_ref="tx-1",
                position_effect="OPEN",
            ),
            _item(
                wallet_address=wallet_address,
                market_id="market-1",
                event_timestamp=now,
                side_or_outcome="YES",
                size=1400.0,
                notional=18000.0,
                price=0.58,
                transaction_ref="tx-2",
                position_effect="CLOSE",
            ),
        ],
    )

    service = WhaleProfilingService()
    result = service.profile_wallets([wallet_address], source_type="phase5b_test", source_ref="phase5b")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM whale_profile_runs WHERE id = %s LIMIT 1",
            (result.whale_profile_run_id,),
        ).fetchone()
        profile_row = conn.execute(
            "SELECT * FROM whale_profiles WHERE whale_profile_run_id = %s LIMIT 1",
            (result.whale_profile_run_id,),
        ).fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert run_row["profiler_version"] == PROFILER_VERSION
    assert profile_row is not None
    assert profile_row["wallet_address"] == wallet_address.lower()
    assert profile_row["total_events"] == 2
    assert profile_row["entry_count"] == 1
    assert profile_row["exit_count"] == 1
    assert float(profile_row["average_hold_time"]) == pytest.approx(3.0, rel=1e-6)
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_metric_computation_behaves_as_expected(postgres_test_schema) -> None:
    wallet_address = _wallet("metrics")
    now = datetime.now(UTC)
    _seed_wallet_events(
        wallet_address,
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-a",
                event_timestamp=now - timedelta(hours=6),
                side_or_outcome="YES",
                size=1200.0,
                notional=15000.0,
                price=0.55,
                transaction_ref="tx-a1",
                position_effect="OPEN",
            ),
            _item(
                wallet_address=wallet_address,
                market_id="market-a",
                event_timestamp=now - timedelta(hours=4),
                side_or_outcome="YES",
                size=1250.0,
                notional=15250.0,
                price=0.56,
                transaction_ref="tx-a2",
                position_effect="INCREASE",
            ),
            _item(
                wallet_address=wallet_address,
                market_id="market-b",
                event_timestamp=now - timedelta(hours=2),
                side_or_outcome="NO",
                size=2000.0,
                notional=25000.0,
                price=0.62,
                transaction_ref="tx-b1",
                position_effect="REVERSE",
                previous_side_or_outcome="YES",
            ),
        ],
    )

    service = WhaleProfilingService()
    result = service.profile_wallets([wallet_address], source_type="phase5b_test")
    assert result is not None

    queries = WhaleProfileQueryService()
    profile = queries.get_whale_profile_details(wallet_address=wallet_address.lower())
    assert profile is not None
    assert profile["reversal_candidate_count"] == 1
    assert profile["active_markets_count"] == 2
    assert float(profile["largest_size"]) == pytest.approx(2000.0, rel=1e-6)
    assert float(profile["average_size"]) == pytest.approx((1200.0 + 1250.0 + 2000.0) / 3.0, rel=1e-6)
    specialties = profile["market_specialties_json"]
    assert specialties[0]["market_id"] == "market-a"


def test_follow_value_baseline_and_noise_timing_metrics_are_persisted(postgres_test_schema) -> None:
    good_wallet = _wallet("good")
    noisy_wallet = _wallet("noisy")
    now = datetime.now(UTC)

    _seed_wallet_events(
        good_wallet,
        [
            _item(wallet_address=good_wallet, market_id="m1", event_timestamp=now - timedelta(hours=9), side_or_outcome="YES", size=1800.0, notional=22000.0, price=0.60, transaction_ref="g1", position_effect="OPEN"),
            _item(wallet_address=good_wallet, market_id="m1", event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=1750.0, notional=21000.0, price=0.61, transaction_ref="g2", position_effect="INCREASE"),
            _item(wallet_address=good_wallet, market_id="m1", event_timestamp=now - timedelta(hours=3), side_or_outcome="YES", size=1700.0, notional=20500.0, price=0.62, transaction_ref="g3", position_effect="CLOSE"),
        ],
    )
    _seed_wallet_events(
        noisy_wallet,
        [
            _item(wallet_address=noisy_wallet, market_id="m2", event_timestamp=now - timedelta(hours=10), side_or_outcome=None, size=1300.0, notional=15000.0, price=None, transaction_ref="n1", position_effect=None),
            _item(wallet_address=noisy_wallet, market_id="m3", event_timestamp=now - timedelta(hours=5), side_or_outcome="NO", size=1350.0, notional=15500.0, price=0.54, transaction_ref="n2", position_effect="REVERSE", previous_side_or_outcome="YES"),
            _item(wallet_address=noisy_wallet, market_id="m4", event_timestamp=now - timedelta(hours=1), side_or_outcome=None, size=1400.0, notional=16000.0, price=None, transaction_ref="n3", position_effect=None),
        ],
    )

    service = WhaleProfilingService()
    result = service.profile_wallets([good_wallet, noisy_wallet], source_type="phase5b_test")
    assert result is not None

    queries = WhaleProfileQueryService()
    good_profile = queries.get_whale_profile_details(wallet_address=good_wallet.lower())
    noisy_profile = queries.get_whale_profile_details(wallet_address=noisy_wallet.lower())
    assert good_profile is not None
    assert noisy_profile is not None
    assert float(good_profile["timing_consistency_score"]) > float(noisy_profile["timing_consistency_score"])
    assert float(good_profile["noise_score"]) < float(noisy_profile["noise_score"])
    assert float(good_profile["follow_value_baseline"]) > float(noisy_profile["follow_value_baseline"])


def test_honest_handling_of_sparse_history(postgres_test_schema) -> None:
    wallet_address = _wallet("sparse")
    _seed_wallet_events(
        wallet_address,
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-sparse",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1500.0,
                notional=18000.0,
                price=0.64,
                transaction_ref="tx-sparse",
                position_effect="OPEN",
            )
        ],
    )

    service = WhaleProfilingService()
    result = service.profile_wallets([wallet_address], source_type="phase5b_test")
    assert result is not None
    assert result.status == "COMPLETED"

    queries = WhaleProfileQueryService()
    profile = queries.get_whale_profile_details(wallet_address=wallet_address.lower())
    assert profile is not None
    assert profile["profile_status"] == "SPARSE_HISTORY"
    assert profile["average_hold_time"] is None


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    wallet_address = _wallet("query")
    _seed_wallet_events(
        wallet_address,
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-query",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1550.0,
                notional=19000.0,
                price=0.66,
                transaction_ref="tx-query",
                position_effect="OPEN",
            )
        ],
    )
    service = WhaleProfilingService()
    result = service.profile_wallets([wallet_address], source_type="phase5b_test")
    assert result is not None

    queries = WhaleProfileQueryService()
    summary = queries.get_whale_profile_run_summary(result.whale_profile_run_id)
    assert summary is not None
    assert summary["profile_count"] == 1

    rows = queries.list_whale_profiles_for_run(result.whale_profile_run_id)
    assert len(rows) == 1
    profile_id = str(rows[0]["id"])
    details = queries.get_whale_profile_details(whale_profile_id=profile_id)
    assert details is not None
    assert details["wallet_address"] == wallet_address.lower()

    top_rows = queries.list_top_whale_profiles(limit=500, order_by="follow_value_baseline")
    assert any(str(row["wallet_address"]) == wallet_address.lower() for row in top_rows)

    comparison = queries.compare_whale_profile_to_registry(wallet_address.lower())
    assert comparison is not None
    assert comparison["profile"] is not None
    assert comparison["registry"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeWhaleProfilingService:
        def profile_wallets(self, wallet_addresses, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["wallet_addresses"] = wallet_addresses
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return WhaleProfileRunResult(
                whale_profile_run_id="profile-run-cli-test",
                status="COMPLETED",
                input_count=len(wallet_addresses),
                success_count=len(wallet_addresses),
                failure_count=0,
            )

        def profile_active_wallets(self, *, limit: int = 100, source_ref: str | None = None):  # noqa: ANN001
            called["limit"] = limit
            called["source_ref"] = source_ref
            return WhaleProfileRunResult(
                whale_profile_run_id="profile-run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.whale_profiling.WhaleProfilingService", FakeWhaleProfilingService)

    exit_code = profiling_main(["--wallet-addresses", "0xabc", "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["wallet_addresses"] == ["0xabc"]
    assert called["source_ref"] == "cli-test"
    assert "profile-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    wallet_address = _wallet("safe")
    _seed_wallet_events(
        wallet_address,
        [
            _item(
                wallet_address=wallet_address,
                market_id="market-safe",
                event_timestamp=datetime.now(UTC),
                side_or_outcome="YES",
                size=1600.0,
                notional=20000.0,
                price=0.67,
                transaction_ref="tx-safe",
                position_effect="OPEN",
            )
        ],
    )
    service = WhaleProfilingService()
    service.profile_wallets([wallet_address], source_type="phase5b_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
