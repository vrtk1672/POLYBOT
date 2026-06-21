from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.market_link_candidate import MarketLinkCandidateContract
from app.domain.contracts.market_link_run import MarketLinkRunCloseContract, MarketLinkRunOpenContract
from app.repositories.event_interpretation_runs_repository import EventInterpretationRunsRepository
from app.repositories.event_interpretations_repository import EventInterpretationsRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.services.recorders.market_link_candidate_recorder import MarketLinkCandidateRecorder
from app.services.recorders.market_link_run_recorder import MarketLinkRunRecorder

logger = logging.getLogger(__name__)

LINKER_VERSION = "phase3b-market-linker-v1"

CANDIDATE_SOURCES = frozenset(
    {"INTERPRETER_MARKET_ID", "TITLE_MATCH", "SLUG_MATCH", "KEYWORD_MATCH", "MANUAL_REF"}
)
LINK_STATUSES = frozenset({"CANDIDATE", "STRONG_CANDIDATE", "NEEDS_REVIEW", "REJECTED"})
USABILITY_CLASSES = frozenset({"USABLE_NOW", "NEEDS_CONFIRMATION", "TOO_AMBIGUOUS", "IRRELEVANT"})

_USABILITY_FROM_ACTION: dict[str, str] = {
    "USABLE_NOW": "USABLE_NOW",
    "NEEDS_MORE_CONFIRMATION": "NEEDS_CONFIRMATION",
    "TOO_AMBIGUOUS": "TOO_AMBIGUOUS",
    "IRRELEVANT": "IRRELEVANT",
}


@dataclass(slots=True)
class MarketLinkCandidateRunResult:
    market_link_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int
    candidate_count: int


