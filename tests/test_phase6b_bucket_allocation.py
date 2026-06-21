from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.bucket_allocation import (
    ALLOCATOR_VERSION,
    BucketAllocationRunResult,
    BucketAllocationService,
    main as bucket_allocation_main,
)
from app.services.query.bucket_allocation_query_service import BucketAllocationQueryService
from app.services.trade_classification import TradeClassificationService
from test_phase6a_trade_classification import _seed_cognition_summary, _seed_market_cycle, _seed_whale_score, _manual_whale_item, _wallet


def _seed_trade_classification(
    *,
    market_id: str,
    question: str,
    slug: str,
    hours_to_close: int,
    cognition_conclusion: str | None = None,
    cognition_confidence: float = 0.0,
    cognition_caution: float = 0.0,
    cognition_usability: str = "DO_NOT_USE",
    whale_items: list | None = None,
) -> str:
    _seed_market_cycle(market_id=market_id, question=question, slug=slug, hours_to_close=hours_to_close)
    if cognition_conclusion is not None:
        _seed_cognition_summary(
            market_id=market_id,
            question=question,
            cognition_conclusion=cognition_conclusion,
            confidence=cognition_confidence,
            caution=cognition_caution,
            usability=cognition_usability,
        )
    if whale_items:
        _seed_whale_score(market_id=market_id, items=whale_items)

    result = TradeClassificationService().classify_markets([market_id], source_type="phase6b_seed", source_ref=f"seed-{market_id}")
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT id FROM trade_classifications WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def test_bucket_allocation_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"bucket_allocation_runs", "bucket_allocations"} <= table_names


def test_successful_bucket_allocation_run_persists_correctly(postgres_test_schema) -> None:
    market_id = f"alloc-fast-{uuid4().hex[:8]}"
    classification_id = _seed_trade_classification(
        market_id=market_id,
        question="Will the allocation fast market resolve soon?",
        slug="alloc-fast",
        hours_to_close=10,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.80,
        cognition_caution=0.28,
        cognition_usability="USABLE_NOW",
    )

    result = BucketAllocationService().allocate_classifications([classification_id], source_type="phase6b_test", source_ref="phase6b")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM bucket_allocation_runs WHERE id = %s LIMIT 1",
            (result.bucket_allocation_run_id,),
        ).fetchone()
        allocation_row = conn.execute(
            "SELECT * FROM bucket_allocations WHERE bucket_allocation_run_id = %s LIMIT 1",
            (result.bucket_allocation_run_id,),
        ).fetchone()

    assert run_row is not None
    assert run_row["allocator_version"] == ALLOCATOR_VERSION
    assert allocation_row is not None
    assert allocation_row["market_id"] == market_id
    assert str(allocation_row["trade_classification_id"]) == classification_id
    assert allocation_row["assigned_bucket_class"] == "FAST_BUCKET"


def test_deterministic_bucket_assignment_behaves_as_expected(postgres_test_schema) -> None:
    fast_market = f"ba-fast-{uuid4().hex[:6]}"
    whale_market = f"ba-whale-{uuid4().hex[:6]}"
    slow_market = f"ba-slow-{uuid4().hex[:6]}"

    fast_id = _seed_trade_classification(
        market_id=fast_market,
        question="Will the fast allocation market resolve soon?",
        slug="ba-fast",
        hours_to_close=12,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.78,
        cognition_caution=0.28,
        cognition_usability="USABLE_NOW",
    )
    whale_id = _seed_trade_classification(
        market_id=whale_market,
        question="Will PSG win the whale-led allocation match?",
        slug="ba-whale",
        hours_to_close=96,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.68,
        cognition_caution=0.35,
        cognition_usability="NEEDS_CONFIRMATION",
        whale_items=[
            _manual_whale_item(wallet_address=_wallet("baw1"), market_id=whale_market, side_or_outcome="YES", size=2300.0, notional=31000.0, price=0.62, transaction_ref="baw1", position_effect="OPEN"),
            _manual_whale_item(wallet_address=_wallet("baw2"), market_id=whale_market, side_or_outcome="YES", size=2250.0, notional=30500.0, price=0.63, transaction_ref="baw2", position_effect="INCREASE"),
            _manual_whale_item(wallet_address=_wallet("baw3"), market_id=whale_market, side_or_outcome="YES", size=2200.0, notional=30000.0, price=0.64, transaction_ref="baw3", position_effect="INCREASE"),
        ],
    )
    slow_id = _seed_trade_classification(
        market_id=slow_market,
        question="Will the slow conviction market resolve later?",
        slug="ba-slow",
        hours_to_close=240,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.83,
        cognition_caution=0.22,
        cognition_usability="USABLE_NOW",
    )

    result = BucketAllocationService().allocate_classifications([fast_id, whale_id, slow_id], source_type="phase6b_test")
    assert result is not None

    queries = BucketAllocationQueryService()
    fast = queries.get_bucket_allocation_details(market_id=fast_market)
    whale = queries.get_bucket_allocation_details(market_id=whale_market)
    slow = queries.get_bucket_allocation_details(market_id=slow_market)
    assert fast is not None
    assert whale is not None
    assert slow is not None

    assert fast["assigned_bucket_class"] == "FAST_BUCKET"
    assert whale["assigned_bucket_class"] == "WHALE_BUCKET"
    assert slow["assigned_bucket_class"] == "CONVICTION_BUCKET"


