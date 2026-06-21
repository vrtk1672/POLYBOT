from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.cognition_handoff_candidate import CognitionHandoffCandidateContract
from app.domain.contracts.cognition_handoff_run import (
    CognitionHandoffRunCloseContract,
    CognitionHandoffRunOpenContract,
)
from app.repositories.cognition_handoff_candidates_repository import CognitionHandoffCandidatesRepository
from app.repositories.cognition_handoff_runs_repository import CognitionHandoffRunsRepository
from app.repositories.external_event_enrichment_runs_repository import (
    ExternalEventEnrichmentRunsRepository,
)
from app.repositories.external_event_enrichments_repository import ExternalEventEnrichmentsRepository
from app.services.recorders.cognition_handoff_candidate_recorder import (
    CognitionHandoffCandidateRecorder,
)
from app.services.recorders.cognition_handoff_run_recorder import CognitionHandoffRunRecorder

logger = logging.getLogger(__name__)

HANDOFF_VERSION = "phase4c-external-to-cognition-handoff-v1"
DECISION_CLASSES = {
    "SEND_TO_INTERPRETER",
    "HOLD_FOR_REVIEW",
    "SKIP_LOW_SIGNAL",
    "SKIP_DUPLICATE",
    "SKIP_STALE",
}
PRIORITY_CLASSES = {"HIGH", "NORMAL", "LOW"}


@dataclass(slots=True)
class CognitionHandoffRunResult:
    cognition_handoff_run_id: str
    status: str
    input_count: int
    sent_count: int
    held_count: int
    skipped_count: int
    failure_count: int


