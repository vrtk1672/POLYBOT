from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.event_interpretation import EventInterpretationContract
from app.domain.contracts.event_interpretation_run import (
    EventInterpretationRunCloseContract,
    EventInterpretationRunOpenContract,
)
from app.services.recorders.event_interpretation_recorder import EventInterpretationRecorder
from app.services.recorders.event_interpretation_run_recorder import EventInterpretationRunRecorder

logger = logging.getLogger(__name__)

PROMPT_VERSION = "phase3a-event-interpreter-v1"
DEFAULT_MODEL = "claude-opus-4-6"
DIRECTNESS_CLASSES = {"DIRECT_SIGNAL", "WEAK_SIGNAL", "INDIRECT_CONTEXT"}
RECOMMENDED_ACTION_CLASSES = {
    "USABLE_NOW",
    "NEEDS_MORE_CONFIRMATION",
    "TOO_AMBIGUOUS",
    "IRRELEVANT",
}


@dataclass(slots=True)
class EventInterpreterInput:
    source_type: str
    raw_event_text: str
    source_ref: str | None = None
    raw_event_payload_json: dict[str, object] = field(default_factory=dict)
    normalized_event_title: str | None = None


@dataclass(slots=True)
class EventInterpretationRunResult:
    interpretation_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class MarketCandidateModel(BaseModel):
    market_id_hint: str | None = None
    question_hint: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=240)


