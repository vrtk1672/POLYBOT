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
from app.domain.contracts.cognition_summary import CognitionSummaryContract
from app.domain.contracts.cognition_summary_run import (
    CognitionSummaryRunCloseContract,
    CognitionSummaryRunOpenContract,
)
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.cognition_summary_runs_repository import CognitionSummaryRunsRepository
from app.repositories.event_interpretations_repository import EventInterpretationsRepository
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository
from app.repositories.resolution_analyses_repository import ResolutionAnalysesRepository
from app.services.recorders.cognition_summary_recorder import CognitionSummaryRecorder
from app.services.recorders.cognition_summary_run_recorder import CognitionSummaryRunRecorder

logger = logging.getLogger(__name__)

NARRATOR_VERSION = "phase3e-cognition-summary-v1"
PROMPT_VERSION = "phase3e-cognition-summary-prompt-v1"
DEFAULT_MODEL = "claude-opus-4-6"
CONCLUSION_CLASSES = {"SUPPORTIVE", "WATCHFUL", "RISKY", "CONTRADICTORY", "INVALIDATION_CANDIDATE"}
USABILITY_CLASSES = {"USABLE_NOW", "NEEDS_CONFIRMATION", "TOO_AMBIGUOUS", "DO_NOT_USE"}
OPERATOR_FOCUS_CLASSES = {"NONE", "MONITOR", "REVIEW_LINKING", "REVIEW_RESOLUTION", "REVIEW_INVALIDATION"}


@dataclass(slots=True)
class CognitionSummaryRunResult:
    cognition_summary_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class CognitionSummaryModel(BaseModel):
    narration_summary: str = Field(min_length=1, max_length=500)
    concise_narration_text: str = Field(min_length=1, max_length=500)
    cognition_conclusion_class: str
    overall_confidence_score: float = Field(ge=0.0, le=1.0)
    caution_score: float = Field(ge=0.0, le=1.0)
    usability_class: str
    recommended_operator_focus: str
    evidence: dict[str, object] = Field(default_factory=dict)


class CognitionSummaryResponseModel(BaseModel):
    summaries: list[CognitionSummaryModel]


