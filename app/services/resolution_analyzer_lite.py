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
from app.domain.contracts.resolution_analysis import ResolutionAnalysisContract
from app.domain.contracts.resolution_analysis_run import (
    ResolutionAnalysisRunCloseContract,
    ResolutionAnalysisRunOpenContract,
)
from app.repositories.event_interpretations_repository import EventInterpretationsRepository
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository
from app.repositories.market_link_runs_repository import MarketLinkRunsRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.services.recorders.resolution_analysis_recorder import ResolutionAnalysisRecorder
from app.services.recorders.resolution_analysis_run_recorder import ResolutionAnalysisRunRecorder

logger = logging.getLogger(__name__)

ANALYZER_VERSION = "phase3c-resolution-analyzer-lite-v1"
PROMPT_VERSION = "phase3c-resolution-analyzer-lite-prompt-v1"
DEFAULT_MODEL = "claude-opus-4-6"
DIRECT_FIT_CLASSES = {"DIRECT_FIT", "PLAUSIBLE_BUT_RISKY", "AMBIGUOUS", "POOR_FIT"}
USABLE_NOW_CLASSES = {"USABLE_NOW", "NEEDS_CONFIRMATION", "TOO_AMBIGUOUS", "DO_NOT_USE"}


@dataclass(slots=True)
class ResolutionAnalysisRunResult:
    resolution_analysis_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class ResolutionAnalysisModel(BaseModel):
    resolution_summary: str = Field(min_length=1, max_length=400)
    wording_clarity_score: float = Field(ge=0.0, le=1.0)
    ambiguity_risk_score: float = Field(ge=0.0, le=1.0)
    resolution_mismatch_risk: float = Field(ge=0.0, le=1.0)
    resolution_confidence_score: float = Field(ge=0.0, le=1.0)
    direct_fit_class: str
    usable_now_class: str
    explanation: dict[str, object] = Field(default_factory=dict)


class ResolutionAnalysisResponseModel(BaseModel):
    analyses: list[ResolutionAnalysisModel]