class ExternalToCognitionHandoffService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        handoff_version: str = HANDOFF_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._handoff_version = handoff_version
        self._enrichment_runs = ExternalEventEnrichmentRunsRepository()
        self._enrichments = ExternalEventEnrichmentsRepository()
        self._run_recorder = CognitionHandoffRunRecorder()
        self._candidate_recorder = CognitionHandoffCandidateRecorder()
        self._runs = CognitionHandoffRunsRepository()
        self._candidates = CognitionHandoffCandidatesRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def evaluate_enrichment_run(
        self,
        external_event_enrichment_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> CognitionHandoffRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._enrichments.list_for_run(conn, external_event_enrichment_run_id)
        enrichment_ids = [str(row["id"]) for row in rows]
        return self.evaluate_enrichments(
            enrichment_ids,
            source_type="external_event_enrichment_run",
            source_ref=_as_optional_str(source_ref) or str(external_event_enrichment_run_id),
            external_event_enrichment_run_id=external_event_enrichment_run_id,
        )

    def evaluate_enrichments(
        self,
        external_event_enrichment_ids: list[str],
        *,
        source_type: str = "external_event_enrichment_batch",
        source_ref: str | None = None,
        external_event_enrichment_run_id: str | None = None,
    ) -> CognitionHandoffRunResult | None:
        if not self.enabled:
            return None
        if not external_event_enrichment_ids:
            raise ValueError("at least one external_event_enrichment_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        sent_count = 0
        held_count = 0
        skipped_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                if external_event_enrichment_run_id is None:
                    first_row = self._enrichments.get_by_id(conn, external_event_enrichment_ids[0])
                    if first_row is not None:
                        external_event_enrichment_run_id = str(first_row["external_event_enrichment_run_id"])

                self._run_recorder.open_run(
                    conn,
                    CognitionHandoffRunOpenContract(
                        id=run_id,
                        external_event_enrichment_run_id=external_event_enrichment_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        handoff_version=self._handoff_version,
                        started_at=started_at,
                        input_count=len(external_event_enrichment_ids),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "interpreter_triggered": False,
                        },
                    ),
                )
                opened_run = True

                for enrichment_id in external_event_enrichment_ids:
                    try:
                        context = self._build_context(conn, enrichment_id)
                        contract = self._build_success_contract(run_id=run_id, context=context)
                        self._candidate_recorder.record(conn, contract)
                        if contract.handoff_decision_class == "SEND_TO_INTERPRETER":
                            sent_count += 1
                        elif contract.handoff_decision_class == "HOLD_FOR_REVIEW":
                            held_count += 1
                        else:
                            skipped_count += 1
                    except Exception as exc:
                        logger.exception("cognition_handoff_failed enrichment_id=%s", enrichment_id)
                        context = self._build_failure_context(conn, enrichment_id)
                        self._candidate_recorder.record(
                            conn,
                            self._build_failure_contract(
                                run_id=run_id,
                                context=context,
                                error_text=str(exc),
                            ),
                        )
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    CognitionHandoffRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        sent_count=sent_count,
                        held_count=held_count,
                        skipped_count=skipped_count,
                        failure_count=failure_count,
                        metadata_json={
                            "handoff_version": self._handoff_version,
                            "interpreter_triggered": False,
                            "source_ref": _as_optional_str(source_ref),
                        },
                    ),
                )

            return CognitionHandoffRunResult(
                cognition_handoff_run_id=run_id,
                status=status,
                input_count=len(external_event_enrichment_ids),
                sent_count=sent_count,
                held_count=held_count,
                skipped_count=skipped_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("cognition_handoff_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        CognitionHandoffRunOpenContract(
                            id=run_id,
                            external_event_enrichment_run_id=external_event_enrichment_run_id,
                            source_type=source_type,
                            source_ref=source_ref,
                            status="OPEN",
                            handoff_version=self._handoff_version,
                            started_at=started_at,
                            input_count=len(external_event_enrichment_ids),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    CognitionHandoffRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        sent_count=sent_count,
                        held_count=held_count,
                        skipped_count=skipped_count,
                        failure_count=max(1, len(external_event_enrichment_ids)),
                        metadata_json={"error": str(exc), "handoff_version": self._handoff_version},
                    ),
                )
            return CognitionHandoffRunResult(
                cognition_handoff_run_id=run_id,
                status="FAILED",
                input_count=len(external_event_enrichment_ids),
                sent_count=sent_count,
                held_count=held_count,
                skipped_count=skipped_count,
                failure_count=max(1, len(external_event_enrichment_ids)),
            )

    def _build_context(self, conn, external_event_enrichment_id: str) -> dict[str, object]:
        enrichment = self._enrichments.get_by_id(conn, external_event_enrichment_id)
        if enrichment is None:
            raise ValueError(f"external_event_enrichment not found: {external_event_enrichment_id}")
        if str(enrichment["status"]) != "SUCCESS":
            raise ValueError("external event enrichment is not usable for handoff")
        return {"enrichment": dict(enrichment)}

    def _build_failure_context(self, conn, external_event_enrichment_id: str) -> dict[str, object]:
        enrichment = self._enrichments.get_by_id(conn, external_event_enrichment_id)
        if enrichment is None:
            raise ValueError(f"external_event_enrichment not found: {external_event_enrichment_id}")
        return {"enrichment": dict(enrichment)}

    def _build_success_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
    ) -> CognitionHandoffCandidateContract:
        enrichment = context["enrichment"]
        decision = _decide_handoff(
            topic_class=_as_optional_str(enrichment["topic_class"]),
            usability_hint_class=_as_optional_str(enrichment["usability_hint_class"]),
            novelty_hint_class=_as_optional_str(enrichment["novelty_hint_class"]),
            contradiction_hint_class=_as_optional_str(enrichment["contradiction_hint_class"]),
            trust_weight_snapshot=float(enrichment["trust_weight_snapshot"]),
        )
        return CognitionHandoffCandidateContract(
            id=str(uuid4()),
            cognition_handoff_run_id=run_id,
            external_event_id=str(enrichment["external_event_id"]),
            external_event_enrichment_id=str(enrichment["id"]),
            intelligence_source_id=str(enrichment["intelligence_source_id"]),
            handoff_decision_class=decision["decision_class"],
            handoff_priority_class=decision["priority_class"],
            handoff_reason_code=decision["reason_code"],
            handoff_reason_text=decision["reason_text"],
            topic_class=_as_optional_str(enrichment["topic_class"]),
            usability_hint_class=_as_optional_str(enrichment["usability_hint_class"]),
            novelty_hint_class=_as_optional_str(enrichment["novelty_hint_class"]),
            contradiction_hint_class=_as_optional_str(enrichment["contradiction_hint_class"]),
            trust_weight_snapshot=_normalize_score(float(enrichment["trust_weight_snapshot"])),
            handoff_payload_json={
                "normalized_title_snapshot": enrichment["normalized_title_snapshot"],
                "normalized_summary_snapshot": enrichment["normalized_summary_snapshot"],
                "entities_json": enrichment["entities_json"],
                "explanation_json": enrichment["explanation_json"],
                "interpreter_triggered": False,
            },
            linked_interpretation_run_id=None,
            linked_interpretation_id=None,
            status="SUCCESS",
            error_text=None,
            handoff_version=self._handoff_version,
        )

    def _build_failure_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        error_text: str,
    ) -> CognitionHandoffCandidateContract:
        enrichment = context["enrichment"]
        return CognitionHandoffCandidateContract(
            id=str(uuid4()),
            cognition_handoff_run_id=run_id,
            external_event_id=str(enrichment["external_event_id"]),
            external_event_enrichment_id=str(enrichment["id"]),
            intelligence_source_id=str(enrichment["intelligence_source_id"]),
            handoff_decision_class=None,
            handoff_priority_class=None,
            handoff_reason_code=None,
            handoff_reason_text=None,
            topic_class=_as_optional_str(enrichment["topic_class"]),
            usability_hint_class=_as_optional_str(enrichment["usability_hint_class"]),
            novelty_hint_class=_as_optional_str(enrichment["novelty_hint_class"]),
            contradiction_hint_class=_as_optional_str(enrichment["contradiction_hint_class"]),
            trust_weight_snapshot=_normalize_score(float(enrichment["trust_weight_snapshot"])),
            handoff_payload_json={"error": error_text},
            linked_interpretation_run_id=None,
            linked_interpretation_id=None,
            status="HANDOFF_ERROR",
            error_text=error_text,
            handoff_version=self._handoff_version,
        )