class CognitionSummaryService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        client: anthropic.Anthropic | None = None,
        model_name: str = DEFAULT_MODEL,
        prompt_version: str = PROMPT_VERSION,
        narrator_version: str = NARRATOR_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._client = client
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._narrator_version = narrator_version
        self._run_recorder = CognitionSummaryRunRecorder()
        self._summary_recorder = CognitionSummaryRecorder()
        self._reasonings_repo = InvalidationReasoningsRepository()
        self._resolution_repo = ResolutionAnalysesRepository()
        self._candidate_repo = MarketLinkCandidatesRepository()
        self._interpretation_repo = EventInterpretationsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def summarize_reasonings(
        self,
        invalidation_reasoning_ids: list[str],
        *,
        source_type: str = "invalidation_reasoning_batch",
        source_ref: str | None = None,
    ) -> CognitionSummaryRunResult | None:
        if not self.enabled:
            return None
        if not invalidation_reasoning_ids:
            raise ValueError("at least one invalidation_reasoning_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    CognitionSummaryRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        narrator_version=self._narrator_version,
                        prompt_version=self._prompt_version,
                        model_name=self._model_name,
                        started_at=started_at,
                        input_count=len(invalidation_reasoning_ids),
                        metadata_json={"source_ref": source_ref},
                    ),
                )

                contexts = [self._build_context(conn, reasoning_id) for reasoning_id in invalidation_reasoning_ids]
                response_text = self._invoke_model(contexts)
                parsed = self._parse_response(response_text, expected_count=len(contexts))

                for context, result in zip(contexts, parsed, strict=True):
                    self._summary_recorder.record(
                        conn,
                        self._build_success_contract(run_id=run_id, context=context, result=result),
                    )
                    success_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    CognitionSummaryRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"narrator_version": self._narrator_version},
                    ),
                )

            return CognitionSummaryRunResult(
                cognition_summary_run_id=run_id,
                status=status,
                input_count=len(invalidation_reasoning_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("cognition_summary_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if success_count == 0:
                    self._run_recorder.open_run(
                        conn,
                        CognitionSummaryRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            narrator_version=self._narrator_version,
                            prompt_version=self._prompt_version,
                            model_name=self._model_name,
                            started_at=started_at,
                            input_count=len(invalidation_reasoning_ids),
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                failure_count = len(invalidation_reasoning_ids)
                error_status = (
                    "PARSE_ERROR"
                    if isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError))
                    else "MODEL_ERROR"
                )
                for reasoning_id in invalidation_reasoning_ids:
                    context = self._build_context(conn, reasoning_id)
                    self._summary_recorder.record(
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
                    CognitionSummaryRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"error": str(exc), "narrator_version": self._narrator_version},
                    ),
                )
            return CognitionSummaryRunResult(
                cognition_summary_run_id=run_id,
                status="FAILED",
                input_count=len(invalidation_reasoning_ids),
                success_count=success_count,
                failure_count=failure_count,
            )

    def _build_context(self, conn, invalidation_reasoning_id: str) -> dict[str, object]:
        reasoning = self._reasonings_repo.get_by_id(conn, invalidation_reasoning_id)
        if reasoning is None:
            raise ValueError(f"invalidation_reasoning not found: {invalidation_reasoning_id}")
        resolution = self._resolution_repo.get_by_id(conn, str(reasoning["resolution_analysis_id"]))
        if resolution is None:
            raise ValueError(f"resolution_analysis not found for invalidation_reasoning: {invalidation_reasoning_id}")
        candidate = self._candidate_repo.get_by_id(conn, str(reasoning["market_link_candidate_id"]))
        if candidate is None:
            raise ValueError(f"market_link_candidate not found for invalidation_reasoning: {invalidation_reasoning_id}")
        interpretation = self._interpretation_repo.get_by_id(conn, str(reasoning["interpretation_id"]))
        if interpretation is None:
            raise ValueError(f"interpretation not found for invalidation_reasoning: {invalidation_reasoning_id}")

        event_summary_snapshot = str(interpretation["event_summary"])
        raw_context = _json_safe(
            {
                "invalidation_reasoning": dict(reasoning),
                "resolution_analysis": dict(resolution),
                "candidate": dict(candidate),
                "interpretation": dict(interpretation),
            }
        )
        return {
            "invalidation_reasoning_id": str(reasoning["id"]),
            "resolution_analysis_id": str(reasoning["resolution_analysis_id"]),
            "candidate_id": str(reasoning["market_link_candidate_id"]),
            "interpretation_id": str(reasoning["interpretation_id"]),
            "market_id": str(reasoning["market_id"]),
            "market_question": str(reasoning["market_question"]),
            "event_summary_snapshot": event_summary_snapshot,
            "raw_context": raw_context,
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
                "text": _system_prompt(self._prompt_version, self._narrator_version),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_user_prompt(contexts)}],
        )
        return _extract_json_text(response)

    def _build_client(self) -> anthropic.Anthropic:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for cognition summary narration")
        return anthropic.Anthropic(api_key=api_key)

    def _parse_response(self, response_text: str, *, expected_count: int) -> list[CognitionSummaryModel]:
        payload = json.loads(response_text)
        parsed = CognitionSummaryResponseModel.model_validate(payload)
        if len(parsed.summaries) != expected_count:
            raise ValueError(f"expected {expected_count} summaries but received {len(parsed.summaries)}")

        normalized: list[CognitionSummaryModel] = []
        for item in parsed.summaries:
            conclusion = item.cognition_conclusion_class.upper()
            usability = item.usability_class.upper()
            operator_focus = item.recommended_operator_focus.upper()
            if conclusion not in CONCLUSION_CLASSES:
                raise ValueError(f"unsupported cognition_conclusion_class: {item.cognition_conclusion_class}")
            if usability not in USABILITY_CLASSES:
                raise ValueError(f"unsupported usability_class: {item.usability_class}")
            if operator_focus not in OPERATOR_FOCUS_CLASSES:
                raise ValueError(f"unsupported recommended_operator_focus: {item.recommended_operator_focus}")
            normalized.append(
                item.model_copy(
                    update={
                        "cognition_conclusion_class": conclusion,
                        "overall_confidence_score": _normalize_score(item.overall_confidence_score),
                        "caution_score": _normalize_score(item.caution_score),
                        "usability_class": usability,
                        "recommended_operator_focus": operator_focus,
                    }
                )
            )
        return normalized

    def _build_success_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        result: CognitionSummaryModel,
    ) -> CognitionSummaryContract:
        return CognitionSummaryContract(
            id=str(uuid4()),
            cognition_summary_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            resolution_analysis_id=str(context["resolution_analysis_id"]),
            invalidation_reasoning_id=str(context["invalidation_reasoning_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            event_summary_snapshot=str(context["event_summary_snapshot"]),
            raw_context_json=dict(context["raw_context"]),
            narration_summary=result.narration_summary,
            concise_narration_text=result.concise_narration_text,
            cognition_conclusion_class=result.cognition_conclusion_class,
            overall_confidence_score=_normalize_score(result.overall_confidence_score),
            caution_score=_normalize_score(result.caution_score),
            usability_class=result.usability_class,
            recommended_operator_focus=result.recommended_operator_focus,
            evidence_json=result.evidence,
            status="SUCCESS",
            error_text=None,
            narrator_version=self._narrator_version,
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
    ) -> CognitionSummaryContract:
        return CognitionSummaryContract(
            id=str(uuid4()),
            cognition_summary_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            resolution_analysis_id=str(context["resolution_analysis_id"]),
            invalidation_reasoning_id=str(context["invalidation_reasoning_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            event_summary_snapshot=str(context["event_summary_snapshot"]),
            raw_context_json=dict(context["raw_context"]),
            narration_summary=None,
            concise_narration_text=None,
            cognition_conclusion_class=None,
            overall_confidence_score=None,
            caution_score=None,
            usability_class=None,
            recommended_operator_focus=None,
            evidence_json={"error": error_text},
            status=status,
            error_text=error_text,
            narrator_version=self._narrator_version,
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )


def _system_prompt(prompt_version: str, narrator_version: str) -> str:
    return f"""You are POLYBOT's Decision Narration / Cognition Summary Layer.
Prompt version: {prompt_version}
Narrator version: {narrator_version}

Summarize the upstream cognition stack into a structured, operator-usable market-context summary.
Return ONLY valid JSON matching the required schema.
Do not suggest executing a trade.
Do not discuss order placement, sizing, or positions.

cognition_conclusion_class must be one of:
- SUPPORTIVE
- WATCHFUL
- RISKY
- CONTRADICTORY
- INVALIDATION_CANDIDATE

usability_class must be one of:
- USABLE_NOW
- NEEDS_CONFIRMATION
- TOO_AMBIGUOUS
- DO_NOT_USE

recommended_operator_focus must be one of:
- NONE
- MONITOR
- REVIEW_LINKING
- REVIEW_RESOLUTION
- REVIEW_INVALIDATION

All scores are between 0.0 and 1.0.
- overall_confidence_score: higher means stronger usable cognition coherence
- caution_score: higher means greater caution required
"""


def _build_user_prompt(contexts: list[dict[str, object]]) -> str:
    payload = [
        {
            "invalidation_reasoning_id": context["invalidation_reasoning_id"],
            "resolution_analysis_id": context["resolution_analysis_id"],
            "candidate_id": context["candidate_id"],
            "interpretation_id": context["interpretation_id"],
            "market_id": context["market_id"],
            "market_question": context["market_question"],
            "event_summary_snapshot": context["event_summary_snapshot"],
            "raw_context": context["raw_context"],
        }
        for context in contexts
    ]
    return (
        "Summarize these cognition-stack contexts into structured market narrations.\n\n"
        f"Contexts:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return a JSON object with this exact shape:\n"
        "{\n"
        '  "summaries": [\n'
        "    {\n"
        '      "narration_summary": "one concise structured summary",\n'
        '      "concise_narration_text": "short human-usable narration",\n'
        '      "cognition_conclusion_class": "WATCHFUL",\n'
        '      "overall_confidence_score": 0.0,\n'
        '      "caution_score": 0.0,\n'
        '      "usability_class": "NEEDS_CONFIRMATION",\n'
        '      "recommended_operator_focus": "MONITOR",\n'
        '      "evidence": {\n'
        '        "event_takeaway": "brief event takeaway",\n'
        '        "link_basis": "brief link basis",\n'
        '        "resolution_takeaway": "brief resolution takeaway",\n'
        '        "invalidation_takeaway": "brief invalidation takeaway",\n'
        '        "open_questions": ["..."]\n'
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
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 3E cognition summary narration")
    parser.add_argument("--invalidation-reasoning-ids", nargs="+", required=True, help="summarize specific invalidation reasoning IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = CognitionSummaryService()
    result = service.summarize_reasonings(
        args.invalidation_reasoning_ids,
        source_type="manual_batch",
        source_ref=args.source_ref,
    )

    if result is None:
        print("Cognition summary persistence is unavailable.")
        return 1

    print(
        f"cognition_summary_run_id={result.cognition_summary_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
