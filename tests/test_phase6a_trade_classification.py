from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.cognition_summary import CognitionSummaryService
from app.services.event_interpreter import ClaudeEventInterpreterService, EventInterpreterInput
from app.services.invalidation_reasoning_lite import InvalidationReasoningLiteService
from app.services.market_link_candidate import MarketLinkCandidateService
from app.services.query.trade_classification_query_service import TradeClassificationQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.resolution_analyzer_lite import ResolutionAnalyzerLiteService
from app.services.trade_classification import (
    CLASSIFIER_VERSION,
    TradeClassificationRunResult,
    TradeClassificationService,
    main as trade_classification_main,
)
from app.services.whale_categories import WhaleCategoryService
from app.services.whale_profiling import WhaleProfilingService
from app.services.whale_scanner import ManualWhaleEventItem, WhaleScannerService
from app.services.whale_scoring import WhaleScoringService
from app.stage2.claude_analyst import MarketRecommendation


class FakeAnthropicResponse:
    def __init__(self, text: str) -> None:
        self.content = [SimpleNamespace(text=text)]


class FakeAnthropicClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.messages = self

    def create(self, **kwargs):  # noqa: ANN003
        return FakeAnthropicResponse(self._text)


def _wallet(label: str) -> str:
    return f"0x{label}{uuid4().hex[:8]}"


def _success_interpreter_response(market_id: str, question: str) -> str:
    return json.dumps(
        {
            "interpretations": [
                {
                    "event_type": "event_update",
                    "event_summary": f"New development directly affects {question}.",
                    "certainty_score": 0.90,
                    "ambiguity_score": 0.10,
                    "novelty_score": 0.75,
                    "directness_class": "direct_signal",
                    "directness_score": 0.88,
                    "contradiction_risk": 0.12,
                    "affected_market_candidates": [
                        {
                            "market_id_hint": market_id,
                            "question_hint": question,
                            "confidence": 0.84,
                            "rationale": "Seeded direct market hint.",
                        }
                    ],
                    "affected_outcomes": ["YES"],
                    "recommended_action_class": "usable_now",
                    "explanation": {"why": "Seeded direct update."},
                }
            ]
        }
    )


def _success_resolution_response() -> str:
    return json.dumps(
        {
            "analyses": [
                {
                    "resolution_summary": "The event fits the market wording cleanly.",
                    "wording_clarity_score": 0.86,
                    "ambiguity_risk_score": 0.18,
                    "resolution_mismatch_risk": 0.10,
                    "resolution_confidence_score": 0.85,
                    "direct_fit_class": "direct_fit",
                    "usable_now_class": "usable_now",
                    "explanation": {
                        "fit_reason": "Seeded direct fit.",
                        "ambiguities": [],
                        "mismatch_points": [],
                        "needs_confirmation": [],
                    },
                }
            ]
        }
    )


def _success_invalidation_response() -> str:
    return json.dumps(
        {
            "reasonings": [
                {
                    "reasoning_summary": "The event supports the thesis with limited invalidation pressure.",
                    "thesis_effect_class": "supports_thesis",
                    "invalidation_risk_score": 0.16,
                    "confidence_degradation_score": 0.18,
                    "contradiction_strength_score": 0.10,
                    "recommended_monitoring_class": "watch",
                    "advisory_action_class": "none",
                    "explanation": {
                        "thesis_reason": "Seeded support case.",
                        "support_points": ["Event supports the market premise."],
                        "contradiction_points": [],
                        "monitoring_triggers": [],
                    },
                }
            ]
        }
    )


def _success_cognition_summary_response(*, conclusion: str, confidence: float, caution: float, usability: str) -> str:
    return json.dumps(
        {
            "summaries": [
                {
                    "narration_summary": "Seeded cognition summary for trade classification tests.",
                    "concise_narration_text": "Seeded cognition summary.",
                    "cognition_conclusion_class": conclusion,
                    "overall_confidence_score": confidence,
                    "caution_score": caution,
                    "usability_class": usability,
                    "recommended_operator_focus": "MONITOR",
                    "evidence": {
                        "event_takeaway": "Seeded event takeaway.",
                        "link_basis": "Seeded link basis.",
                        "resolution_takeaway": "Seeded resolution takeaway.",
                        "invalidation_takeaway": "Seeded invalidation takeaway.",
                        "open_questions": [],
                    },
                }
            ]
        }
    )


