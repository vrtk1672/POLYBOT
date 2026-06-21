from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.query.whale_scoring_query_service import WhaleScoringQueryService
from app.services.whale_categories import WhaleCategoryService
from app.services.whale_profiling import WhaleProfilingService
from app.services.whale_scanner import ManualWhaleEventItem, WhaleScannerService
from app.services.whale_scoring import DEFAULT_WINDOW_HOURS, SCORER_VERSION, WhaleScoringRunResult, WhaleScoringService, main as scoring_main


def _wallet(label: str) -> str:
    return f"0x{label}{uuid4().hex[:8]}"


def _market(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


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


def _seed_category(wallet_address: str, items: list[ManualWhaleEventItem]) -> None:
    scanner = WhaleScannerService()
    scan_result = scanner.scan_manual_items(items, source_ref=f"seed-{wallet_address}")
    assert scan_result is not None
    profiler = WhaleProfilingService()
    profile_result = profiler.profile_wallets([wallet_address], source_type="seed_profile")
    assert profile_result is not None
    categorizer = WhaleCategoryService()
    category_result = categorizer.categorize_wallets([wallet_address], source_type="seed_category")
    assert category_result is not None


def test_whale_scoring_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"whale_scoring_runs", "whale_market_scores"} <= table_names


def test_successful_whale_scoring_run_persists_correctly(postgres_test_schema) -> None:
    market_id = _market("sports-finals-market")
    wallet_a = _wallet("smarta")
    wallet_b = _wallet("smartb")
    now = datetime.now(UTC)

    _seed_category(
        wallet_a,
        [
            _item(wallet_address=wallet_a, market_id=market_id, event_timestamp=now - timedelta(hours=10), side_or_outcome="YES", size=2100.0, notional=29000.0, price=0.58, transaction_ref="a1", position_effect="OPEN"),
            _item(wallet_address=wallet_a, market_id=market_id, event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=2200.0, notional=30000.0, price=0.59, transaction_ref="a2", position_effect="INCREASE"),
            _item(wallet_address=wallet_a, market_id=market_id, event_timestamp=now - timedelta(hours=2), side_or_outcome="YES", size=2150.0, notional=29500.0, price=0.60, transaction_ref="a3", position_effect="CLOSE"),
        ],
    )
    _seed_category(
        wallet_b,
        [
            _item(wallet_address=wallet_b, market_id=market_id, event_timestamp=now - timedelta(hours=9), side_or_outcome="YES", size=1800.0, notional=24000.0, price=0.57, transaction_ref="b1", position_effect="OPEN"),
            _item(wallet_address=wallet_b, market_id=market_id, event_timestamp=now - timedelta(hours=4), side_or_outcome="YES", size=1850.0, notional=24500.0, price=0.58, transaction_ref="b2", position_effect="INCREASE"),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([market_id], source_type="phase5d_test", source_ref="phase5d")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM whale_scoring_runs WHERE id = %s LIMIT 1",
            (result.whale_scoring_run_id,),
        ).fetchone()
        score_row = conn.execute(
            "SELECT * FROM whale_market_scores WHERE whale_scoring_run_id = %s LIMIT 1",
            (result.whale_scoring_run_id,),
        ).fetchone()

    assert run_row is not None
    assert run_row["scorer_version"] == SCORER_VERSION
    assert score_row is not None
    assert score_row["market_id"] == market_id
    assert int(score_row["supporting_wallet_count"]) == 2
    assert len(score_row["top_supporting_wallets_json"]) >= 1


def test_deterministic_score_computation_behaves_as_expected(postgres_test_schema) -> None:
    strong_market = _market("sports-dominant-market")
    sparse_market = _market("sports-sparse-market")
    wallet_a = _wallet("doma")
    wallet_b = _wallet("domb")
    sparse_wallet = _wallet("sparse")
    now = datetime.now(UTC)

    _seed_category(
        wallet_a,
        [
            _item(wallet_address=wallet_a, market_id=strong_market, event_timestamp=now - timedelta(hours=8), side_or_outcome="YES", size=2400.0, notional=32000.0, price=0.61, transaction_ref="da1", position_effect="OPEN"),
            _item(wallet_address=wallet_a, market_id=strong_market, event_timestamp=now - timedelta(hours=4), side_or_outcome="YES", size=2350.0, notional=31800.0, price=0.62, transaction_ref="da2", position_effect="INCREASE"),
        ],
    )
    _seed_category(
        wallet_b,
        [
            _item(wallet_address=wallet_b, market_id=strong_market, event_timestamp=now - timedelta(hours=7), side_or_outcome="YES", size=2100.0, notional=28500.0, price=0.60, transaction_ref="db1", position_effect="OPEN"),
            _item(wallet_address=wallet_b, market_id=strong_market, event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=2050.0, notional=28000.0, price=0.61, transaction_ref="db2", position_effect="CLOSE"),
        ],
    )
    _seed_category(
        sparse_wallet,
        [
            _item(wallet_address=sparse_wallet, market_id=sparse_market, event_timestamp=now - timedelta(hours=2), side_or_outcome="YES", size=1200.0, notional=14000.0, price=0.54, transaction_ref="sp1", position_effect="OPEN"),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([strong_market, sparse_market], source_type="phase5d_test")
    assert result is not None

    queries = WhaleScoringQueryService()
    strong_score = queries.get_whale_market_score_details(market_id=strong_market)
    sparse_score = queries.get_whale_market_score_details(market_id=sparse_market)
    assert strong_score is not None
    assert sparse_score is not None

    assert float(strong_score["whale_presence_score"]) > float(sparse_score["whale_presence_score"])
    assert float(strong_score["whale_conviction_score"]) > float(sparse_score["whale_conviction_score"])


def test_smart_vs_noisy_contribution_affects_scores_correctly(postgres_test_schema) -> None:
    smart_market = _market("sports-smart-support")
    noisy_market = _market("politics-noisy-support")
    smart_wallet = _wallet("smart")
    noisy_wallet = _wallet("noisy")
    now = datetime.now(UTC)

    _seed_category(
        smart_wallet,
        [
            _item(wallet_address=smart_wallet, market_id=smart_market, event_timestamp=now - timedelta(hours=9), side_or_outcome="YES", size=2200.0, notional=30000.0, price=0.60, transaction_ref="sm1", position_effect="OPEN"),
            _item(wallet_address=smart_wallet, market_id=smart_market, event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=2250.0, notional=30500.0, price=0.61, transaction_ref="sm2", position_effect="INCREASE"),
            _item(wallet_address=smart_wallet, market_id=smart_market, event_timestamp=now - timedelta(hours=3), side_or_outcome="YES", size=2150.0, notional=29500.0, price=0.62, transaction_ref="sm3", position_effect="CLOSE"),
        ],
    )
    _seed_category(
        noisy_wallet,
        [
            _item(wallet_address=noisy_wallet, market_id=noisy_market, event_timestamp=now - timedelta(hours=8), side_or_outcome=None, size=1400.0, notional=16000.0, price=None, transaction_ref="nz1", position_effect=None),
            _item(wallet_address=noisy_wallet, market_id=noisy_market, event_timestamp=now - timedelta(hours=5), side_or_outcome="NO", size=1500.0, notional=17000.0, price=0.46, transaction_ref="nz2", position_effect="REVERSE", previous_side_or_outcome="YES"),
            _item(wallet_address=noisy_wallet, market_id=noisy_market, event_timestamp=now - timedelta(hours=1), side_or_outcome=None, size=1450.0, notional=16500.0, price=None, transaction_ref="nz3", position_effect=None),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([smart_market, noisy_market], source_type="phase5d_test")
    assert result is not None

    queries = WhaleScoringQueryService()
    smart_score = queries.get_whale_market_score_details(market_id=smart_market)
    noisy_score = queries.get_whale_market_score_details(market_id=noisy_market)
    assert smart_score is not None
    assert noisy_score is not None

    assert float(smart_score["smart_whale_alignment_score"]) > float(noisy_score["smart_whale_alignment_score"])
    assert float(smart_score["whale_reversal_risk"]) < float(noisy_score["whale_reversal_risk"])


def test_reversal_risk_handling_behaves_correctly(postgres_test_schema) -> None:
    steady_market = _market("steady-market")
    reversal_market = _market("reversal-market")
    steady_wallet = _wallet("steady")
    reversal_wallet = _wallet("reversal")
    now = datetime.now(UTC)

    _seed_category(
        steady_wallet,
        [
            _item(wallet_address=steady_wallet, market_id=steady_market, event_timestamp=now - timedelta(hours=10), side_or_outcome="YES", size=1900.0, notional=24000.0, price=0.59, transaction_ref="st1", position_effect="OPEN"),
            _item(wallet_address=steady_wallet, market_id=steady_market, event_timestamp=now - timedelta(hours=6), side_or_outcome="YES", size=1925.0, notional=24500.0, price=0.60, transaction_ref="st2", position_effect="INCREASE"),
            _item(wallet_address=steady_wallet, market_id=steady_market, event_timestamp=now - timedelta(hours=2), side_or_outcome="YES", size=1880.0, notional=23800.0, price=0.61, transaction_ref="st3", position_effect="CLOSE"),
        ],
    )
    _seed_category(
        reversal_wallet,
        [
            _item(wallet_address=reversal_wallet, market_id=reversal_market, event_timestamp=now - timedelta(hours=7), side_or_outcome="YES", size=1700.0, notional=21000.0, price=0.57, transaction_ref="rv1", position_effect="OPEN"),
            _item(wallet_address=reversal_wallet, market_id=reversal_market, event_timestamp=now - timedelta(hours=3), side_or_outcome="NO", size=1800.0, notional=22000.0, price=0.43, transaction_ref="rv2", position_effect="REVERSE", previous_side_or_outcome="YES"),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([steady_market, reversal_market], source_type="phase5d_test")
    assert result is not None

    queries = WhaleScoringQueryService()
    steady_score = queries.get_whale_market_score_details(market_id=steady_market)
    reversal_score = queries.get_whale_market_score_details(market_id=reversal_market)
    assert steady_score is not None
    assert reversal_score is not None

    assert float(reversal_score["whale_reversal_risk"]) > float(steady_score["whale_reversal_risk"])
    assert "elevated_reversal_risk" in reversal_score["scoring_reason_codes_json"]


def test_sparse_market_handling_is_honest(postgres_test_schema) -> None:
    sparse_market = _market("sparse-honest-market")
    wallet = _wallet("honest")
    now = datetime.now(UTC)

    _seed_category(
        wallet,
        [
            _item(wallet_address=wallet, market_id=sparse_market, event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=1300.0, notional=15000.0, price=0.55, transaction_ref="hs1", position_effect="OPEN"),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([sparse_market], source_type="phase5d_test")
    assert result is not None

    queries = WhaleScoringQueryService()
    score = queries.get_whale_market_score_details(market_id=sparse_market)
    assert score is not None
    assert "sparse_market_support" in score["scoring_reason_codes_json"]
    assert int(score["supporting_wallet_count"]) == 1


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = _market("query-whale-market")
    wallet = _wallet("query")
    now = datetime.now(UTC)
    _seed_category(
        wallet,
        [
            _item(wallet_address=wallet, market_id=market_id, event_timestamp=now - timedelta(hours=5), side_or_outcome="YES", size=1600.0, notional=21000.0, price=0.59, transaction_ref="q1", position_effect="OPEN"),
            _item(wallet_address=wallet, market_id=market_id, event_timestamp=now - timedelta(hours=2), side_or_outcome="YES", size=1650.0, notional=21500.0, price=0.60, transaction_ref="q2", position_effect="CLOSE"),
        ],
    )

    service = WhaleScoringService()
    result = service.score_markets([market_id], source_type="phase5d_test")
    assert result is not None

    queries = WhaleScoringQueryService()
    summary = queries.get_whale_scoring_run_summary(result.whale_scoring_run_id)
    assert summary is not None
    assert summary["score_count"] == 1

    rows = queries.list_whale_market_scores_for_run(result.whale_scoring_run_id)
    assert len(rows) == 1
    score_id = str(rows[0]["id"])
    details = queries.get_whale_market_score_details(whale_market_score_id=score_id)
    assert details is not None
    assert details["market_id"] == market_id

    by_top = queries.list_top_whale_scored_markets(limit=200, order_by="whale_presence_score")
    assert any(str(row["market_id"]) == market_id for row in by_top)

    comparison = queries.compare_whale_market_score_to_underlying_wallets(market_id)
    assert comparison is not None
    assert comparison["score"] is not None
    assert len(comparison["supporting_wallets"]) >= 1


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeWhaleScoringService:
        def score_markets(  # noqa: ANN001
            self,
            market_ids,
            *,
            window_start=None,
            window_end=None,
            source_type: str,
            source_ref: str | None = None,
        ):
            called["market_ids"] = market_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            called["window_start"] = window_start
            called["window_end"] = window_end
            return WhaleScoringRunResult(
                whale_scoring_run_id="scoring-run-cli-test",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

        def score_recent_markets(self, *, window_hours: int, limit_markets: int | None = None, source_ref: str | None = None):  # noqa: ANN001
            called["window_hours"] = window_hours
            called["limit_markets"] = limit_markets
            called["source_ref"] = source_ref
            return WhaleScoringRunResult(
                whale_scoring_run_id="scoring-run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.whale_scoring.WhaleScoringService", FakeWhaleScoringService)

    exit_code = scoring_main(["--market-ids", "market-a", "--source-ref", "cli-test", "--window-hours", str(DEFAULT_WINDOW_HOURS)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["market_ids"] == ["market-a"]
    assert called["source_ref"] == "cli-test"
    assert "scoring-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    market_id = _market("safe-whale-market")
    wallet = _wallet("safe")
    now = datetime.now(UTC)
    _seed_category(
        wallet,
        [
            _item(wallet_address=wallet, market_id=market_id, event_timestamp=now - timedelta(hours=4), side_or_outcome="YES", size=1600.0, notional=21000.0, price=0.60, transaction_ref="s1", position_effect="OPEN"),
            _item(wallet_address=wallet, market_id=market_id, event_timestamp=now - timedelta(hours=1), side_or_outcome="YES", size=1550.0, notional=20500.0, price=0.61, transaction_ref="s2", position_effect="CLOSE"),
        ],
    )

    service = WhaleScoringService()
    service.score_markets([market_id], source_type="phase5d_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []


def test_score_recent_markets_noops_cleanly_when_recent_window_is_empty(postgres_test_schema, caplog: pytest.LogCaptureFixture) -> None:
    run_migrations()
    service = WhaleScoringService()

    with caplog.at_level("INFO"):
        result = service.score_recent_markets(window_hours=24, limit_markets=25, source_ref="empty-window-test")

    assert result is None
    assert "whale_recent_markets_noop" in caplog.text
