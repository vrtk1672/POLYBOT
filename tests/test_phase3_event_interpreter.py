from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.event_interpreter import (
    ClaudeEventInterpreterService,
    EventInterpreterInput,
    EventInterpretationRunResult,
    main as event_interpreter_main,
)
from app.services.query.event_interpretation_query_service import EventInterpretationQueryService


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


def _sample_input() -> EventInterpreterInput:
    return EventInterpreterInput(
        source_type="manual_event",
        source_ref="tweet:1",
        raw_event_text="PSG striker ruled out for tonight after confirmed injury report.",
        raw_event_payload_json={"url": "https://example.com/post/1"},
        normalized_event_title="PSG striker ruled out",
    )


def _success_response() -> str:
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
                            "question_hint": "PSG match outcome market",
                            "confidence": 0.82,
                            "rationale": "Team strength directly changes."
                        }
                    ],
                    "affected_outcomes": ["NO"],
                    "recommended_action_class": "usable_now",
                    "explanation": {
                        "why": "Lineup confirmation directly changes expected strength.",
                        "ambiguities": ["Replacement quality not fully known."],
                        "contradictions": [],
                    },
                }
            ]
        }
    )


def test_event_interpreter_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"event_interpretation_runs", "event_interpretations"} <= table_names


def test_successful_event_interpretation_persists_correctly(postgres_test_schema) -> None:
    run_migrations()
    fake_client = FakeAnthropicClient(_success_response())
    service = ClaudeEventInterpreterService(client=fake_client)

    result = service.interpret_events([_sample_input()], source_type="manual_event", source_ref="tweet:1")
    assert result is not None
    assert result.status == "COMPLETED"

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        runs = conn.execute("SELECT * FROM event_interpretation_runs").fetchall()
        interpretations = conn.execute("SELECT * FROM event_interpretations").fetchall()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_runs = conn.execute("SELECT * FROM paper_runs").fetchall()

    assert len(runs) == 1
    assert runs[0]["prompt_version"] == "phase3a-event-interpreter-v1"
    assert runs[0]["model_name"] == "claude-opus-4-6"
    assert len(interpretations) == 1
    assert interpretations[0]["status"] == "SUCCESS"
    assert interpretations[0]["event_type"] == "LINEUP_UPDATE"
    assert interpretations[0]["directness_class"] == "DIRECT_SIGNAL"
    assert interpretations[0]["recommended_action_class"] == "USABLE_NOW"
    assert len(live_orders) == 0
    assert len(paper_runs) == 0


def test_malformed_model_output_is_recorded_truthfully(postgres_test_schema) -> None:
    run_migrations()
    fake_client = FakeAnthropicClient('{"interpretations": [')
    service = ClaudeEventInterpreterService(client=fake_client)

    result = service.interpret_events([_sample_input()], source_type="manual_event", source_ref="tweet:bad")
    assert result is not None
    assert result.status == "FAILED"
    assert result.failure_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM event_interpretation_runs LIMIT 1").fetchone()
        interpretation_row = conn.execute("SELECT * FROM event_interpretations LIMIT 1").fetchone()

    assert run_row is not None
    assert run_row["status"] == "FAILED"
    assert interpretation_row is not None
    assert interpretation_row["status"] == "PARSE_ERROR"
    assert interpretation_row["event_type"] is None
    assert interpretation_row["error_text"] is not None


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    service = ClaudeEventInterpreterService(client=FakeAnthropicClient(_success_response()))
    result = service.interpret_events([_sample_input()], source_type="manual_event", source_ref="tweet:1")
    assert result is not None

    queries = EventInterpretationQueryService()
    summary = queries.get_interpretation_run_summary(result.interpretation_run_id)
    assert summary is not None
    assert summary["status_counts"]["success"] == 1

    interpretations = queries.list_interpretations_for_run(result.interpretation_run_id)
    assert len(interpretations) == 1
    details = queries.get_interpretation_details(str(interpretations[0]["id"]))
    assert details is not None
    assert details["model_name"] == "claude-opus-4-6"

    recent = queries.list_recent_interpretations(limit=5)
    assert len(recent) == 1

    matches = queries.compare_interpretation_candidates_to_existing_market_ids(str(interpretations[0]["id"]))
    assert matches is not None
    assert matches["matches"] == []


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeInterpreterService:
        def interpret_events(self, inputs, *, source_type: str, source_ref: str | None = None):  # noqa: ANN001
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            called["raw_event_text"] = inputs[0].raw_event_text
            return EventInterpretationRunResult(
                interpretation_run_id="run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.event_interpreter.ClaudeEventInterpreterService", FakeInterpreterService)

    exit_code = event_interpreter_main(
        [
            "--source-type",
            "manual_event",
            "--source-ref",
            "tweet:cli",
            "--event-text",
            "Breaking event text",
            "--payload-json",
            '{"foo": "bar"}',
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["source_type"] == "manual_event"
    assert called["source_ref"] == "tweet:cli"
    assert called["raw_event_text"] == "Breaking event text"
    assert "run-cli-test" in output