class EventInterpretationModel(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    event_summary: str = Field(min_length=1, max_length=400)
    certainty_score: float = Field(ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    novelty_score: float | None = Field(default=None, ge=0.0, le=1.0)
    directness_class: str
    directness_score: float = Field(ge=0.0, le=1.0)
    contradiction_risk: float = Field(ge=0.0, le=1.0)
    affected_market_candidates: list[MarketCandidateModel]
    affected_outcomes: list[str]
    recommended_action_class: str
    explanation: dict[str, object] = Field(default_factory=dict)


class EventInterpreterResponseModel(BaseModel):
    interpretations: list[EventInterpretationModel]


class ClaudeEventInterpreterService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        client: anthropic.Anthropic | None = None,
        model_name: str = DEFAULT_MODEL,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._run_recorder = EventInterpretationRunRecorder()
        self._interpretation_recorder = EventInterpretationRecorder()
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def interpret_events(
        self,
        inputs: list[EventInterpreterInput],
        *,
        source_type: str,
        source_ref: str | None = None,
    ) -> EventInterpretationRunResult | None:
        if not self.enabled:
            return None
        if not inputs:
            raise ValueError("at least one event input is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0
        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    EventInterpretationRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        prompt_version=self._prompt_version,
                        model_name=self._model_name,
                        started_at=started_at,
                        input_count=len(inputs),
                        metadata_json={"source_ref": source_ref},
                    ),
                )
                response_text = self._invoke_model(inputs)
                parsed = self._parse_response(response_text, expected_count=len(inputs))
                for event_input, result in zip(inputs, parsed, strict=True):
                    record = self._build_success_contract(
                        run_id=run_id,
                        event_input=event_input,
                        result=result,
                    )
                    self._interpretation_recorder.record(conn, record)
                    success_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    EventInterpretationRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"model_name": self._model_name},
                    ),
                )
            return EventInterpretationRunResult(
                interpretation_run_id=run_id,
                status="COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS",
                input_count=len(inputs),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("event_interpreter_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if success_count == 0:
                    self._run_recorder.open_run(
                        conn,
                        EventInterpretationRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            prompt_version=self._prompt_version,
                            model_name=self._model_name,
                            started_at=started_at,
                            input_count=len(inputs),
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                if isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError)):
                    failure_count = len(inputs)
                    for event_input in inputs:
                        self._interpretation_recorder.record(
                            conn,
                            self._build_failure_contract(
                                run_id=run_id,
                                event_input=event_input,
                                status="PARSE_ERROR",
                                error_text=str(exc),
                            ),
                        )
                else:
                    failure_count = len(inputs)
                    for event_input in inputs:
                        self._interpretation_recorder.record(
                            conn,
                            self._build_failure_contract(
                                run_id=run_id,
                                event_input=event_input,
                                status="MODEL_ERROR",
                                error_text=str(exc),
                            ),
                        )
                self._run_recorder.close_run(
                    conn,
                    EventInterpretationRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"error": str(exc), "model_name": self._model_name},
                    ),
                )
            return EventInterpretationRunResult(
                interpretation_run_id=run_id,
                status="FAILED",
                input_count=len(inputs),
                success_count=success_count,
                failure_count=failure_count,
            )

    def _invoke_model(self, inputs: list[EventInterpreterInput]) -> str:
        client = self._client or self._build_client()
        response = client.messages.create(
            model=self._model_name,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{
                "type": "text",
                "text": _system_prompt(self._prompt_version),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_user_prompt(inputs)}],
        )
        return _extract_json_text(response)

    def _build_client(self) -> anthropic.Anthropic:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the event interpreter")
        return anthropic.Anthropic(api_key=api_key)

    def _parse_response(self, response_text: str, *, expected_count: int) -> list[EventInterpretationModel]:
        payload = json.loads(response_text)
        parsed = EventInterpreterResponseModel.model_validate(payload)
        if len(parsed.interpretations) != expected_count:
            raise ValueError(
                f"expected {expected_count} interpretations but received {len(parsed.interpretations)}"
            )
        normalized: list[EventInterpretationModel] = []
        for item in parsed.interpretations:
            directness_class = item.directness_class.upper()
            if directness_class not in DIRECTNESS_CLASSES:
                raise ValueError(f"unsupported directness_class: {item.directness_class}")
            recommended_action_class = item.recommended_action_class.upper()
            if recommended_action_class not in RECOMMENDED_ACTION_CLASSES:
                raise ValueError(
                    f"unsupported recommended_action_class: {item.recommended_action_class}"
                )
            normalized.append(
                item.model_copy(
                    update={
                        "directness_class": directness_class,
                        "recommended_action_class": recommended_action_class,
                        "event_type": item.event_type.upper(),
                    }
                )
            )
        return normalized

    def _build_success_contract(
        self,
        *,
        run_id: str,
        event_input: EventInterpreterInput,
        result: EventInterpretationModel,
    ) -> EventInterpretationContract:
        return EventInterpretationContract(
            id=str(uuid4()),
            interpretation_run_id=run_id,
            source_type=event_input.source_type,
            source_ref=event_input.source_ref,
            status="SUCCESS",
            error_text=None,
            raw_event_text=event_input.raw_event_text,
            raw_event_payload_json=event_input.raw_event_payload_json,
            normalized_event_title=event_input.normalized_event_title,
            event_type=result.event_type,
            event_summary=result.event_summary,
            certainty_score=_normalize_score(result.certainty_score),
            ambiguity_score=_normalize_score(result.ambiguity_score),
            novelty_score=_normalize_score(result.novelty_score),
            directness_class=result.directness_class,
            directness_score=_normalize_score(result.directness_score),
            contradiction_risk=_normalize_score(result.contradiction_risk),
            affected_market_candidates_json=[candidate.model_dump() for candidate in result.affected_market_candidates],
            affected_outcomes_json=result.affected_outcomes,
            recommended_action_class=result.recommended_action_class,
            explanation_json=result.explanation,
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )

    def _build_failure_contract(
        self,
        *,
        run_id: str,
        event_input: EventInterpreterInput,
        status: str,
        error_text: str,
    ) -> EventInterpretationContract:
        return EventInterpretationContract(
            id=str(uuid4()),
            interpretation_run_id=run_id,
            source_type=event_input.source_type,
            source_ref=event_input.source_ref,
            status=status,
            error_text=error_text,
            raw_event_text=event_input.raw_event_text,
            raw_event_payload_json=event_input.raw_event_payload_json,
            normalized_event_title=event_input.normalized_event_title,
            event_type=None,
            event_summary=None,
            certainty_score=None,
            ambiguity_score=None,
            novelty_score=None,
            directness_class=None,
            directness_score=None,
            contradiction_risk=None,
            affected_market_candidates_json=[],
            affected_outcomes_json=[],
            recommended_action_class=None,
            explanation_json={"error": error_text},
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )


