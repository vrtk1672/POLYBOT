from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.invalidation_reasoning import InvalidationReasoningContract
from app.domain.contracts.invalidation_reasoning_run import (
    InvalidationReasoningRunCloseContract,
    InvalidationReasoningRunOpenContract,
)
from app.repositories.event_interpretations_repository import EventInterpretationsRepository
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository
from app.repositories.invalidation_reasoning_runs_repository import InvalidationReasoningRunsRepository
from app.repositories.resolution_analyses_repository import ResolutionAnalysesRepository
from app.repositories.resolution_analysis_runs_repository import ResolutionAnalysisRunsRepository
from app.services.recorders.invalidation_reasoning_recorder import InvalidationReasoningRecorder
from app.services.recorders.invalidation_reasoning_run_recorder import InvalidationReasoningRunRecorder

logger = logging.getLogger(__name__)

REASONER_VERSION = "phase3d-invalidation-reasoning-lite-v1"
PROMPT_VERSION = "phase3d-invalidation-reasoning-lite-prompt-v1"
DEFAULT_MODEL = "claude-opus-4-6"
THESIS_EFFECT_CLASSES = {
    "SUPPORTS_THESIS",
    "NEUTRAL",
    "WARNING",
    "CONTRADICTS_THESIS",
    "INVALIDATES_THESIS",
}
MONITORING_CLASSES = {"IGNORE", "WATCH", "ESCALATE", "INVALIDATION_CANDIDATE"}
ADVISORY_ACTION_CLASSES = {
    "NONE",
    "DEGRADE_CONFIDENCE",
    "REQUIRE_CONFIRMATION",
    "PREPARE_INVALIDATION_REVIEW",
}


@dataclass(slots=True)
class InvalidationReasoningRunResult:
    invalidation_reasoning_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class InvalidationReasoningModel(BaseModel):
    reasoning_summary: str = Field(min_length=1, max_length=400)
    thesis_effect_class: str
    invalidation_risk_score: float = Field(ge=0.0, le=1.0)
    confidence_degradation_score: float = Field(ge=0.0, le=1.0)
    contradiction_strength_score: float = Field(ge=0.0, le=1.0)
    recommended_monitoring_class: str
    advisory_action_class: str
    explanation: dict[str, object] = Field(default_factory=dict)


class InvalidationReasoningResponseModel(BaseModel):
    reasonings: list[InvalidationReasoningModel]