def test_confidence_and_risk_posture_materially_affect_deployment_fraction(postgres_test_schema) -> None:
    stronger_market = f"ba-strong-{uuid4().hex[:6]}"
    weaker_market = f"ba-weak-{uuid4().hex[:6]}"

    stronger_id = _seed_trade_classification(
        market_id=stronger_market,
        question="Will stronger conviction market resolve well?",
        slug="ba-strong",
        hours_to_close=180,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.87,
        cognition_caution=0.18,
        cognition_usability="USABLE_NOW",
    )
    weaker_id = _seed_trade_classification(
        market_id=weaker_market,
        question="Will weaker conviction market stay risky?",
        slug="ba-weak",
        hours_to_close=180,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.60,
        cognition_caution=0.62,
        cognition_usability="NEEDS_CONFIRMATION",
    )

    BucketAllocationService().allocate_classifications([stronger_id, weaker_id], source_type="phase6b_test")
    queries = BucketAllocationQueryService()
    stronger = queries.get_bucket_allocation_details(market_id=stronger_market)
    weaker = queries.get_bucket_allocation_details(market_id=weaker_market)
    assert stronger is not None
    assert weaker is not None

    assert float(stronger["deployment_fraction"]) > float(weaker["deployment_fraction"])
    assert stronger["deployability_class"] in {"DEPLOYABLE", "LIMITED"}
    assert weaker["deployability_class"] in {"DEPLOYABLE", "LIMITED", "SATURATED", "BLOCKED"}


def test_no_trade_produces_no_bucket_and_blocked_deployability(postgres_test_schema) -> None:
    market_id = f"ba-no-trade-{uuid4().hex[:6]}"
    classification_id = _seed_trade_classification(
        market_id=market_id,
        question="Will the no-trade allocation market stay ambiguous?",
        slug="ba-no-trade",
        hours_to_close=72,
        cognition_conclusion="CONTRADICTORY",
        cognition_confidence=0.41,
        cognition_caution=0.83,
        cognition_usability="DO_NOT_USE",
    )

    BucketAllocationService().allocate_classifications([classification_id], source_type="phase6b_test")
    allocation = BucketAllocationQueryService().get_bucket_allocation_details(market_id=market_id)
    assert allocation is not None
    assert allocation["assigned_bucket_class"] == "NO_BUCKET"
    assert float(allocation["deployment_fraction"]) == 0.0
    assert allocation["deployability_class"] == "BLOCKED"
    assert allocation["occupancy_status"] == "BLOCKED"


def test_sparse_context_allocation_is_honest(postgres_test_schema) -> None:
    market_id = f"ba-sparse-{uuid4().hex[:6]}"
    classification_id = _seed_trade_classification(
        market_id=market_id,
        question="Will sparse allocation market stay weak?",
        slug="ba-sparse",
        hours_to_close=120,
    )

    BucketAllocationService().allocate_classifications([classification_id], source_type="phase6b_test")
    allocation = BucketAllocationQueryService().get_bucket_allocation_details(market_id=market_id)
    assert allocation is not None
    assert allocation["assigned_bucket_class"] == "NO_BUCKET"
    assert "sparse_classification_context" in allocation["allocation_reason_codes_json"] or "no_trade_blocked" in allocation["allocation_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"ba-query-{uuid4().hex[:6]}"
    classification_id = _seed_trade_classification(
        market_id=market_id,
        question="Will query allocation market resolve?",
        slug="ba-query",
        hours_to_close=60,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.71,
        cognition_caution=0.38,
        cognition_usability="USABLE_NOW",
    )

    result = BucketAllocationService().allocate_classifications([classification_id], source_type="phase6b_test", source_ref="query")
    assert result is not None

    queries = BucketAllocationQueryService()
    summary = queries.get_bucket_allocation_run_summary(result.bucket_allocation_run_id)
    assert summary is not None
    assert summary["allocation_count"] == 1

    rows = queries.list_bucket_allocations_for_run(result.bucket_allocation_run_id)
    assert len(rows) == 1
    allocation_id = str(rows[0]["id"])
    details = queries.get_bucket_allocation_details(bucket_allocation_id=allocation_id)
    assert details is not None
    assert details["market_id"] == market_id

    by_bucket = queries.list_bucket_allocations_by_bucket(str(details["assigned_bucket_class"]), limit=50)
    assert any(str(row["market_id"]) == market_id for row in by_bucket)

    comparison = queries.compare_bucket_allocation_to_trade_classification(market_id)
    assert comparison is not None
    assert comparison["bucket_allocation"] is not None
    assert comparison["trade_classification"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeBucketAllocationService:
        def allocate_classifications(self, trade_classification_ids, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["trade_classification_ids"] = trade_classification_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return BucketAllocationRunResult(
                bucket_allocation_run_id="bucket-allocation-cli-test",
                status="COMPLETED",
                input_count=len(trade_classification_ids),
                success_count=len(trade_classification_ids),
                failure_count=0,
            )

        def allocate_for_classification_run(self, trade_classification_run_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["trade_classification_run_id"] = trade_classification_run_id
            called["source_ref"] = source_ref
            return BucketAllocationRunResult(
                bucket_allocation_run_id="bucket-allocation-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.bucket_allocation.BucketAllocationService", FakeBucketAllocationService)

    exit_code = bucket_allocation_main(["--trade-classification-ids", "classification-a", "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["trade_classification_ids"] == ["classification-a"]
    assert called["source_ref"] == "cli-test"
    assert "bucket-allocation-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    market_id = f"ba-safe-{uuid4().hex[:6]}"
    classification_id = _seed_trade_classification(
        market_id=market_id,
        question="Will safe allocation remain isolated?",
        slug="ba-safe",
        hours_to_close=36,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.72,
        cognition_caution=0.31,
        cognition_usability="USABLE_NOW",
    )

    BucketAllocationService().allocate_classifications([classification_id], source_type="phase6b_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