def _event_input(label: str) -> EventInterpreterInput:
    return EventInterpreterInput(
        source_type="manual_event",
        source_ref=f"trade-classification:{label}",
        raw_event_text=f"Seeded event for {label}",
        raw_event_payload_json={"label": label},
        normalized_event_title=f"Seeded {label}",
    )


def _scored_market(*, market_id: str, question: str, slug: str, hours_to_close: int, score: float = 82.0) -> ScoredMarket:
    now = datetime.now(UTC)
    end_time = now + timedelta(hours=hours_to_close)
    market = NormalizedMarket(
        market_id=market_id,
        event_id=f"event-{market_id}",
        event_title=question,
        question=question,
        slug=slug,
        end_time=end_time,
        yes_price=0.63,
        no_price=0.37,
        last_trade_price=0.63,
        best_bid=0.62,
        best_ask=0.64,
        spread=0.02,
        liquidity=60000.0,
        volume=15000.0,
        volume_24h=12000.0,
        open_interest=1100.0,
        comment_count=35,
        competitive=0.82,
        accepting_orders=True,
        updated_at=now,
        raw_market={"market_id": market_id, "slug": slug, "question": question},
    )
    return ScoredMarket(
        market=market,
        score=score,
        breakdown=ScoreBreakdown(
            price_attractiveness=30.0,
            time_to_close=20.0,
            liquidity_volume=16.0,
            market_activity=16.0,
        ),
        reason="seeded for phase6a tests",
        computed_at=now,
    )


def _manual_whale_item(
    *,
    wallet_address: str,
    market_id: str,
    side_or_outcome: str | None,
    size: float,
    notional: float | None,
    price: float | None,
    transaction_ref: str,
    position_effect: str | None,
    previous_side_or_outcome: str | None = None,
) -> ManualWhaleEventItem:
    return ManualWhaleEventItem(
        wallet_address=wallet_address,
        market_id=market_id,
        event_timestamp=datetime.now(UTC),
        side_or_outcome=side_or_outcome,
        size=size,
        notional=notional,
        price=price,
        transaction_ref=transaction_ref,
        source_type="MANUAL_IMPORT",
        position_effect=position_effect,
        previous_side_or_outcome=previous_side_or_outcome,
        source_payload_json={"wallet_address": wallet_address, "market_id": market_id, "position_effect": position_effect},
    )


def _seed_market_cycle(*, market_id: str, question: str, slug: str, hours_to_close: int, selected: bool = True) -> str:
    persistence = Phase1CyclePersistenceService()
    handle = persistence.open_cycle(
        mode="SCAN_ONLY",
        trigger_source="phase6a_seed",
        top_n=1,
        pages_requested=1,
    )
    recommendation = MarketRecommendation(
        rank=1,
        question=question,
        confidence=0.78,
        action="BUY_YES",
        reason="Seeded phase6a recommendation.",
        yes_price=0.63,
        no_price=0.37,
        score=82.0,
        computed_at=datetime.now(UTC).isoformat(),
    )
    cycle_result = SimpleNamespace(
        top_scored=[_scored_market(market_id=market_id, question=question, slug=slug, hours_to_close=hours_to_close)],
        recommendations=[recommendation],
    )
    persistence.persist_cycle_snapshot(handle=handle, cycle_result=cycle_result)
    assert handle.cycle_id is not None
    return handle.cycle_id