def _system_prompt(prompt_version: str) -> str:
    return f"""You are POLYBOT's Claude Event Interpreter.
Prompt version: {prompt_version}

Interpret each input event into structured cognition only.
Do not recommend executing a trade directly.
Do not discuss portfolio allocation.
Return ONLY valid JSON matching the required schema.

directness_class must be one of:
- DIRECT_SIGNAL
- WEAK_SIGNAL
- INDIRECT_CONTEXT

recommended_action_class must be one of:
- USABLE_NOW
- NEEDS_MORE_CONFIRMATION
- TOO_AMBIGUOUS
- IRRELEVANT

Score rules:
- certainty_score, ambiguity_score, novelty_score, directness_score, contradiction_risk are all between 0.0 and 1.0
- higher certainty means clearer interpretation
- higher ambiguity means more uncertainty or unresolved meaning
- higher contradiction_risk means the event likely conflicts with existing assumptions or has contested interpretations

affected_market_candidates should be a list of concise market hints with confidence and rationale.
affected_outcomes should only include specific outcomes when truly supportable.
"""


def _build_user_prompt(inputs: list[EventInterpreterInput]) -> str:
    payload = [
        {
            "source_type": item.source_type,
            "source_ref": item.source_ref,
            "normalized_event_title": item.normalized_event_title,
            "raw_event_text": item.raw_event_text,
            "raw_event_payload_json": item.raw_event_payload_json,
        }
        for item in inputs
    ]
    return (
        "Interpret these event inputs and return one structured interpretation per input.\n\n"
        f"Input events:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return a JSON object with this exact shape:\n"
        "{\n"
        '  "interpretations": [\n'
        "    {\n"
        '      "event_type": "RESULT_UPDATE",\n'
        '      "event_summary": "short factual summary",\n'
        '      "certainty_score": 0.0,\n'
        '      "ambiguity_score": 0.0,\n'
        '      "novelty_score": 0.0,\n'
        '      "directness_class": "DIRECT_SIGNAL",\n'
        '      "directness_score": 0.0,\n'
        '      "contradiction_risk": 0.0,\n'
        '      "affected_market_candidates": [\n'
        "        {\n"
        '          "market_id_hint": "optional market id string",\n'
        '          "question_hint": "short market hint",\n'
        '          "confidence": 0.0,\n'
        '          "rationale": "short reason"\n'
        "        }\n"
        "      ],\n"
        '      "affected_outcomes": ["YES"],\n'
        '      "recommended_action_class": "USABLE_NOW",\n'
        '      "explanation": {\n'
        '        "why": "brief explanation",\n'
        '        "ambiguities": ["..."],\n'
        '        "contradictions": ["..."]\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )


def _extract_json_text(response: anthropic.types.Message | Any) -> str:
    text_parts = [block.text for block in response.content if hasattr(block, "text") and block.text]
    full_text = "\n".join(text_parts).strip()
    try:
        json.loads(full_text)
        return full_text
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", full_text)
    if match:
        candidate = match.group()
        json.loads(candidate)
        return candidate
    raise ValueError(f"No valid JSON found in response. Text: {full_text[:300]}")


def _normalize_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(min(1.0, max(0.0, float(value))), 5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the POLYBOT Claude event interpreter")
    parser.add_argument("--source-type", default="manual_event", help="source type label")
    parser.add_argument("--source-ref", default=None, help="optional source reference")
    parser.add_argument("--event-text", required=True, help="raw event text to interpret")
    parser.add_argument("--event-title", default=None, help="optional normalized event title")
    parser.add_argument("--payload-json", default="{}", help="optional raw payload JSON")
    args = parser.parse_args(argv)

    payload = json.loads(args.payload_json)
    service = ClaudeEventInterpreterService()
    result = service.interpret_events(
        [
            EventInterpreterInput(
                source_type=args.source_type,
                source_ref=args.source_ref,
                raw_event_text=args.event_text,
                raw_event_payload_json=payload,
                normalized_event_title=args.event_title,
            )
        ],
        source_type=args.source_type,
        source_ref=args.source_ref,
    )
    if result is None:
        print("Event interpreter persistence is unavailable.")
        return 1
    print(
        f"interpretation_run_id={result.interpretation_run_id} "
        f"status={result.status} success={result.success_count} failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
