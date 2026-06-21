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
from app.services.market_link_candidate import (
    MarketLinkCandidateService,
    _classify_link_status,
    _classify_usability,
    _derive_candidates,
    _score_relevance,
    main as market_link_main,
)
from app.services.query.market_link_query_service import MarketLinkQueryService
from app.services.recorders.phase1_cycle_persistence import Phase1CyclePersistenceService
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


def _success_response() -> str:
    return json.dumps(
        {
            "interpretations": [
                {
                    "event_type": "lineup_update",
                    "event_summary": "Key PSG striker ruled out tonight.",
                    "certainty_score": 0.91,
                    "ambiguity_score": 0.12,
                    "novelty_score": 0.77,
                    "directness_class": "direct_signal",
                    "directness_score": 0.89,
                    "contradiction_risk": 0.15,
                    "affected_market_candidates": [
                        {
                            "market_id_hint": "566136",
                            "question_hint": "PSG match outcome market",
                            "confidence": 0.82,
                            "rationale": "Team strength changes.",
                        }
                    ],
                    "affected_outcomes": ["NO"],
                    "recommended_action_class": "usable_now",
                    "explanation": {"why": "Lineup change alters win prob."},
                }
            ]
        }
    )


def _interpreter_input() -> EventInterpreterInput:
    return EventInterpreterInput(
        source_type="manual_event",
        source_ref="tweet:phase3b",
        raw_event_text="PSG striker ruled out for tonight.",
        raw_event_payload_json={"url": "https://example.com/1"},
        normalized_event_title="PSG striker ruled out",
    )


def _scored_market(
    *,
    market_id: str,
    question: str,
    slug: str,
    yes_price: float,
    no_price: float,
) -> ScoredMarket:
    now = datetime.now(UTC)
    market = NormalizedMarket(
        market_id=market_id,
        event_id=f"event-{market_id}",
        event_title=question,
        question=question,
        slug=slug,
        end_time=now,
        yes_price=yes_price,
        no_price=no_price,
        last_trade_price=yes_price,
        best_bid=max(0.0, yes_price - 0.01),
        best_ask=min(1.0, yes_price + 0.01),
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
        reason="seeded for phase3b tests",
        computed_at=now,
    )


def _seed_market_snapshots() -> None:
    persistence = Phase1CyclePersistenceService()
    handle = persistence.open_cycle(
        mode="SCAN_ONLY",
        trigger_source="phase3b_seed",
        top_n=2,
        pages_requested=1,
    )
    cycle_result = SimpleNamespace(
        top_scored=[
            _scored_market(
                market_id="566136",
                question="Will PSG beat Marseille tonight?",
                slug="psg-vs-marseille-tonight",
                yes_price=0.64,
                no_price=0.36,
            ),
            _scored_market(
                market_id="MARKET_002",
                question="Will Player Y transfer to Arsenal this summer?",
                slug="player-y-transfer-arsenal",
                yes_price=0.41,
                no_price=0.59,
            ),
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
            ),
            MarketRecommendation(
                rank=2,
                question="Will Player Y transfer to Arsenal this summer?",
                confidence=0.44,
                action="SKIP",
                reason="Weak context only.",
                yes_price=0.41,
                no_price=0.59,
                score=75.0,
                computed_at=datetime.now(UTC).isoformat(),
            ),
        ],
    )
    persistence.persist_cycle_snapshot(handle=handle, cycle_result=cycle_result)


def _seed_interpretation(postgres_test_schema) -> str:
    run_migrations()
    _seed_market_snapshots()
    service = ClaudeEventInterpreterService(client=FakeAnthropicClient(_success_response()))
    result = service.interpret_events(
        [_interpreter_input()], source_type="manual_event", source_ref="tweet:phase3b"
    )
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM event_interpretations LIMIT 1").fetchone()
    assert row is not None
    return str(row["id"])


def test_market_link_migrations_create_tables(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        ).fetchall()
    names = {r["table_name"] for r in tables}
    assert "market_link_runs" in names
    assert "market_link_candidates" in names


def test_successful_linking_run_persists_correctly(postgres_test_schema) -> None:
    interpretation_id = _seed_interpretation(postgres_test_schema)
    service = MarketLinkCandidateService()
    result = service.link_interpretations(
        [interpretation_id],
        source_type="test_batch",
        source_ref="phase3b-test",
    )

    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1
    assert result.failure_count == 0
    assert result.candidate_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        runs = conn.execute("SELECT * FROM market_link_runs").fetchall()
        candidates = conn.execute("SELECT * FROM market_link_candidates").fetchall()

    assert len(runs) == 1
    assert runs[0]["status"] == "COMPLETED"
    assert runs[0]["linker_version"] == "phase3b-market-linker-v1"

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["market_id"] == "566136"
    assert candidate["candidate_source"] == "INTERPRETER_MARKET_ID"
    assert candidate["link_status"] == "STRONG_CANDIDATE"
    assert candidate["usability_class"] == "USABLE_NOW"
    assert candidate["directness_class"] == "DIRECT_SIGNAL"
    assert str(candidate["interpretation_id"]) == interpretation_id