class ResolutionAnalyzerLiteService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        client: anthropic.Anthropic | None = None,
        model_name: str = DEFAULT_MODEL,
        prompt_version: str = PROMPT_VERSION,
        analyzer_version: str = ANALYZER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._client = client
        self._model_name = model_name
        self._prompt_version = prompt_version
        self._analyzer_version = analyzer_version
        self._run_recorder = ResolutionAnalysisRunRecorder()
        self._analysis_recorder = ResolutionAnalysisRecorder()
        self._candidate_repo = MarketLinkCandidatesRepository()
        self._link_run_repo = MarketLinkRunsRepository()
        self._interpretation_repo = EventInterpretationsRepository()
        self._market_snapshots_repo = MarketSnapshotsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def analyze_market_link_run(
        self,
        market_link_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> ResolutionAnalysisRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            candidates = self._candidate_repo.list_for_run(conn, market_link_run_id)
        candidate_ids = [str(row["id"]) for row in candidates]
        return self.analyze_candidates(
            candidate_ids,
            source_type="market_link_run",
            source_ref=source_ref or market_link_run_id,
            market_link_run_id=market_link_run_id,
        )

    def analyze_candidates(
        self,
        candidate_ids: list[str],
        *,
        source_type: str = "candidate_batch",
        source_ref: str | None = None,
        market_link_run_id: str | None = None,
    ) -> ResolutionAnalysisRunResult | None:
        if not self.enabled:
            return None
        if not candidate_ids:
            raise ValueError("at least one market_link_candidate_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0

        try:
            with self._factory.connect() as conn, conn.transaction():
                if market_link_run_id is None:
                    first_candidate = self._candidate_repo.get_by_id(conn, candidate_ids[0])
                    market_link_run_id = (
                        str(first_candidate["market_link_run_id"]) if first_candidate is not None else None
                    )

                self._run_recorder.open_run(
                    conn,
                    ResolutionAnalysisRunOpenContract(
                        id=run_id,
                        market_link_run_id=market_link_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        analyzer_version=self._analyzer_version,
                        prompt_version=self._prompt_version,
                        model_name=self._model_name,
                        started_at=started_at,
                        input_count=len(candidate_ids),
                        metadata_json={"source_ref": source_ref},
                    ),
                )

                contexts = [self._build_context(conn, candidate_id) for candidate_id in candidate_ids]
                response_text = self._invoke_model(contexts)
                parsed = self._parse_response(response_text, expected_count=len(contexts))

                for context, result in zip(contexts, parsed, strict=True):
                    self._analysis_recorder.record(
                        conn,
                        self._build_success_contract(
                            run_id=run_id,
                            context=context,
                            result=result,
                        ),
                    )
                    success_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    ResolutionAnalysisRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"analyzer_version": self._analyzer_version},
                    ),
                )

            return ResolutionAnalysisRunResult(
                resolution_analysis_run_id=run_id,
                status=status,
                input_count=len(candidate_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("resolution_analyzer_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if success_count == 0:
                    self._run_recorder.open_run(
                        conn,
                        ResolutionAnalysisRunOpenContract(
                            id=run_id,
                            market_link_run_id=market_link_run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            analyzer_version=self._analyzer_version,
                            prompt_version=self._prompt_version,
                            model_name=self._model_name,
                            started_at=started_at,
                            input_count=len(candidate_ids),
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                failure_count = len(candidate_ids)
                error_status = (
                    "PARSE_ERROR"
                    if isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError))
                    else "MODEL_ERROR"
                )
                for candidate_id in candidate_ids:
                    context = self._build_context(conn, candidate_id)
                    self._analysis_recorder.record(
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
                    ResolutionAnalysisRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"error": str(exc), "analyzer_version": self._analyzer_version},
                    ),
                )

            return ResolutionAnalysisRunResult(
                resolution_analysis_run_id=run_id,
                status="FAILED",
                input_count=len(candidate_ids),
                success_count=success_count,
                failure_count=failure_count,
            )

    def _build_context(self, conn, candidate_id: str) -> dict[str, object]:
        candidate = self._candidate_repo.get_by_id(conn, candidate_id)
        if candidate is None:
            raise ValueError(f"market_link_candidate not found: {candidate_id}")
        interpretation = self._interpretation_repo.get_by_id(conn, str(candidate["interpretation_id"]))
        if interpretation is None:
            raise ValueError(f"interpretation not found for candidate: {candidate_id}")
        snapshot = self._market_snapshots_repo.get_latest_for_market(conn, str(candidate["market_id"]))
        market_question = (
            str(snapshot["question"])
            if snapshot is not None and snapshot.get("question")
            else str(candidate["explanation_json"].get("matched_market_question") or candidate["market_id"])
        )
        raw_context = {
            "candidate": dict(candidate),
            "interpretation": dict(interpretation),
            "market_snapshot": dict(snapshot) if snapshot is not None else None,
        }
        return {
            "candidate_id": str(candidate["id"]),
            "interpretation_id": str(candidate["interpretation_id"]),
            "market_id": str(candidate["market_id"]),
            "market_question": market_question,
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
                "text": _system_prompt(self._prompt_version, self._analyzer_version),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_user_prompt(contexts)}],
        )
        return _extract_json_text(response)

    def _build_client(self) -> anthropic.Anthropic:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the resolution analyzer")
        return anthropic.Anthropic(api_key=api_key)

    def _parse_response(self, response_text: str, *, expected_count: int) -> list[ResolutionAnalysisModel]:
        payload = json.loads(response_text)
        parsed = ResolutionAnalysisResponseModel.model_validate(payload)
        if len(parsed.analyses) != expected_count:
            raise ValueError(f"expected {expected_count} analyses but received {len(parsed.analyses)}")

        normalized: list[ResolutionAnalysisModel] = []
        for item in parsed.analyses:
            direct_fit_class = item.direct_fit_class.upper()
            usable_now_class = item.usable_now_class.upper()
            if direct_fit_class not in DIRECT_FIT_CLASSES:
                raise ValueError(f"unsupported direct_fit_class: {item.direct_fit_class}")
            if usable_now_class not in USABLE_NOW_CLASSES:
                raise ValueError(f"unsupported usable_now_class: {item.usable_now_class}")
            normalized.append(
                item.model_copy(
                    update={
                        "direct_fit_class": direct_fit_class,
                        "usable_now_class": usable_now_class,
                    }
                )
            )
        return normalized

    def _build_success_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        result: ResolutionAnalysisModel,
    ) -> ResolutionAnalysisContract:
        return ResolutionAnalysisContract(
            id=str(uuid4()),
            resolution_analysis_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            raw_context_json=dict(context["raw_context"]),
            resolution_summary=result.resolution_summary,
            wording_clarity_score=_normalize_score(result.wording_clarity_score),
            ambiguity_risk_score=_normalize_score(result.ambiguity_risk_score),
            resolution_mismatch_risk=_normalize_score(result.resolution_mismatch_risk),
            resolution_confidence_score=_normalize_score(result.resolution_confidence_score),
            direct_fit_class=result.direct_fit_class,
            usable_now_class=result.usable_now_class,
            explanation_json=result.explanation,
            status="SUCCESS",
            error_text=None,
            analyzer_version=self._analyzer_version,
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
    ) -> ResolutionAnalysisContract:
        return ResolutionAnalysisContract(
            id=str(uuid4()),
            resolution_analysis_run_id=run_id,
            interpretation_id=str(context["interpretation_id"]),
            market_link_candidate_id=str(context["candidate_id"]),
            market_id=str(context["market_id"]),
            market_question=str(context["market_question"]),
            raw_context_json=dict(context["raw_context"]),
            resolution_summary=None,
            wording_clarity_score=None,
            ambiguity_risk_score=None,
            resolution_mismatch_risk=None,
            resolution_confidence_score=None,
            direct_fit_class=None,
            usable_now_class=None,
            explanation_json={"error": error_text},
            status=status,
            error_text=error_text,
            analyzer_version=self._analyzer_version,
            prompt_version=self._prompt_version,
            model_name=self._model_name,
        )