class InvalidationReasoningLiteService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        client: anthropic.Anthropic | None = None,
        model_name: str = DEFAULT_MODEL,
        prompt_version: str = PROMPT_VERSION,
        reasoner_version: str = REASONER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._client = client
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._reasoner_version = reasoner_version
        self._run_recorder = InvalidationReasoningRunRecorder()
        self._reasoning_recorder = InvalidationReasoningRecorder()
        self._resolution_analyses_repo = ResolutionAnalysesRepository()
        self._resolution_analysis_runs_repo = ResolutionAnalysisRunsRepository()
        self._candidate_repo = MarketLinkCandidatesRepository()
        self._interpretation_repo = EventInterpretationsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def analyze_resolution_run(
        self,
        resolution_analysis_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> InvalidationReasoningRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            analyses = self._resolution_analyses_repo.list_for_run(conn, resolution_analysis_run_id)
        analysis_ids = [str(row["id"]) for row in analyses]
        return self.analyze_resolution_analyses(
            analysis_ids,
            source_type="resolution_analysis_run",
            source_ref=source_ref or resolution_analysis_run_id,
            resolution_analysis_run_id=resolution_analysis_run_id,
        )

    def analyze_resolution_analyses(
        self,
        resolution_analysis_ids: list[str],
        *,
        source_type: str = "resolution_analysis_batch",
        source_ref: str | None = None,
        resolution_analysis_run_id: str | None = None,
    ) -> InvalidationReasoningRunResult | None:
        if not self.enabled:
            return None
        if not resolution_analysis_ids:
            raise ValueError("at least one resolution_analysis_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0

        try:
            with self._factory.connect() as conn, conn.transaction():
                if resolution_analysis_run_id is None:
                    first_analysis = self._resolution_analyses_repo.get_by_id(conn, resolution_analysis_ids[0])
                    resolution_analysis_run_id = (
                        str(first_analysis["resolution_analysis_run_id"]) if first_analysis is not None else None
                    )

                self._run_recorder.open_run(
                    conn,
                    InvalidationReasoningRunOpenContract(
                        id=run_id,
                        resolution_analysis_run_id=resolution_analysis_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        reasoner_version=self._reasoner_version,
                        prompt_version=self._prompt_version,
                        model_name=self._model_name,
                        started_at=started_at,
                        input_count=len(resolution_analysis_ids),
                        metadata_json={"source_ref": source_ref},
                    ),
                )

                contexts = [self._build_context(conn, analysis_id) for analysis_id in resolution_analysis_ids]
                response_text = self._invoke_model(contexts)
                parsed = self._parse_response(response_text, expected_count=len(contexts))

                for context, result in zip(contexts, parsed, strict=True):
                    self._reasoning_recorder.record(
                        conn,
                        self._build_success_contract(run_id=run_id, context=context, result=result),
                    )
                    success_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    InvalidationReasoningRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"reasoner_version": self._reasoner_version},
                    ),
                )

            return InvalidationReasoningRunResult(
                invalidation_reasoning_run_id=run_id,
                status=status,
                input_count=len(resolution_analysis_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("invalidation_reasoner_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if success_count == 0:
                    self._run_recorder.open_run(
                        conn,
                        InvalidationReasoningRunOpenContract(
                            id=run_id,
                            resolution_analysis_run_id=resolution_analysis_run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            reasoner_version=self._reasoner_version,
                            prompt_version=self._prompt_version,
                            model_name=self._model_name,
                            started_at=started_at,
                            input_count=len(resolution_analysis_ids),
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                failure_count = len(resolution_analysis_ids)
                error_status = (
                    "PARSE_ERROR"
                    if isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError))
                    else "MODEL_ERROR"
                )
                for analysis_id in resolution_analysis_ids:
                    context = self._build_context(conn, analysis_id)
                    self._reasoning_recorder.record(
                        conn,
                        self._build_failure_contract(
                            run_id=run_id,
                            context=context,
                            status=error_status,
                            error_text=str(exc),
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    InvalidationReasoningRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"error": str(exc), "reasoner_version": self._reasoner_version},
                    ),
                )
            return InvalidationReasoningRunResult(
                invalidation_reasoning_run_id=run_id,
                status="FAILED",
                input_count=len(resolution_analysis_ids),
                success_count=success_count,
                failure_count=failure_count,
            )

    def _build_context(self, conn, resolution_analysis_id: str) -> dict[str, object]:
        analysis = self._resolution_analyses_repo.get_by_id(conn, resolution_analysis_id)
        if analysis is None:
            raise ValueError(f"resolution_analysis not found: {resolution_analysis_id}")
        candidate = self._candidate_repo.get_by_id(conn, str(analysis["market_link_candidate_id"]))
        if candidate is None:
            raise ValueError(f"market_link_candidate not found for resolution_analysis: {resolution_analysis_id}")
        interpretation = self._interpretation_repo.get_by_id(conn, str(analysis["interpretation_id"]))
        if interpretation is None:
            raise ValueError(f"interpretation not found for resolution_analysis: {resolution_analysis_id}")

        raw_context = {
            "resolution_analysis": dict(analysis),
            "candidate": dict(candidate),
            "interpretation": dict(interpretation),
        }
        return {
            "resolution_analysis_id": str(analysis["id"]),
            "candidate_id": str(analysis["market_link_candidate_id"]),
            "interpretation_id": str(analysis["interpretation_id"]),
            "market_id": str(analysis["market_id"]),
            "market_question": str(analysis["market_question"]),
            "raw_context": _json_safe(raw_context),
        }

    def _invoke_model(self, contexts: list[dict[str, object]]) -> str:
        client = self._client or self._build_client()
        response = client.messages.create(
            model=self._model_name,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{
                "type": "text",
                "text": _system_prompt(self._prompt_version, self._reasoner_version),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_user_prompt(contexts)}],
        )
        return _extract_json_text(response)

    def _build_client(self) -> anthropic.Anthropic:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the invalidation reasoner")
        return anthropic.Anthropic(api_key=api_key)

    def _parse_response(self, response_text: str, *, expected_count: int) -> list[InvalidationReasoningModel]:
        payload = json.loads(response_text)
        parsed = InvalidationReasoningResponseModel.model_validate(payload)
        if len(parsed.reasonings) != expected_count:
            raise ValueError(f"expected {expected_count} reasonings but received {len(parsed.reasonings)}")

        normalized: list[InvalidationReasoningModel] = []
        for item in parsed.reasonings:
            thesis_effect_class = item.thesis_effect_class.upper()
            monitoring_class = item.recommended_monitoring_class.upper()
            advisory_action_class = item.advisory_action_class.upper()
            if thesis_effect_class not in THESIS_EFFECT_CLASSES:
                raise ValueError(f"unsupported thesis_effect_class: {item.thesis_effect_class}")
            if monitoring_class not in MONITORING_CLASSES:
                raise ValueError(f"unsupported recommended_monitoring_class: {item.recommended_monitoring_class}")
            if advisory_action_class not in ADVISORY_ACTION_CLASSES:
                raise ValueError(f"unsupported advisory_action_class: {item.advisory_action_class}")
            normalized.append(
                item.model_copy(
                    update={
                        "thesis_effect_class": thesis_effect_class,
                        "recommended_monitoring_class": monitoring_class,
                        "advisory_action_class": advisory_action_class,
                    }
                )
            )
        return normalized

    def _build_success_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        result: InvalidationReasoningModel,
    ) -> InvalidationReasoningContract:
        return InvalidationReasoningContract(
            id=str(uuid4()),
            invalidation_reasoning_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            resolution_analysis_id=str(context["resolution_analysis_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            raw_context_json=dict(context["raw_context"]),
            reasoning_summary=result.reasoning_summary,
            thesis_effect_class=result.thesis_effect_class,
            invalidation_risk_score=_normalize_score(result.invalidation_risk_score),
            confidence_degradation_score=_normalize_score(result.confidence_degradation_score),
            contradiction_strength_score=_normalize_score(result.contradiction_strength_score),
            recommended_monitoring_class=result.recommended_monitoring_class,
            advisory_action_class=result.advisory_action_class,
            explanation_json=result.explanation,
            status="SUCCESS",
            error_text=None,
            reasoner_version=self._reasoner_version,
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )

    def _build_failure_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        status: str,
        error_text: str,
    ) -> InvalidationReasoningContract:
        return InvalidationReasoningContract(
            id=str(uuid4()),
            invalidation_reasoning_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            resolution_analysis_id=str(context["resolution_analysis_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            raw_context_json=dict(context["raw_context"]),
            reasoning_summary=None,
            thesis_effect_class=None,
            invalidation_risk_score=None,
            confidence_degradation_score=None,
            contradiction_strength_score=None,
            recommended_monitoring_class=None,
            advisory_action_class=None,
            explanation_json={"error": error_text},
            status=status,
            error_text=error_text,
            reasoner_version=self._reasoner_version,
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )


def _system_prompt(prompt_version: str, reasoner_version: str) -> str:
    return f"""You are POLYBOT's Invalidation Reasoning Lite.
Prompt version: {prompt_version}
Reasoner version: {reasoner_version}

Assess whether the new event supports, weakens, contradicts, or invalidates the market thesis.
Return ONLY valid JSON matching the required schema.
Do not suggest executing a trade.
Do not discuss position sizing or order placement.

thesis_effect_class must be one of:
- SUPPORTS_THESIS
- NEUTRAL
- WARNING
- CONTRADICTS_THESIS
- INVALIDATES_THESIS

recommended_monitoring_class must be one of:
- IGNORE
- WATCH
- ESCALATE
- INVALIDATION_CANDIDATE

advisory_action_class must be one of:
- NONE
- DEGRADE_CONFIDENCE
- REQUIRE_CONFIRMATION
- PREPARE_INVALIDATION_REVIEW

All scores are between 0.0 and 1.0.
- invalidation_risk_score: higher means greater thesis invalidation risk
- confidence_degradation_score: higher means stronger confidence reduction
- contradiction_strength_score: higher means stronger contradiction rather than weak noise
"""


def _build_user_prompt(contexts: list[dict[str, object]]) -> str:
    payload = [
        {
            "resolution_analysis_id": context["resolution_analysis_id"],
            "candidate_id": context["candidate_id"],
            "interpretation_id": context["interpretation_id"],
            "market_id": context["market_id"],
            "market_question": context["market_question"],
            "raw_context": context["raw_context"],
        }
        for context in contexts
    ]
    return (
        "Analyze these resolution-analysis contexts for thesis invalidation reasoning.\n\n"
        f"Contexts:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return a JSON object with this exact shape:\n"
        "{\n"
        '  "reasonings": [\n'
        "    {\n"
        '      "reasoning_summary": "short thesis effect summary",\n'
        '      "thesis_effect_class": "WARNING",\n'
        '      "invalidation_risk_score": 0.0,\n'
        '      "confidence_degradation_score": 0.0,\n'
        '      "contradiction_strength_score": 0.0,\n'
        '      "recommended_monitoring_class": "WATCH",\n'
        '      "advisory_action_class": "DEGRADE_CONFIDENCE",\n'
        '      "explanation": {\n'
        '        "thesis_reason": "brief reason",\n'
        '        "support_points": ["..."],\n'
        '        "contradiction_points": ["..."],\n'
        '        "monitoring_triggers": ["..."]\n'
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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 3D invalidation reasoning lite")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolution-analysis-run-id", help="analyze all rows from this resolution analysis run")
    group.add_argument("--resolution-analysis-ids", nargs="+", help="analyze specific resolution analysis IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = InvalidationReasoningLiteService()
    if args.resolution_analysis_run_id:
        result = service.analyze_resolution_run(args.resolution_analysis_run_id, source_ref=args.source_ref)
    else:
        result = service.analyze_resolution_analyses(
            args.resolution_analysis_ids,
            source_type="manual_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Invalidation reasoning persistence is unavailable.")
        return 1

    print(
        f"invalidation_reasoning_run_id={result.invalidation_reasoning_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