def test_candidate_matching_is_deterministic(postgres_test_schema) -> None:
    run_migrations()
    _seed_market_snapshots()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        market_catalog = conn.execute(
            """
            SELECT DISTINCT ON (market_id) market_id, question, slug
            FROM market_snapshots
            ORDER BY market_id, captured_at DESC, id DESC
            """
        ).fetchall()

    fake_interpretation = {
        "id": "fake-interp-id-000",
        "directness_class": "DIRECT_SIGNAL",
        "directness_score": 0.89,
        "contradiction_risk": 0.15,
        "ambiguity_score": 0.12,
        "recommended_action_class": "USABLE_NOW",
        "affected_market_candidates_json": [
            {
                "market_id_hint": "566136",
                "question_hint": "Will PSG beat Marseille tonight?",
                "confidence": 0.80,
                "rationale": "Direct impact on outcome.",
            },
            {
                "market_id_hint": None,
                "question_hint": "Player Y transfer speculation Arsenal",
                "confidence": 0.40,
                "rationale": "Indirect but plausible.",
            },
            {
                "market_id_hint": None,
                "question_hint": None,
                "confidence": 0.10,
                "rationale": "No usable hint.",
            },
        ],
        "affected_outcomes_json": ["YES"],
        "prompt_version": "phase3a-event-interpreter-v1",
        "model_name": "claude-opus-4-6",
    }

    candidates = _derive_candidates(
        run_id="run-test-000",
        interpretation=fake_interpretation,
        market_catalog=list(market_catalog),
        linker_version="phase3b-market-linker-v1",
    )

    assert len(candidates) == 2
    assert candidates[0].candidate_source == "INTERPRETER_MARKET_ID"
    assert candidates[0].market_id == "566136"
    assert candidates[0].link_status == "STRONG_CANDIDATE"

    assert candidates[1].candidate_source == "KEYWORD_MATCH"
    assert candidates[1].market_id == "MARKET_002"
    assert candidates[1].link_status == "CANDIDATE"
    assert candidates[1].usability_class == "USABLE_NOW"


def test_derive_candidates_returns_empty_for_no_match(postgres_test_schema) -> None:
    run_migrations()
    _seed_market_snapshots()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        market_catalog = conn.execute(
            """
            SELECT DISTINCT ON (market_id) market_id, question, slug
            FROM market_snapshots
            ORDER BY market_id, captured_at DESC, id DESC
            """
        ).fetchall()

    fake_interpretation = {
        "id": "fake-interp-empty",
        "directness_class": "WEAK_SIGNAL",
        "directness_score": 0.3,
        "contradiction_risk": 0.1,
        "ambiguity_score": 0.2,
        "recommended_action_class": "NEEDS_MORE_CONFIRMATION",
        "affected_market_candidates_json": [
            {
                "market_id_hint": None,
                "question_hint": "Completely unrelated commodity shock",
                "confidence": 0.55,
                "rationale": "No seeded market should match this.",
            }
        ],
        "affected_outcomes_json": [],
        "prompt_version": "phase3a-event-interpreter-v1",
        "model_name": "claude-opus-4-6",
    }

    candidates = _derive_candidates(
        run_id="run-empty",
        interpretation=fake_interpretation,
        market_catalog=list(market_catalog),
        linker_version="phase3b-market-linker-v1",
    )
    assert candidates == []


def test_score_relevance_direct_signal_boosts() -> None:
    score = _score_relevance(
        base_confidence=0.80,
        candidate_source="INTERPRETER_MARKET_ID",
        directness_class="DIRECT_SIGNAL",
        contradiction_risk=0.0,
    )
    assert score == 1.0


def test_score_relevance_high_contradiction_penalizes() -> None:
    score = _score_relevance(
        base_confidence=0.80,
        candidate_source="KEYWORD_MATCH",
        directness_class=None,
        contradiction_risk=0.75,
    )
    assert score == round(0.75, 5)


def test_classify_link_status_strong_candidate() -> None:
    assert _classify_link_status(0.85, "DIRECT_SIGNAL") == "STRONG_CANDIDATE"


def test_classify_usability_maps_action_class() -> None:
    assert _classify_usability("NEEDS_MORE_CONFIRMATION", None, None) == "NEEDS_CONFIRMATION"
    assert _classify_usability("USABLE_NOW", 0.1, 0.1) == "USABLE_NOW"