def _system_prompt(prompt_version: str, analyzer_version: str) -> str:
    return f"""You are POLYBOT's Resolution Analyzer Lite.
Prompt version: {prompt_version}
Analyzer version: {analyzer_version}

Analyze whether a linked event actually fits the market's literal resolution wording.
Return ONLY valid JSON matching the required schema.
Do not suggest executing a trade.
Do not discuss portfolio allocation.

direct_fit_class must be one of:
- DIRECT_FIT
- PLAUSIBLE_BUT_RISKY
- AMBIGUOUS
- POOR_FIT

usable_now_class must be one of:
- USABLE_NOW
- NEEDS_CONFIRMATION
- TOO_AMBIGUOUS
- DO_NOT_USE

All scores are between 0.0 and 1.0.
- wording_clarity_score: higher means cleaner, less dangerous wording
- ambiguity_risk_score: higher means more ambiguity in wording or event interpretation
- resolution_mismatch_risk: higher means the event does not cleanly map to the market wording
- resolution_confidence_score: higher means the analysis is more reliable
"""


def _build_user_prompt(contexts: list[dict[str, object]]) -> str:
    payload = [
        {
            "candidate_id": context["candidate_id"],
            "interpretation_id": context["interpretation_id"],
            "market_id": context["market_id"],
            "market_question": context["market_question"],
            "raw_context": context["raw_context"],
        }
        for context in contexts
    ]
    return (
        "Analyze these interpretation-to-market link candidates for resolution risk.\n\n"
        f"Contexts:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return a JSON object with this exact shape:\n"
        "{\n"
        '  "analyses": [\n'
        "    {\n"
        '      "resolution_summary": "short summary of fit versus wording",\n'
        '      "wording_clarity_score": 0.0,\n'
        '      "ambiguity_risk_score": 0.0,\n'
        '      "resolution_mismatch_risk": 0.0,\n'
        '      "resolution_confidence_score": 0.0,\n'
        '      "direct_fit_class": "DIRECT_FIT",\n'
        '      "usable_now_class": "USABLE_NOW",\n'
        '      "explanation": {\n'
        '        "fit_reason": "brief reason",\n'
        '        "ambiguities": ["..."],\n'
        '        "mismatch_points": ["..."],\n'
        '        "needs_confirmation": ["..."]\n'
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
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 3C resolution analyzer lite")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--market-link-run-id", help="analyze all candidates from this market link run")
    group.add_argument("--market-link-candidate-ids", nargs="+", help="analyze specific candidate IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = ResolutionAnalyzerLiteService()
    if args.market_link_run_id:
        result = service.analyze_market_link_run(args.market_link_run_id, source_ref=args.source_ref)
    else:
        result = service.analyze_candidates(
            args.market_link_candidate_ids,
            source_type="manual_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Resolution analyzer persistence is unavailable.")
        return 1

    print(
        f"resolution_analysis_run_id={result.resolution_analysis_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
