from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.bucket_allocation import BucketAllocationService
from app.services.query.ranking_v2_query_service import RankingV2QueryService
from app.services.ranking_v2 import RANKING_VERSION, RankingV2RunResult, RankingV2Service, main as ranking_v2_main
from app.services.trade_classification import TradeClassificationService
from test_phase6a_trade_classification import _manual_whale_item, _seed_cognition_summary, _seed_market_cycle, _seed_whale_score, _wallet


def _seed_rankable_context(
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
) -> dict[str, str | None]:
    cycle_id = _seed_market_cycle(market_id=market_id, question=question, slug=slug, hours_to_close=hours_to_close)
    cognition_summary_id = None
    if cognition_conclusion is not None:
        cognition_summary_id = _seed_cognition_summary(
            market_id=market_id,
            question=question,
            cognition_conclusion=cognition_conclusion,
            confidence=cognition_confidence,
            caution=cognition_caution,
            usability=cognition_usability,
        )
    whale_market_score_id = None
    if whale_items:
        whale_market_score_id = _seed_whale_score(market_id=market_id, items=whale_items)

    classification_result = TradeClassificationService().classify_markets([market_id], source_type="phase7a_seed", source_ref=f"seed-{market_id}")
    assert classification_result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        classification_row = conn.execute(
            "SELECT id FROM trade_classifications WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert classification_row is not None
    trade_classification_id = str(classification_row["id"])

    allocation_result = BucketAllocationService().allocate_classifications([trade_classification_id], source_type="phase7a_seed")
    assert allocation_result is not None
    with factory.connect() as conn:
        allocation_row = conn.execute(
            "SELECT id FROM bucket_allocations WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert allocation_row is not None

    return {
        "cycle_id": cycle_id,
        "cognition_summary_id": cognition_summary_id,
        "whale_market_score_id": whale_market_score_id,
        "trade_classification_id": trade_classification_id,
        "bucket_allocation_id": str(allocation_row["id"]),
    }


def test_ranking_v2_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"ranking_v2_runs", "ranking_v2_candidates"} <= table_names


def test_successful_ranking_v2_run_persists_correctly(postgres_test_schema) -> None:
    market_id = f"rank-fast-{uuid4().hex[:8]}"
    seeded = _seed_rankable_context(
        market_id=market_id,
        question="Will ranking fast market resolve soon?",
        slug="rank-fast",
        hours_to_close=10,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.81,
        cognition_caution=0.27,
        cognition_usability="USABLE_NOW",
    )

    result = RankingV2Service().rank_markets([market_id], source_type="phase7a_test", source_ref="phase7a")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM ranking_v2_runs WHERE id = %s LIMIT 1", (result.ranking_v2_run_id,)).fetchone()
        candidate_row = conn.execute("SELECT * FROM ranking_v2_candidates WHERE ranking_v2_run_id = %s LIMIT 1", (result.ranking_v2_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["ranking_version"] == RANKING_VERSION
    assert candidate_row is not None
    assert candidate_row["market_id"] == market_id
    assert str(candidate_row["cycle_id"]) == seeded["cycle_id"]
    assert str(candidate_row["cognition_summary_id"]) == seeded["cognition_summary_id"]
    assert str(candidate_row["trade_classification_id"]) == seeded["trade_classification_id"]
    assert str(candidate_row["bucket_allocation_id"]) == seeded["bucket_allocation_id"]


def test_deterministic_factor_computation_behaves_as_expected(postgres_test_schema) -> None:
    strong_market = f"rank-strong-{uuid4().hex[:6]}"
    weak_market = f"rank-weak-{uuid4().hex[:6]}"

    _seed_rankable_context(
        market_id=strong_market,
        question="Will the strong ranked market resolve well?",
        slug="rank-strong",
        hours_to_close=36,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.86,
        cognition_caution=0.18,
        cognition_usability="USABLE_NOW",
        whale_items=[
            _manual_whale_item(wallet_address=_wallet("rs1"), market_id=strong_market, side_or_outcome="YES", size=2200.0, notional=30000.0, price=0.61, transaction_ref="rs1", position_effect="OPEN"),
            _manual_whale_item(wallet_address=_wallet("rs2"), market_id=strong_market, side_or_outcome="YES", size=2150.0, notional=29200.0, price=0.62, transaction_ref="rs2", position_effect="INCREASE"),
        ],
    )
    _seed_rankable_context(
        market_id=weak_market,
        question="Will the weaker ranked market stay mixed?",
        slug="rank-weak",
        hours_to_close=300,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.58,
        cognition_caution=0.63,
        cognition_usability="NEEDS_CONFIRMATION",
    )

    RankingV2Service().rank_markets([strong_market, weak_market], source_type="phase7a_test")
    queries = RankingV2QueryService()
    strong = queries.get_ranking_v2_candidate_details(market_id=strong_market)
    weak = queries.get_ranking_v2_candidate_details(market_id=weak_market)
    assert strong is not None
    assert weak is not None

    assert float(strong["total_rank_score"]) > float(weak["total_rank_score"])
    assert float(strong["factor_scores_json"]["cognition_factor"]) > float(weak["factor_scores_json"]["cognition_factor"])
    assert float(strong["factor_scores_json"]["risk_penalty"]) < float(weak["factor_scores_json"]["risk_penalty"])


def test_score_ordering_behaves_as_expected(postgres_test_schema) -> None:
    top_market = f"rank-top-{uuid4().hex[:6]}"
    mid_market = f"rank-mid-{uuid4().hex[:6]}"
    low_market = f"rank-low-{uuid4().hex[:6]}"

    _seed_rankable_context(
        market_id=top_market,
        question="Will top ranked market resolve positively?",
        slug="rank-top",
        hours_to_close=48,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.88,
        cognition_caution=0.15,
        cognition_usability="USABLE_NOW",
        whale_items=[
            _manual_whale_item(wallet_address=_wallet("rt1"), market_id=top_market, side_or_outcome="YES", size=2300.0, notional=31500.0, price=0.62, transaction_ref="rt1", position_effect="OPEN"),
            _manual_whale_item(wallet_address=_wallet("rt2"), market_id=top_market, side_or_outcome="YES", size=2250.0, notional=30800.0, price=0.63, transaction_ref="rt2", position_effect="INCREASE"),
        ],
    )
    _seed_rankable_context(
        market_id=mid_market,
        question="Will mid ranked market stay decent?",
        slug="rank-mid",
        hours_to_close=96,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.73,
        cognition_caution=0.34,
        cognition_usability="USABLE_NOW",
    )
    _seed_rankable_context(
        market_id=low_market,
        question="Will low ranked market stay weak?",
        slug="rank-low",
        hours_to_close=320,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.52,
        cognition_caution=0.67,
        cognition_usability="NEEDS_CONFIRMATION",
    )

    result = RankingV2Service().rank_markets([top_market, mid_market, low_market], source_type="phase7a_test")
    assert result is not None
    rows = RankingV2QueryService().list_ranking_v2_candidates_for_run(result.ranking_v2_run_id)
    assert [str(row["market_id"]) for row in rows] == [top_market, mid_market, low_market]


def test_reject_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"rank-reject-{uuid4().hex[:6]}"
    _seed_rankable_context(
        market_id=market_id,
        question="Will reject ranked market remain unusable?",
        slug="rank-reject",
        hours_to_close=72,
        cognition_conclusion="CONTRADICTORY",
        cognition_confidence=0.40,
        cognition_caution=0.86,
        cognition_usability="DO_NOT_USE",
    )

    RankingV2Service().rank_markets([market_id], source_type="phase7a_test")
    candidate = RankingV2QueryService().get_ranking_v2_candidate_details(market_id=market_id)
    assert candidate is not None
    assert candidate["rank_tier_class"] == "REJECT"
    assert float(candidate["total_rank_score"]) < 25.0
    assert "forced_reject_guardrail" in candidate["rank_reason_codes_json"]


def test_sparse_context_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"rank-sparse-{uuid4().hex[:6]}"
    _seed_market_cycle(market_id=market_id, question="Will sparse market rank weakly?", slug="rank-sparse", hours_to_close=120)

    result = RankingV2Service().rank_markets([market_id], source_type="phase7a_test")
    assert result is not None

    candidate = RankingV2QueryService().get_ranking_v2_candidate_details(market_id=market_id)
    assert candidate is not None
    assert candidate["rank_tier_class"] == "REJECT"
    assert "missing_trade_classification" in candidate["rank_reason_codes_json"] or "missing_cognition_context" in candidate["rank_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"rank-query-{uuid4().hex[:6]}"
    seeded = _seed_rankable_context(
        market_id=market_id,
        question="Will query ranked market resolve?",
        slug="rank-query",
        hours_to_close=60,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.74,
        cognition_caution=0.30,
        cognition_usability="USABLE_NOW",
    )
    result = RankingV2Service().rank_cycle(seeded["cycle_id"])
    assert result is not None

    queries = RankingV2QueryService()
    summary = queries.get_ranking_v2_run_summary(result.ranking_v2_run_id)
    assert summary is not None
    assert summary["candidate_count"] == 1

    rows = queries.list_ranking_v2_candidates_for_run(result.ranking_v2_run_id)
    assert len(rows) == 1
    candidate_id = str(rows[0]["id"])
    details = queries.get_ranking_v2_candidate_details(ranking_v2_candidate_id=candidate_id)
    assert details is not None
    assert details["market_id"] == market_id

    top = queries.list_top_ranked_candidates(limit=200)
    assert any(str(row["market_id"]) == market_id for row in top)

    comparison = queries.compare_ranking_v2_candidate_to_upstream_context(market_id)
    assert comparison is not None
    assert comparison["ranking_candidate"] is not None
    assert comparison["market_snapshot"] is not None
    assert comparison["trade_classification"] is not None
    assert comparison["bucket_allocation"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeRankingV2Service:
        def rank_markets(self, market_ids, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["market_ids"] = market_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return RankingV2RunResult(
                ranking_v2_run_id="ranking-v2-cli-test",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

        def rank_cycle(self, cycle_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["cycle_id"] = cycle_id
            called["source_ref"] = source_ref
            return RankingV2RunResult(
                ranking_v2_run_id="ranking-v2-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

        def rank_latest_catalog(self, *, limit: int = 25, source_ref: str | None = None):  # noqa: ANN001
            called["limit"] = limit
            called["source_ref"] = source_ref
            return RankingV2RunResult(
                ranking_v2_run_id="ranking-v2-cli-test",
                status="COMPLETED",
                input_count=limit,
                success_count=limit,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.ranking_v2.RankingV2Service", FakeRankingV2Service)

    exit_code = ranking_v2_main(["--market-ids", "market-a", "--source-ref", "cli-test"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert called["market_ids"] == ["market-a"]
    assert called["source_ref"] == "cli-test"
    assert "ranking-v2-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    market_id = f"rank-safe-{uuid4().hex[:6]}"
    _seed_rankable_context(
        market_id=market_id,
        question="Will safe ranking remain isolated?",
        slug="rank-safe",
        hours_to_close=36,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.76,
        cognition_caution=0.26,
        cognition_usability="USABLE_NOW",
    )

    RankingV2Service().rank_markets([market_id], source_type="phase7a_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