def test_linking_nonexistent_interpretation_is_recorded_as_failure(postgres_test_schema) -> None:
    run_migrations()
    service = MarketLinkCandidateService()
    result = service.link_interpretations(
        ["00000000-0000-0000-0000-000000000000"],
        source_type="test_batch",
        source_ref="nonexistent",
    )
    assert result is not None
    assert result.failure_count == 1
    assert result.success_count == 0
    assert result.candidate_count == 0

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM market_link_runs LIMIT 1").fetchone()
    assert run_row is not None
    assert run_row["status"] in {"FAILED", "COMPLETED_WITH_ERRORS"}


def test_linker_version_and_lineage_persisted(postgres_test_schema) -> None:
    interpretation_id = _seed_interpretation(postgres_test_schema)
    service = MarketLinkCandidateService()
    result = service.link_interpretations([interpretation_id], source_type="lineage_test")
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM market_link_runs LIMIT 1").fetchone()
        candidate_row = conn.execute("SELECT * FROM market_link_candidates LIMIT 1").fetchone()

    assert run_row["linker_version"] == "phase3b-market-linker-v1"
    assert candidate_row["linker_version"] == "phase3b-market-linker-v1"
    assert candidate_row["prompt_version"] == "phase3a-event-interpreter-v1"
    assert candidate_row["model_name"] == "claude-opus-4-6"
    assert str(candidate_row["interpretation_id"]) == interpretation_id


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    interpretation_id = _seed_interpretation(postgres_test_schema)
    service = MarketLinkCandidateService()
    result = service.link_interpretations([interpretation_id], source_type="query_test")
    assert result is not None

    queries = MarketLinkQueryService()
    summary = queries.get_market_link_run_summary(result.market_link_run_id)
    assert summary is not None
    assert summary["candidate_count"] == 1
    assert "STRONG_CANDIDATE" in summary["link_status_counts"]

    candidates = queries.list_market_link_candidates_for_run(result.market_link_run_id)
    assert len(candidates) == 1
    assert candidates[0]["market_id"] == "566136"

    candidate_id = str(candidates[0]["id"])
    details = queries.get_market_link_candidate_details(candidate_id)
    assert details is not None
    assert details["candidate_source"] == "INTERPRETER_MARKET_ID"

    links = queries.list_market_links_for_interpretation(interpretation_id)
    assert len(links) == 1

    comparison = queries.compare_linked_market_ids_to_interpreter_candidates(interpretation_id)
    assert comparison is not None
    assert comparison["total_hints"] == 1
    assert comparison["linked_count"] == 1
    assert len(comparison["matched_hints"]) == 1
    assert comparison["unmatched_hints"] == []


def test_link_interpretation_run_links_all_successes(postgres_test_schema) -> None:
    run_migrations()
    _seed_market_snapshots()
    interp_service = ClaudeEventInterpreterService(client=FakeAnthropicClient(_success_response()))
    interp_result = interp_service.interpret_events(
        [_interpreter_input()], source_type="manual_event", source_ref="run-link-test"
    )
    assert interp_result is not None

    service = MarketLinkCandidateService()
    result = service.link_interpretation_run(interp_result.interpretation_run_id)
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1
    assert result.candidate_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM market_link_runs LIMIT 1").fetchone()
    assert str(run_row["interpretation_run_id"]) == interp_result.interpretation_run_id


def test_safe_entry_point_works(postgres_test_schema, capsys) -> None:
    run_migrations()
    interpretation_id = _seed_interpretation(postgres_test_schema)

    exit_code = market_link_main(["--interpretation-ids", interpretation_id, "--source-ref", "cli-test"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "market_link_run_id=" in output
    assert "status=COMPLETED" in output
    assert "candidates=1" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    interpretation_id = _seed_interpretation(postgres_test_schema)
    service = MarketLinkCandidateService()
    service.link_interpretations([interpretation_id], source_type="isolation_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_runs = conn.execute("SELECT * FROM paper_runs").fetchall()
        shadow_runs = conn.execute("SELECT * FROM shadow_runs").fetchall()

    assert live_orders == []
    assert paper_runs == []
    assert shadow_runs == []


def test_explanation_json_contains_audit_trail(postgres_test_schema) -> None:
    interpretation_id = _seed_interpretation(postgres_test_schema)
    service = MarketLinkCandidateService()
    service.link_interpretations([interpretation_id], source_type="audit_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        candidate_row = conn.execute("SELECT * FROM market_link_candidates LIMIT 1").fetchone()

    explanation = candidate_row["explanation_json"]
    assert explanation["candidate_source"] == "INTERPRETER_MARKET_ID"
    assert explanation["market_id_hint"] == "566136"
    assert explanation["interpreter_rationale"] == "Team strength changes."
    assert explanation["matched_market_id"] == "566136"
    assert explanation["matched_market_question"] == "Will PSG beat Marseille tonight?"
    assert "match_detail" in explanation
    assert "usability_derivation" in explanation
