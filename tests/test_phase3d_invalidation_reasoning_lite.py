from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.services.event_interpreter import ClaudeEventInterpreterService, EventInterpreterInput
from app.services.invalidation_reasoning_lite import (
    InvalidationReasoningLiteService,
    InvalidationReasoningRunResult,
    main as invalidation_reasoning_main,
)
from app.services.market_link_candidate import MarketLinkCandidateService
from app.services.query.invalidation_reasoning_query_service import InvalidationReasoningQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
from app.services.resolution_analyzer_lite import ResolutionAnalyzerLiteService
from app.stage2.claude_analyst import MarketRecommendation


class FakeAnthropicResponse:
    def __init__(self, text: str) -> None:
        self.content = [SimpleNamespace(text=text)]


class FakeAnthropicClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict[str, object]] = []
        self.messages = self

    def create(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        return FakeAnthropicResponse(self._text)


def _success_interpreter_response() -> str:
    return json.dumps(
        {
            "interpretations": [
                {
                    "event_type": "lineup_update",
                    "event_summary": "A key PSG striker is unavailable tonight due to injury.",
                    "certainty_score": 0.91,
                    "ambiguity_score": 0.12,
                    "novelty_score": 0.77,
                    "directness_class": "direct_signal",
                    "directness_score": 0.89,
                    "contradiction_risk": 0.15,
                    "affected_market_candidates": [
                        {
                            "market_id_hint": "566136",
                            "question_hint": "Will PSG beat Marseille tonight?",
                            "confidence": 0.82,
                            "rationale": "Lineup change directly affects the match outcome.",
                        }
                    ],
                    "affected_outcomes": ["NO"],
                    "recommended_action_class": "usable_now",
                    "explanation": {"why": "Confirmed lineup change affects PSG strength."},
                }
            ]
        }
    )


def _success_resolution_response() -> str:
    return json.dumps(
        {
            "analyses": [
                {
                    "resolution_summary": "The injury update directly affects the match winner wording without changing the market definition.",
                    "wording_clarity_score": 0.88,
                    "ambiguity_risk_score": 0.16,
                    "resolution_mismatch_risk": 0.12,
                    "resolution_confidence_score": 0.87,
                    "direct_fit_class": "direct_fit",
                    "usable_now_class": "usable_now",
                    "explanation": {
                        "fit_reason": "The market asks who wins the match, and the injury update changes team strength directly.",
                        "ambiguities": ["Replacement player quality is not fully known."],
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
                    "reasoning_summary": "The injury does not invalidate the thesis, but it is meaningful enough to degrade confidence and keep the market under watch.",
                    "thesis_effect_class": "warning",
                    "invalidation_risk_score": 0.38,
                    "confidence_degradation_score": 0.44,
                    "contradiction_strength_score": 0.35,
                    "recommended_monitoring_class": "watch",
                    "advisory_action_class": "degrade_confidence",
                    "explanation": {
                        "thesis_reason": "The event weakens PSG's position but does not overturn the market premise.",
                        "support_points": [],
                        "contradiction_points": ["Lineup strength is weaker than previously assumed."],
                        "monitoring_triggers": ["Further confirmed injuries", "Late lineup changes"],
                    },
                }
            ]
        }
    )


def _sample_input() -> EventInterpreterInput:
    return EventInterpreterInput(
        source_type="manual_event",
        source_ref="tweet:invalidation-lite",
        raw_event_text="PSG striker ruled out for tonight after confirmed injury report.",
        raw_event_payload_json={"url": "https://example.com/post/1"},
        normalized_event_title="PSG striker ruled out",
    )


def _scored_market(*, market_id: str, question: str, slug: str) -> ScoredMarket:
    now = datetime.now(UTC)
    market = NormalizedMarket(
        market_id=market_id,
        event_id=f"event-{market_id}",
        event_title=question,
        question=question,
        slug=slug,
        end_time=now,
        yes_price=0.64,
        no_price=0.36,
        last_trade_price=0.64,
        best_bid=0.63,
        best_ask=0.65,
        spread=0.02,
        liquidity=50000.0,
        volume=12000.0,
        volume_24h=8000.0,
        open_interest=1000.0,
        comment_count=25,
        competitive=0.8,
        accepting_orders=True,
        updated_at=now,
        raw_market={"market_id": market_id, "slug": slug, "question": question},
    )
    return ScoredMarket(
        market=market,
        score=80.0,
        breakdown=ScoreBreakdown(
            price_attractiveness=30.0,
            time_to_close=20.0,
            liquidity_volume=15.0,
            market_activity=15.0,
        ),
        reason="seeded for phase3d tests",
        computed_at=now,
    )


def _seed_market_snapshots() -> None:
    persistence = Phase1CyclePersistenceService()
    handle = persistence.open_cycle(
        mode="SCAN_ONLY",
        trigger_source="phase3d_seed",
        top_n=1,
        pages_requested=1,
    )
    cycle_result = SimpleNamespace(
        top_scored=[
            _scored_market(
                market_id="566136",
                question="Will PSG beat Marseille tonight?",
                slug="psg-vs-marseille-tonight",
            )
        ],
        recommendations=[
            MarketRecommendation(
                rank=1,
                question="Will PSG beat Marseille tonight?",
                confidence=0.82,
                action="BUY_NO",
                reason="Lineup downgrade supports No.",
                yes_price=0.64,
                no_price=0.36,
                score=80.0,
                computed_at=datetime.now(UTC).isoformat(),
            )
        ],
    )
    persistence.persist_cycle_snapshot(handle=handle, cycle_result=cycle_result)


def _seed_resolution_analysis() -> tuple[str, str, str, str]:
    run_migrations()
    _seed_market_snapshots()
    interpreter = ClaudeEventInterpreterService(client=FakeAnthropicClient(_success_interpreter_response()))
    interpretation_run = interpreter.interpret_events(
        [_sample_input()],
        source_type="manual_event",
        source_ref="tweet:invalidation-lite",
    )
    assert interpretation_run is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        interpretation_row = conn.execute("SELECT id FROM event_interpretations LIMIT 1").fetchone()
    assert interpretation_row is not None
    interpretation_id = str(interpretation_row["id"])

    linker = MarketLinkCandidateService()
    link_result = linker.link_interpretations([interpretation_id], source_type="phase3d_seed")
    assert link_result is not None

    with factory.connect() as conn:
        candidate_row = conn.execute("SELECT id, market_link_run_id FROM market_link_candidates LIMIT 1").fetchone()
    assert candidate_row is not None
    candidate_id = str(candidate_row["id"])

    analyzer = ResolutionAnalyzerLiteService(client=FakeAnthropicClient(_success_resolution_response()))
    resolution_result = analyzer.analyze_candidates(
        [candidate_id],
        source_type="phase3d_seed",
        market_link_run_id=str(candidate_row["market_link_run_id"]),
    )
    assert resolution_result is not None

    with factory.connect() as conn:
        analysis_row = conn.execute(
            "SELECT id, resolution_analysis_run_id FROM resolution_analyses LIMIT 1"
        ).fetchone()
    assert analysis_row is not None
    return (
        interpretation_id,
        candidate_id,
        str(analysis_row["id"]),
        str(analysis_row["resolution_analysis_run_id"]),
    )


def test_invalidation_reasoning_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"invalidation_reasoning_runs", "invalidation_reasonings"} <= table_names


def test_successful_invalidation_reasoning_persists_correctly(postgres_test_schema) -> None:
    interpretation_id, candidate_id, resolution_analysis_id, resolution_analysis_run_id = _seed_resolution_analysis()
    service = InvalidationReasoningLiteService(client=FakeAnthropicClient(_success_invalidation_response()))

    result = service.analyze_resolution_analyses(
        [resolution_analysis_id],
        source_type="invalidation_test",
        source_ref="phase3d-test",
        resolution_analysis_run_id=resolution_analysis_run_id,
    )

    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        runs = conn.execute("SELECT * FROM invalidation_reasoning_runs").fetchall()
        rows = conn.execute("SELECT * FROM invalidation_reasonings").fetchall()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert len(runs) == 1
    assert runs[0]["reasoner_version"] == "phase3d-invalidation-reasoning-lite-v1"
    assert runs[0]["prompt_version"] == "phase3d-invalidation-reasoning-lite-prompt-v1"
    assert runs[0]["model_name"] == "claude-opus-4-6"

    assert len(rows) == 1
    reasoning = rows[0]
    assert str(reasoning["interpretation_id"]) == interpretation_id
    assert str(reasoning["market_link_candidate_id"]) == candidate_id
    assert str(reasoning["resolution_analysis_id"]) == resolution_analysis_id
    assert reasoning["market_id"] == "566136"
    assert reasoning["market_question"] == "Will PSG beat Marseille tonight?"
    assert reasoning["status"] == "SUCCESS"
    assert reasoning["thesis_effect_class"] == "WARNING"
    assert reasoning["recommended_monitoring_class"] == "WATCH"
    assert reasoning["advisory_action_class"] == "DEGRADE_CONFIDENCE"
    assert live_orders == []
    assert paper_orders == []


def test_malformed_model_output_is_recorded_truthfully(postgres_test_schema) -> None:
    _, _, resolution_analysis_id, resolution_analysis_run_id = _seed_resolution_analysis()
    service = InvalidationReasoningLiteService(client=FakeAnthropicClient('{"reasonings": ['))

    result = service.analyze_resolution_analyses(
        [resolution_analysis_id],
        source_type="invalidation_test",
        source_ref="phase3d-bad",
        resolution_analysis_run_id=resolution_analysis_run_id,
    )
    assert result is not None
    assert result.status == "FAILED"
    assert result.failure_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM invalidation_reasoning_runs LIMIT 1").fetchone()
        reasoning_row = conn.execute("SELECT * FROM invalidation_reasonings LIMIT 1").fetchone()

    assert run_row is not None
    assert run_row["status"] == "FAILED"
    assert reasoning_row is not None
    assert reasoning_row["status"] == "PARSE_ERROR"
    assert reasoning_row["reasoning_summary"] is None
    assert reasoning_row["error_text"] is not None


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    _, _, resolution_analysis_id, resolution_analysis_run_id = _seed_resolution_analysis()
    service = InvalidationReasoningLiteService(client=FakeAnthropicClient(_success_invalidation_response()))
    result = service.analyze_resolution_analyses(
        [resolution_analysis_id],
        source_type="query_test",
        resolution_analysis_run_id=resolution_analysis_run_id,
    )
    assert result is not None

    queries = InvalidationReasoningQueryService()
    summary = queries.get_invalidation_reasoning_run_summary(result.invalidation_reasoning_run_id)
    assert summary is not None
    assert summary["reasoning_count"] == 1
    assert summary["status_counts"]["SUCCESS"] == 1

    rows = queries.list_invalidation_reasonings_for_run(result.invalidation_reasoning_run_id)
    assert len(rows) == 1
    reasoning_id = str(rows[0]["id"])
    details = queries.get_invalidation_reasoning_details(reasoning_id)
    assert details is not None
    assert details["model_name"] == "claude-opus-4-6"

    by_market = queries.list_invalidation_reasonings_for_market("566136", limit=5)
    assert len(by_market) == 1

    comparison = queries.compare_invalidation_reasoning_to_resolution_analysis(reasoning_id)
    assert comparison is not None
    assert comparison["resolution_analysis"] is not None
    assert comparison["resolution_analysis"]["market_id"] == "566136"


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeReasonerService:
        def analyze_resolution_analyses(self, analysis_ids, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["analysis_ids"] = analysis_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return InvalidationReasoningRunResult(
                invalidation_reasoning_run_id="invalidation-run-cli-test",
                status="COMPLETED",
                input_count=len(analysis_ids),
                success_count=len(analysis_ids),
                failure_count=0,
            )

        def analyze_resolution_run(self, resolution_analysis_run_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["resolution_analysis_run_id"] = resolution_analysis_run_id
            called["source_ref"] = source_ref
            return InvalidationReasoningRunResult(
                invalidation_reasoning_run_id="invalidation-run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.invalidation_reasoning_lite.InvalidationReasoningLiteService", FakeReasonerService)

    exit_code = invalidation_reasoning_main(
        ["--resolution-analysis-ids", "analysis-1", "--source-ref", "cli-test"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["analysis_ids"] == ["analysis-1"]
    assert called["source_ref"] == "cli-test"
    assert "invalidation-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    _, _, resolution_analysis_id, resolution_analysis_run_id = _seed_resolution_analysis()
    service = InvalidationReasoningLiteService(client=FakeAnthropicClient(_success_invalidation_response()))
    service.analyze_resolution_analyses(
        [resolution_analysis_id],
        source_type="isolation_test",
        resolution_analysis_run_id=resolution_analysis_run_id,
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