def _seed_cognition_summary(*, market_id: str, question: str, cognition_conclusion: str, confidence: float, caution: float, usability: str) -> str:
    interpreter = ClaudeEventInterpreterService(client=FakeAnthropicClient(_success_interpreter_response(market_id, question)))
    interpretation_run = interpreter.interpret_events([_event_input(market_id)], source_type="phase6a_seed", source_ref=market_id)
    assert interpretation_run is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        interpretation_row = conn.execute(
            "SELECT id FROM event_interpretations ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert interpretation_row is not None

    linker = MarketLinkCandidateService()
    link_result = linker.link_interpretations([str(interpretation_row["id"])], source_type="phase6a_seed")
    assert link_result is not None

    with factory.connect() as conn:
        candidate_row = conn.execute(
            "SELECT id, market_link_run_id FROM market_link_candidates WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert candidate_row is not None

    analyzer = ResolutionAnalyzerLiteService(client=FakeAnthropicClient(_success_resolution_response()))
    analysis_result = analyzer.analyze_candidates(
        [str(candidate_row["id"])],
        source_type="phase6a_seed",
        market_link_run_id=str(candidate_row["market_link_run_id"]),
    )
    assert analysis_result is not None

    with factory.connect() as conn:
        analysis_row = conn.execute(
            "SELECT id, resolution_analysis_run_id FROM resolution_analyses WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert analysis_row is not None

    reasoner = InvalidationReasoningLiteService(client=FakeAnthropicClient(_success_invalidation_response()))
    reasoning_result = reasoner.analyze_resolution_analyses(
        [str(analysis_row["id"])],
        source_type="phase6a_seed",
        resolution_analysis_run_id=str(analysis_row["resolution_analysis_run_id"]),
    )
    assert reasoning_result is not None

    with factory.connect() as conn:
        reasoning_row = conn.execute(
            "SELECT id FROM invalidation_reasonings WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert reasoning_row is not None

    summarizer = CognitionSummaryService(
        client=FakeAnthropicClient(
            _success_cognition_summary_response(
                conclusion=cognition_conclusion,
                confidence=confidence,
                caution=caution,
                usability=usability,
            )
        )
    )
    summary_result = summarizer.summarize_reasonings([str(reasoning_row["id"])], source_type="phase6a_seed")
    assert summary_result is not None

    with factory.connect() as conn:
        summary_row = conn.execute(
            "SELECT id FROM cognition_summaries WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert summary_row is not None
    return str(summary_row["id"])


def _seed_whale_score(*, market_id: str, items: list[ManualWhaleEventItem]) -> str:
    wallets = sorted({item.wallet_address for item in items})
    scan_result = WhaleScannerService().scan_manual_items(items, source_ref=f"seed-{market_id}")
    assert scan_result is not None
    profile_result = WhaleProfilingService().profile_wallets(wallets, source_type="phase6a_seed")
    assert profile_result is not None
    category_result = WhaleCategoryService().categorize_wallets(wallets, source_type="phase6a_seed")
    assert category_result is not None
    scoring_result = WhaleScoringService().score_markets([market_id], source_type="phase6a_seed")
    assert scoring_result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT id FROM whale_market_scores WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def test_trade_classification_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"trade_classification_runs", "trade_classifications"} <= table_names


def test_successful_trade_classification_run_persists_correctly(postgres_test_schema) -> None:
    market_id = f"fast-market-{uuid4().hex[:8]}"
    question = "Will seeded fast market resolve soon?"
    _seed_market_cycle(market_id=market_id, question=question, slug="fast-market", hours_to_close=12)
    cognition_summary_id = _seed_cognition_summary(
        market_id=market_id,
        question=question,
        cognition_conclusion="SUPPORTIVE",
        confidence=0.79,
        caution=0.32,
        usability="USABLE_NOW",
    )
    whale_market_score_id = _seed_whale_score(
        market_id=market_id,
        items=[
            _manual_whale_item(wallet_address=_wallet("fast"), market_id=market_id, side_or_outcome="YES", size=1900.0, notional=24000.0, price=0.60, transaction_ref="tx1", position_effect="OPEN"),
            _manual_whale_item(wallet_address=_wallet("fastb"), market_id=market_id, side_or_outcome="YES", size=1800.0, notional=22000.0, price=0.61, transaction_ref="tx2", position_effect="INCREASE"),
        ],
    )

    service = TradeClassificationService()
    result = service.classify_markets([market_id], source_type="phase6a_test", source_ref="phase6a")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM trade_classification_runs WHERE id = %s LIMIT 1", (result.trade_classification_run_id,)).fetchone()
        classification_row = conn.execute("SELECT * FROM trade_classifications WHERE trade_classification_run_id = %s LIMIT 1", (result.trade_classification_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["classifier_version"] == CLASSIFIER_VERSION
    assert classification_row is not None
    assert classification_row["market_id"] == market_id
    assert str(classification_row["cognition_summary_id"]) == cognition_summary_id
    assert str(classification_row["whale_market_score_id"]) == whale_market_score_id
    assert classification_row["primary_trade_type"] in {"FAST_TRADE", "WHALE_FOLLOW", "SLOW_CONVICTION"}


def test_deterministic_trade_type_assignment_behaves_as_expected(postgres_test_schema) -> None:
    fast_market = f"fast-{uuid4().hex[:6]}"
    whale_market = f"sports-psg-whale-{uuid4().hex[:6]}"
    slow_market = f"slow-{uuid4().hex[:6]}"

    _seed_market_cycle(market_id=fast_market, question="Will fast market resolve soon?", slug="fast", hours_to_close=10)
    _seed_cognition_summary(market_id=fast_market, question="Will fast market resolve soon?", cognition_conclusion="SUPPORTIVE", confidence=0.78, caution=0.28, usability="USABLE_NOW")

    _seed_market_cycle(market_id=whale_market, question="Will PSG win the seeded whale-follow match?", slug="whale", hours_to_close=96)
    _seed_cognition_summary(market_id=whale_market, question="Will PSG win the seeded whale-follow match?", cognition_conclusion="WATCHFUL", confidence=0.68, caution=0.35, usability="NEEDS_CONFIRMATION")
    _seed_whale_score(
        market_id=whale_market,
        items=[
            _manual_whale_item(wallet_address=_wallet("wa"), market_id=whale_market, side_or_outcome="YES", size=2300.0, notional=31000.0, price=0.62, transaction_ref="wa1", position_effect="OPEN"),
            _manual_whale_item(wallet_address=_wallet("wb"), market_id=whale_market, side_or_outcome="YES", size=2250.0, notional=30500.0, price=0.63, transaction_ref="wa2", position_effect="INCREASE"),
            _manual_whale_item(wallet_address=_wallet("wc"), market_id=whale_market, side_or_outcome="YES", size=2200.0, notional=30000.0, price=0.64, transaction_ref="wa3", position_effect="INCREASE"),
        ],
    )

    _seed_market_cycle(market_id=slow_market, question="Will slow conviction market resolve later?", slug="slow", hours_to_close=240)
    _seed_cognition_summary(market_id=slow_market, question="Will slow conviction market resolve later?", cognition_conclusion="SUPPORTIVE", confidence=0.83, caution=0.22, usability="USABLE_NOW")

    service = TradeClassificationService()
    result = service.classify_markets([fast_market, whale_market, slow_market], source_type="phase6a_test")
    assert result is not None

    queries = TradeClassificationQueryService()
    fast = queries.get_trade_classification_details(market_id=fast_market)
    whale = queries.get_trade_classification_details(market_id=whale_market)
    slow = queries.get_trade_classification_details(market_id=slow_market)
    assert fast is not None
    assert whale is not None
    assert slow is not None

    assert fast["primary_trade_type"] == "FAST_TRADE"
    assert whale["primary_trade_type"] == "WHALE_FOLLOW"
    assert slow["primary_trade_type"] == "SLOW_CONVICTION"


def test_no_trade_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"no-trade-{uuid4().hex[:6]}"
    question = "Will no-trade market stay ambiguous?"
    _seed_market_cycle(market_id=market_id, question=question, slug="no-trade", hours_to_close=72)
    _seed_cognition_summary(
        market_id=market_id,
        question=question,
        cognition_conclusion="CONTRADICTORY",
        confidence=0.41,
        caution=0.83,
        usability="DO_NOT_USE",
    )

    service = TradeClassificationService()
    result = service.classify_markets([market_id], source_type="phase6a_test")
    assert result is not None

    queries = TradeClassificationQueryService()
    classification = queries.get_trade_classification_details(market_id=market_id)
    assert classification is not None
    assert classification["primary_trade_type"] == "NO_TRADE"
    assert classification["risk_posture_class"] == "DO_NOT_DEPLOY"
    assert classification["suggested_bucket_class"] == "NO_BUCKET"


def test_confidence_risk_posture_and_bucket_persist_correctly(postgres_test_schema) -> None:
    market_id = f"risky-{uuid4().hex[:6]}"
    question = "Will risky market produce upside?"
    _seed_market_cycle(market_id=market_id, question=question, slug="risky", hours_to_close=84)
    _seed_cognition_summary(
        market_id=market_id,
        question=question,
        cognition_conclusion="WATCHFUL",
        confidence=0.65,
        caution=0.58,
        usability="NEEDS_CONFIRMATION",
    )

    service = TradeClassificationService()
    result = service.classify_markets([market_id], source_type="phase6a_test")
    assert result is not None

    queries = TradeClassificationQueryService()
    classification = queries.get_trade_classification_details(market_id=market_id)
    assert classification is not None
    assert float(classification["classification_confidence"]) >= 0.0
    assert classification["risk_posture_class"] in {"BALANCED", "ELEVATED_RISK", "HIGH_RISK"}
    assert classification["suggested_bucket_class"] in {"RISKY_BUCKET", "CONVICTION_BUCKET", "NO_BUCKET"}
    assert len(classification["classification_reason_codes_json"]) >= 1


def test_sparse_context_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"sparse-{uuid4().hex[:6]}"
    question = "Will sparse market be classified cautiously?"
    _seed_market_cycle(market_id=market_id, question=question, slug="sparse", hours_to_close=120)

    service = TradeClassificationService()
    result = service.classify_markets([market_id], source_type="phase6a_test")
    assert result is not None

    queries = TradeClassificationQueryService()
    classification = queries.get_trade_classification_details(market_id=market_id)
    assert classification is not None
    assert classification["primary_trade_type"] == "NO_TRADE"
    assert "missing_cognition_context" in classification["classification_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"query-{uuid4().hex[:6]}"
    question = "Will query market resolve?"
    cycle_id = _seed_market_cycle(market_id=market_id, question=question, slug="query", hours_to_close=60)
    _seed_cognition_summary(market_id=market_id, question=question, cognition_conclusion="SUPPORTIVE", confidence=0.71, caution=0.38, usability="USABLE_NOW")

    service = TradeClassificationService()
    result = service.classify_cycle(cycle_id, source_ref="cycle-query")
    assert result is not None

    queries = TradeClassificationQueryService()
    summary = queries.get_trade_classification_run_summary(result.trade_classification_run_id)
    assert summary is not None
    assert summary["classification_count"] == 1

    rows = queries.list_trade_classifications_for_run(result.trade_classification_run_id)
    assert len(rows) == 1
    classification_id = str(rows[0]["id"])
    details = queries.get_trade_classification_details(trade_classification_id=classification_id)
    assert details is not None
    assert details["market_id"] == market_id

    by_type = queries.list_trade_classifications_by_type(str(details["primary_trade_type"]), limit=50)
    assert any(str(row["market_id"]) == market_id for row in by_type)

    comparison = queries.compare_trade_classification_to_upstream_context(market_id)
    assert comparison is not None
    assert comparison["classification"] is not None
    assert comparison["market_snapshot"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeTradeClassificationService:
        def classify_markets(self, market_ids, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["market_ids"] = market_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return TradeClassificationRunResult(
                trade_classification_run_id="trade-classification-cli-test",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

        def classify_cycle(self, cycle_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["cycle_id"] = cycle_id
            called["source_ref"] = source_ref
            return TradeClassificationRunResult(
                trade_classification_run_id="trade-classification-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.trade_classification.TradeClassificationService", FakeTradeClassificationService)

    exit_code = trade_classification_main(["--market-ids", "market-a", "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["market_ids"] == ["market-a"]
    assert called["source_ref"] == "cli-test"
    assert "trade-classification-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    market_id = f"safe-{uuid4().hex[:6]}"
    question = "Will safe trade classification stay isolated?"
    _seed_market_cycle(market_id=market_id, question=question, slug="safe", hours_to_close=36)
    _seed_cognition_summary(market_id=market_id, question=question, cognition_conclusion="SUPPORTIVE", confidence=0.72, caution=0.31, usability="USABLE_NOW")

    service = TradeClassificationService()
    service.classify_markets([market_id], source_type="phase6a_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