def _decide_handoff(
    *,
    topic_class: str | None,
    usability_hint_class: str | None,
    novelty_hint_class: str | None,
    contradiction_hint_class: str | None,
    trust_weight_snapshot: float,
) -> dict[str, str]:
    topic = topic_class or "OTHER"
    usability = usability_hint_class or "LOW_SIGNAL"
    novelty = novelty_hint_class or "UNCLEAR"
    contradiction = contradiction_hint_class or "NONE"

    if novelty == "RECENT_DUPLICATE":
        return {
            "decision_class": "SKIP_DUPLICATE",
            "priority_class": "LOW",
            "reason_code": "duplicate_recent",
            "reason_text": "Recent duplicate enrichment does not justify another cognition intake.",
        }
    if novelty == "STALE":
        return {
            "decision_class": "SKIP_STALE",
            "priority_class": "LOW",
            "reason_code": "stale_event",
            "reason_text": "Event is stale relative to the handoff window and is skipped for cognition intake.",
        }
    if usability in {"LOW_SIGNAL", "IGNORE"}:
        return {
            "decision_class": "SKIP_LOW_SIGNAL",
            "priority_class": "LOW",
            "reason_code": "low_signal",
            "reason_text": "Event utility is too weak for interpreter intake.",
        }
    if usability == "HIGH_UTILITY" and novelty in {"NEW", "UNCLEAR"} and trust_weight_snapshot >= 0.60:
        priority = "HIGH" if contradiction in {"POSSIBLE", "STRONG"} or topic in {"POLITICS", "ECONOMICS", "LEGAL", "CRYPTO"} else "NORMAL"
        return {
            "decision_class": "SEND_TO_INTERPRETER",
            "priority_class": priority,
            "reason_code": "high_utility_recent",
            "reason_text": "High-utility enriched event is recent enough and strong enough to send into the cognition stack.",
        }
    if usability == "REVIEW" and novelty != "STALE" and trust_weight_snapshot >= 0.45:
        return {
            "decision_class": "HOLD_FOR_REVIEW",
            "priority_class": "NORMAL",
            "reason_code": "review_required",
            "reason_text": "Event may be useful but needs operator review before cognition intake.",
        }
    return {
        "decision_class": "SKIP_LOW_SIGNAL",
        "priority_class": "LOW",
        "reason_code": "default_low_signal",
        "reason_text": "Event does not meet the deterministic handoff thresholds.",
    }


def _normalize_score(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 5)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 4C external-to-cognition handoff")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--external-event-enrichment-run-id", help="evaluate all enrichments from this enrichment run")
    group.add_argument("--external-event-enrichment-ids", nargs="+", help="evaluate specific enrichment IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = ExternalToCognitionHandoffService()
    if args.external_event_enrichment_run_id:
        result = service.evaluate_enrichment_run(args.external_event_enrichment_run_id, source_ref=args.source_ref)
    else:
        result = service.evaluate_enrichments(
            args.external_event_enrichment_ids,
            source_type="manual_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Cognition handoff persistence is unavailable.")
        return 1

    print(
        f"cognition_handoff_run_id={result.cognition_handoff_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"sent={result.sent_count} "
        f"held={result.held_count} "
        f"skipped={result.skipped_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