class MarketLinkCandidateService:
    """Phase 3B deterministic market-link candidate layer."""

    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._run_recorder = MarketLinkRunRecorder()
        self._candidate_recorder = MarketLinkCandidateRecorder()
        self._interpretations_repo = EventInterpretationsRepository()
        self._interpretation_runs_repo = EventInterpretationRunsRepository()
        self._market_snapshots_repo = MarketSnapshotsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def link_interpretation_run(
        self,
        interpretation_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> MarketLinkCandidateRunResult | None:
        if not self.enabled:
            return None

        with self._factory.connect() as conn:
            rows = self._interpretations_repo.list_for_run(conn, interpretation_run_id)

        success_rows = [r for r in rows if r["status"] == "SUCCESS"]
        interpretation_ids = [str(r["id"]) for r in success_rows]
        return self.link_interpretations(
            interpretation_ids,
            source_type="interpretation_run",
            source_ref=source_ref or interpretation_run_id,
            interpretation_run_id=interpretation_run_id,
        )

    def link_interpretations(
        self,
        interpretation_ids: list[str],
        *,
        source_type: str = "interpretation_batch",
        source_ref: str | None = None,
        interpretation_run_id: str | None = None,
    ) -> MarketLinkCandidateRunResult | None:
        if not self.enabled:
            return None
        if not interpretation_ids:
            raise ValueError("at least one interpretation_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0
        candidate_count = 0

        try:
            with self._factory.connect() as conn, conn.transaction():
                market_catalog = self._market_snapshots_repo.list_latest_catalog(conn)
                self._run_recorder.open_run(
                    conn,
                    MarketLinkRunOpenContract(
                        id=run_id,
                        interpretation_run_id=interpretation_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        linker_version=LINKER_VERSION,
                        started_at=started_at,
                        input_count=len(interpretation_ids),
                        metadata_json={
                            "source_ref": source_ref,
                            "market_catalog_count": len(market_catalog),
                        },
                    ),
                )

                for interpretation_id in interpretation_ids:
                    try:
                        interpretation = self._interpretations_repo.get_by_id(conn, interpretation_id)
                        if interpretation is None:
                            logger.warning(
                                "market_linker: interpretation not found id=%s",
                                interpretation_id,
                            )
                            failure_count += 1
                            continue

                        candidates = _derive_candidates(
                            run_id=run_id,
                            interpretation=interpretation,
                            market_catalog=market_catalog,
                            linker_version=LINKER_VERSION,
                        )
                        for candidate in candidates:
                            self._candidate_recorder.record(conn, candidate)
                            candidate_count += 1
                        success_count += 1
                    except Exception:
                        logger.exception(
                            "market_linker: failed to link interpretation_id=%s",
                            interpretation_id,
                        )
                        failure_count += 1

                final_status = (
                    "COMPLETED"
                    if failure_count == 0
                    else ("FAILED" if success_count == 0 else "COMPLETED_WITH_ERRORS")
                )
                self._run_recorder.close_run(
                    conn,
                    MarketLinkRunCloseContract(
                        id=run_id,
                        status=final_status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "candidate_count": candidate_count,
                            "linker_version": LINKER_VERSION,
                            "market_catalog_count": len(market_catalog),
                        },
                    ),
                )

            return MarketLinkCandidateRunResult(
                market_link_run_id=run_id,
                status=final_status,
                input_count=len(interpretation_ids),
                success_count=success_count,
                failure_count=failure_count,
                candidate_count=candidate_count,
            )

        except Exception as exc:
            logger.exception("market_linker: run failed run_id=%s", run_id)
            try:
                with self._factory.connect() as conn, conn.transaction():
                    self._run_recorder.open_run(
                        conn,
                        MarketLinkRunOpenContract(
                            id=run_id,
                            interpretation_run_id=interpretation_run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            linker_version=LINKER_VERSION,
                            started_at=started_at,
                            input_count=len(interpretation_ids),
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                    self._run_recorder.close_run(
                        conn,
                        MarketLinkRunCloseContract(
                            id=run_id,
                            status="FAILED",
                            ended_at=datetime.now(UTC),
                            success_count=0,
                            failure_count=len(interpretation_ids),
                            metadata_json={"error": str(exc), "linker_version": LINKER_VERSION},
                        ),
                    )
            except Exception:
                logger.exception("market_linker: failed to record failed run run_id=%s", run_id)

            return MarketLinkCandidateRunResult(
                market_link_run_id=run_id,
                status="FAILED",
                input_count=len(interpretation_ids),
                success_count=0,
                failure_count=len(interpretation_ids),
                candidate_count=0,
            )


def _derive_candidates(
    *,
    run_id: str,
    interpretation: dict,
    market_catalog: list[dict[str, object]],
    linker_version: str,
) -> list[MarketLinkCandidateContract]:
    raw_candidates: list[dict] = list(interpretation.get("affected_market_candidates_json") or [])
    if not raw_candidates:
        return []

    interpretation_id = str(interpretation["id"])
    directness_class = interpretation.get("directness_class")
    directness_score = _to_float(interpretation.get("directness_score"))
    contradiction_risk = _to_float(interpretation.get("contradiction_risk"))
    ambiguity_score = _to_float(interpretation.get("ambiguity_score"))
    recommended_action_class = interpretation.get("recommended_action_class")
    affected_outcomes: list = list(interpretation.get("affected_outcomes_json") or [])
    prompt_version = interpretation.get("prompt_version")
    model_name = interpretation.get("model_name")

    affected_outcome = _extract_affected_outcome(affected_outcomes)
    usability_class = _classify_usability(recommended_action_class, ambiguity_score, contradiction_risk)

    results: list[MarketLinkCandidateContract] = []
    for raw in raw_candidates:
        market_id_hint = raw.get("market_id_hint") or None
        question_hint = raw.get("question_hint") or None
        confidence = float(raw.get("confidence") or 0.0)
        rationale = str(raw.get("rationale") or "")

        match = _match_market_by_hint(
            market_catalog=market_catalog,
            market_id_hint=market_id_hint,
            question_hint=question_hint,
        )
        if match is None:
            logger.debug(
                "market_linker: no persisted market match interpretation_id=%s market_id_hint=%s question_hint=%s",
                interpretation_id,
                market_id_hint,
                question_hint,
            )
            continue

        relevance_score = _score_relevance(
            base_confidence=confidence,
            candidate_source=match["candidate_source"],
            directness_class=directness_class,
            contradiction_risk=contradiction_risk,
        )
        link_status = _classify_link_status(relevance_score, directness_class)

        explanation = {
            "candidate_source": match["candidate_source"],
            "interpreter_confidence": confidence,
            "interpreter_rationale": rationale,
            "question_hint": question_hint,
            "market_id_hint": market_id_hint,
            "matched_market_id": match["market_id"],
            "matched_market_question": match["question"],
            "matched_market_slug": match["slug"],
            "match_detail": match["match_detail"],
            "directness_class": directness_class,
            "contradiction_risk": contradiction_risk,
            "usability_derivation": {
                "recommended_action_class": recommended_action_class,
                "ambiguity_score": ambiguity_score,
                "override_applied": ambiguity_score is not None and ambiguity_score > 0.70,
            },
        }

        results.append(
            MarketLinkCandidateContract(
                id=str(uuid4()),
                market_link_run_id=run_id,
                interpretation_id=interpretation_id,
                market_id=str(match["market_id"]),
                candidate_source=str(match["candidate_source"]),
                link_status=link_status,
                relevance_score=relevance_score,
                directness_class=directness_class,
                directness_score=directness_score,
                contradiction_risk=contradiction_risk,
                affected_outcome=affected_outcome,
                usability_class=usability_class,
                explanation_json=explanation,
                linker_version=linker_version,
                prompt_version=prompt_version,
                model_name=model_name,
            )
        )

    return results


def _match_market_by_hint(
    *,
    market_catalog: list[dict[str, object]],
    market_id_hint: str | None,
    question_hint: str | None,
) -> dict[str, object] | None:
    if market_id_hint:
        for market in market_catalog:
            if str(market["market_id"]) == str(market_id_hint):
                return {
                    "market_id": str(market["market_id"]),
                    "question": str(market.get("question") or ""),
                    "slug": str(market.get("slug") or ""),
                    "candidate_source": "INTERPRETER_MARKET_ID",
                    "match_detail": "Exact market_id hint matched persisted market catalog.",
                }

    if not question_hint:
        return None

    normalized_hint = _normalize_text(question_hint)
    slug_hint = _slugify(question_hint)
    tokens = _tokenize(question_hint)

    for market in market_catalog:
        slug = str(market.get("slug") or "")
        if slug and slug == slug_hint:
            return {
                "market_id": str(market["market_id"]),
                "question": str(market.get("question") or ""),
                "slug": slug,
                "candidate_source": "SLUG_MATCH",
                "match_detail": "Slugified question hint matched persisted market slug.",
            }

    for market in market_catalog:
        normalized_question = _normalize_text(str(market.get("question") or ""))
        if normalized_hint and (
            normalized_hint in normalized_question or normalized_question in normalized_hint
        ):
            return {
                "market_id": str(market["market_id"]),
                "question": str(market.get("question") or ""),
                "slug": str(market.get("slug") or ""),
                "candidate_source": "TITLE_MATCH",
                "match_detail": "Normalized question hint matched persisted market title.",
            }

    best_match: dict[str, object] | None = None
    best_overlap = 0.0
    for market in market_catalog:
        market_tokens = _tokenize(str(market.get("question") or ""))
        if not tokens or not market_tokens:
            continue
        overlap = len(tokens & market_tokens) / max(1, len(tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = market
    if best_match is not None and best_overlap >= 0.50:
        return {
            "market_id": str(best_match["market_id"]),
            "question": str(best_match.get("question") or ""),
            "slug": str(best_match.get("slug") or ""),
            "candidate_source": "KEYWORD_MATCH",
            "match_detail": f"Keyword overlap matched persisted market title with overlap={best_overlap:.2f}.",
        }

    return None


def _score_relevance(
    *,
    base_confidence: float,
    candidate_source: str,
    directness_class: str | None,
    contradiction_risk: float | None,
) -> float:
    score = float(base_confidence)
    source_bonus = {
        "INTERPRETER_MARKET_ID": 0.15,
        "SLUG_MATCH": 0.10,
        "TITLE_MATCH": 0.08,
        "KEYWORD_MATCH": 0.05,
        "MANUAL_REF": 0.15,
    }.get(candidate_source, 0.0)
    score += source_bonus
    if directness_class == "DIRECT_SIGNAL":
        score += 0.05
    if contradiction_risk is not None and contradiction_risk > 0.70:
        score -= 0.10
    return round(min(1.0, max(0.0, score)), 5)


def _classify_link_status(relevance_score: float, directness_class: str | None) -> str:
    if relevance_score >= 0.80 and directness_class == "DIRECT_SIGNAL":
        return "STRONG_CANDIDATE"
    if relevance_score >= 0.50:
        return "CANDIDATE"
    if relevance_score >= 0.20:
        return "NEEDS_REVIEW"
    return "REJECTED"


def _classify_usability(
    recommended_action_class: str | None,
    ambiguity_score: float | None,
    contradiction_risk: float | None,
) -> str:
    if ambiguity_score is not None and ambiguity_score > 0.70:
        return "TOO_AMBIGUOUS"
    if recommended_action_class is not None:
        mapped = _USABILITY_FROM_ACTION.get(recommended_action_class.upper())
        if mapped:
            return mapped
    return "NEEDS_CONFIRMATION"


def _extract_affected_outcome(outcomes: list) -> str | None:
    if not outcomes:
        return None
    first = outcomes[0]
    return str(first) if first is not None else None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _tokenize(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split(" ") if token and len(token) > 2}


def _slugify(value: str) -> str:
    normalized = _normalize_text(value)
    return normalized.replace(" ", "-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 3B market link candidate linker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--interpretation-run-id", help="Link all SUCCESS interpretations from this run")
    group.add_argument("--interpretation-ids", nargs="+", help="Link specific interpretation IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = MarketLinkCandidateService()
    if args.interpretation_run_id:
        result = service.link_interpretation_run(args.interpretation_run_id, source_ref=args.source_ref)
    else:
        result = service.link_interpretations(
            args.interpretation_ids,
            source_type="manual_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Market link candidate persistence is unavailable.")
        return 1

    print(
        f"market_link_run_id={result.market_link_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count} "
        f"candidates={result.candidate_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
