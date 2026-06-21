from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.external_event_enrichment import ExternalEventEnrichmentContract
from app.domain.contracts.external_event_enrichment_run import (
    ExternalEventEnrichmentRunCloseContract,
    ExternalEventEnrichmentRunOpenContract,
)
from app.repositories.external_event_enrichment_runs_repository import (
    ExternalEventEnrichmentRunsRepository,
)
from app.repositories.external_event_enrichments_repository import ExternalEventEnrichmentsRepository
from app.repositories.external_events_normalized_repository import ExternalEventsNormalizedRepository
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.recorders.external_event_enrichment_recorder import ExternalEventEnrichmentRecorder
from app.services.recorders.external_event_enrichment_run_recorder import (
    ExternalEventEnrichmentRunRecorder,
)

logger = logging.getLogger(__name__)

ENRICHMENT_VERSION = "phase4b-external-intelligence-enrichment-v1"
TOPIC_CLASSES = {"POLITICS", "SPORTS", "ECONOMICS", "CRYPTO", "LEGAL", "GENERAL_NEWS", "OTHER"}
CONTRADICTION_HINT_CLASSES = {"NONE", "LOW", "POSSIBLE", "STRONG"}
NOVELTY_HINT_CLASSES = {"NEW", "RECENT_DUPLICATE", "STALE", "UNCLEAR"}
USABILITY_HINT_CLASSES = {"HIGH_UTILITY", "REVIEW", "LOW_SIGNAL", "IGNORE"}

SPORTS_KEYWORDS = {"goal", "striker", "match", "kickoff", "injury", "lineup", "coach", "team", "vs"}
POLITICS_KEYWORDS = {"election", "senate", "minister", "parliament", "policy", "vote", "president"}
ECONOMICS_KEYWORDS = {"inflation", "gdp", "jobs", "unemployment", "rate", "fed", "economy"}
CRYPTO_KEYWORDS = {"bitcoin", "ethereum", "crypto", "token", "blockchain", "etf"}
LEGAL_KEYWORDS = {"court", "judge", "lawsuit", "ruling", "legal", "appeal", "indicted"}
CONTRADICTION_KEYWORDS = {"denied", "refuted", "reversed", "canceled", "cancelled", "contradicts", "false"}
STRONG_CONTRADICTION_KEYWORDS = {"withdraws", "withdrawn", "suspended", "ruled out", "out for season", "terminated"}
PERSON_STOPWORDS = {"Will", "The", "A", "An", "For", "And", "But", "With", "Tonight", "Today"}
ORG_SUFFIXES = {"FC", "CF", "Inc", "Ltd", "LLC", "Corp", "AI", "ETF", "DAO"}
LOCATION_TOKENS = {"Paris", "Marseille", "Israel", "Jerusalem", "London", "Washington", "Gaza", "Europe"}


@dataclass(slots=True)
class ExternalEventEnrichmentRunResult:
    external_event_enrichment_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class ExternalEventEnrichmentService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        enrichment_version: str = ENRICHMENT_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._enrichment_version = enrichment_version
        self._runs = ExternalEventEnrichmentRunsRepository()
        self._enrichments = ExternalEventEnrichmentsRepository()
        self._normalized_events = ExternalEventsNormalizedRepository()
        self._sources = IntelligenceSourcesRepository()
        self._run_recorder = ExternalEventEnrichmentRunRecorder()
        self._enrichment_recorder = ExternalEventEnrichmentRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def enrich_ingestion_run(
        self,
        intelligence_ingestion_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> ExternalEventEnrichmentRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            events = self._normalized_events.list_by_ingestion_run_id(conn, intelligence_ingestion_run_id)
        event_ids = [str(row["id"]) for row in events]
        return self.enrich_external_events(
            event_ids,
            source_type="ingestion_run",
            source_ref=source_ref or intelligence_ingestion_run_id,
            intelligence_ingestion_run_id=intelligence_ingestion_run_id,
        )

    def enrich_external_events(
        self,
        external_event_ids: list[str],
        *,
        source_type: str = "external_event_batch",
        source_ref: str | None = None,
        intelligence_ingestion_run_id: str | None = None,
    ) -> ExternalEventEnrichmentRunResult | None:
        if not self.enabled:
            return None
        if not external_event_ids:
            raise ValueError("at least one external_event_id is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    ExternalEventEnrichmentRunOpenContract(
                        id=run_id,
                        intelligence_ingestion_run_id=intelligence_ingestion_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        enrichment_version=self._enrichment_version,
                        started_at=started_at,
                        input_count=len(external_event_ids),
                        metadata_json={"source_ref": source_ref},
                    ),
                )

                for external_event_id in external_event_ids:
                    try:
                        context = self._build_context(conn, external_event_id)
                        contract = self._build_success_contract(run_id=run_id, context=context)
                        self._enrichment_recorder.record(conn, contract)
                        success_count += 1
                    except Exception as exc:
                        logger.exception("external_event_enrichment_failed external_event_id=%s", external_event_id)
                        context = self._build_failure_context(conn, external_event_id)
                        self._enrichment_recorder.record(
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
                    ExternalEventEnrichmentRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={"enrichment_version": self._enrichment_version},
                    ),
                )

            return ExternalEventEnrichmentRunResult(
                external_event_enrichment_run_id=run_id,
                status=status,
                input_count=len(external_event_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("external_event_enrichment_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    ExternalEventEnrichmentRunOpenContract(
                        id=run_id,
                        intelligence_ingestion_run_id=intelligence_ingestion_run_id,
                        source_type=source_type,
                        source_ref=source_ref,
                        status="OPEN",
                        enrichment_version=self._enrichment_version,
                        started_at=started_at,
                        input_count=len(external_event_ids),
                        metadata_json={"source_ref": source_ref},
                    ),
                )
                self._run_recorder.close_run(
                    conn,
                    ExternalEventEnrichmentRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=max(1, len(external_event_ids)),
                        metadata_json={"error": str(exc), "enrichment_version": self._enrichment_version},
                    ),
                )
            return ExternalEventEnrichmentRunResult(
                external_event_enrichment_run_id=run_id,
                status="FAILED",
                input_count=len(external_event_ids),
                success_count=success_count,
                failure_count=max(1, len(external_event_ids)),
            )

    def _build_context(self, conn, external_event_id: str) -> dict[str, object]:
        event = self._normalized_events.get_by_id(conn, external_event_id)
        if event is None:
            raise ValueError(f"external_event not found: {external_event_id}")
        source = self._sources.get_by_id(conn, str(event["intelligence_source_id"]))
        if source is None:
            raise ValueError(f"intelligence source not found for external_event: {external_event_id}")
        title = str(event["normalized_title"] or "").strip()
        summary = str(event["normalized_summary"] or "").strip()
        if not title or not summary:
            raise ValueError("normalized event is missing title or summary")

        return {
            "event": dict(event),
            "source": dict(source),
            "title": title,
            "summary": summary,
        }

    def _build_failure_context(self, conn, external_event_id: str) -> dict[str, object]:
        event = self._normalized_events.get_by_id(conn, external_event_id)
        if event is None:
            raise ValueError(f"external_event not found: {external_event_id}")
        return {
            "event": dict(event),
            "source": {"id": event["intelligence_source_id"]},
            "title": str(event["normalized_title"] or ""),
            "summary": str(event["normalized_summary"] or ""),
        }

    def _build_success_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
    ) -> ExternalEventEnrichmentContract:
        event = context["event"]
        source = context["source"]
        title = context["title"]
        summary = context["summary"]
        combined_text = f"{title} {summary}"
        entities = _extract_entities(combined_text)
        topic_class, subtopic_class = _classify_topic(
            source_category=str(event["source_category"]),
            text=combined_text,
        )
        contradiction_hint_class = _classify_contradiction_hint(combined_text)
        novelty_hint_class = _classify_novelty_hint(
            status=str(event["status"]),
            published_at=event["published_at"],
        )
        usability_hint_class = _classify_usability_hint(
            trust_weight=float(event["trust_weight_snapshot"]),
            duplicate_status=str(event["status"]),
            summary=summary,
        )

        explanation = {
            "entity_counts": {
                "people": len(entities["people"]),
                "organizations": len(entities["organizations"]),
                "locations": len(entities["locations"]),
                "topics": len(entities["topics"]),
                "keywords": len(entities["keywords"]),
            },
            "topic_reason": {
                "source_category": str(event["source_category"]),
                "matched_keywords": entities["topics"],
            },
            "contradiction_reason": _contradiction_reason(combined_text),
            "novelty_reason": {
                "duplicate_status": str(event["status"]),
                "published_at": str(event["published_at"]) if event["published_at"] is not None else None,
            },
            "usability_reason": {
                "trust_weight_snapshot": float(event["trust_weight_snapshot"]),
                "summary_length": len(summary),
            },
        }

        return ExternalEventEnrichmentContract(
            id=str(uuid4()),
            external_event_enrichment_run_id=run_id,
            external_event_id=str(event["id"]),
            intelligence_source_id=str(event["intelligence_source_id"]),
            normalized_title_snapshot=title,
            normalized_summary_snapshot=summary,
            entities_json=entities,
            topic_class=topic_class,
            subtopic_class=subtopic_class,
            contradiction_hint_class=contradiction_hint_class,
            novelty_hint_class=novelty_hint_class,
            usability_hint_class=usability_hint_class,
            trust_weight_snapshot=_normalize_score(float(event["trust_weight_snapshot"])),
            enrichment_version=self._enrichment_version,
            explanation_json=explanation,
            status="SUCCESS",
            error_text=None,
        )

    def _build_failure_contract(
        self,
        *,
        run_id: str,
        context: dict[str, object],
        error_text: str,
    ) -> ExternalEventEnrichmentContract:
        event = context["event"]
        return ExternalEventEnrichmentContract(
            id=str(uuid4()),
            external_event_enrichment_run_id=run_id,
            external_event_id=str(event["id"]),
            intelligence_source_id=str(context["source"]["id"]),
            normalized_title_snapshot=str(context["title"]),
            normalized_summary_snapshot=str(context["summary"]),
            entities_json={},
            topic_class=None,
            subtopic_class=None,
            contradiction_hint_class=None,
            novelty_hint_class=None,
            usability_hint_class=None,
            trust_weight_snapshot=_normalize_score(float(event["trust_weight_snapshot"])),
            enrichment_version=self._enrichment_version,
            explanation_json={"error": error_text},
            status="ENRICHMENT_ERROR",
            error_text=error_text,
        )


def _extract_entities(text: str) -> dict[str, object]:
    tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z'-]+", text)]
    people: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []
    dates: list[str] = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|today|tonight|tomorrow|yesterday)\b", text, re.IGNORECASE)
    keywords = _top_keywords(tokens)
    topics = [keyword.upper() for keyword in keywords if keyword.lower() in SPORTS_KEYWORDS | POLITICS_KEYWORDS | ECONOMICS_KEYWORDS | CRYPTO_KEYWORDS | LEGAL_KEYWORDS]

    for token in tokens:
        if token in LOCATION_TOKENS and token not in locations:
            locations.append(token)
        elif token.isupper() and len(token) >= 2 and token not in organizations:
            organizations.append(token)
        elif token in ORG_SUFFIXES and token not in organizations:
            organizations.append(token)
        elif token[0].isupper() and token not in PERSON_STOPWORDS and token not in people and token not in locations:
            people.append(token)

    return {
        "people": people[:10],
        "organizations": organizations[:10],
        "locations": locations[:10],
        "dates": dates[:10],
        "topics": topics[:10],
        "keywords": keywords[:12],
    }


def _top_keywords(tokens: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for token in tokens:
        lowered = token.lower()
        if len(lowered) < 4:
            continue
        counts[lowered] = counts.get(lowered, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:12]]


def _classify_topic(*, source_category: str, text: str) -> tuple[str, str | None]:
    lowered_category = source_category.lower()
    lowered_text = text.lower()
    if "sports" in lowered_category or _contains_any(lowered_text, SPORTS_KEYWORDS):
        return "SPORTS", _sports_subtopic(lowered_text)
    if "polit" in lowered_category or _contains_any(lowered_text, POLITICS_KEYWORDS):
        return "POLITICS", None
    if "econom" in lowered_category or _contains_any(lowered_text, ECONOMICS_KEYWORDS):
        return "ECONOMICS", None
    if "crypto" in lowered_category or _contains_any(lowered_text, CRYPTO_KEYWORDS):
        return "CRYPTO", None
    if "legal" in lowered_category or _contains_any(lowered_text, LEGAL_KEYWORDS):
        return "LEGAL", None
    if "news" in lowered_category:
        return "GENERAL_NEWS", None
    return "OTHER", None


def _sports_subtopic(text: str) -> str | None:
    if any(word in text for word in ("injury", "ruled out", "lineup")):
        return "TEAM_NEWS"
    if any(word in text for word in ("goal", "score", "beat", "wins", "match")):
        return "MATCH_RESULT"
    return "SPORTS_UPDATE"


def _classify_contradiction_hint(text: str) -> str:
    lowered = text.lower()
    if _contains_any(lowered, STRONG_CONTRADICTION_KEYWORDS):
        return "STRONG"
    if _contains_any(lowered, CONTRADICTION_KEYWORDS):
        return "POSSIBLE"
    if any(word in lowered for word in ("uncertain", "reportedly", "questionable", "doubt")):
        return "LOW"
    return "NONE"


def _contradiction_reason(text: str) -> dict[str, object]:
    lowered = text.lower()
    strong = [word for word in sorted(STRONG_CONTRADICTION_KEYWORDS) if word in lowered]
    possible = [word for word in sorted(CONTRADICTION_KEYWORDS) if word in lowered]
    return {
        "strong_matches": strong,
        "possible_matches": possible,
    }


def _classify_novelty_hint(*, status: str, published_at: Any) -> str:
    if status == "DUPLICATE":
        return "RECENT_DUPLICATE"
    if published_at is None:
        return "UNCLEAR"
    published_dt = published_at if isinstance(published_at, datetime) else None
    if published_dt is None:
        return "UNCLEAR"
    return "NEW"


def _classify_usability_hint(*, trust_weight: float, duplicate_status: str, summary: str) -> str:
    if duplicate_status == "DUPLICATE":
        return "LOW_SIGNAL"
    if len(summary.strip()) < 25:
        return "IGNORE"
    if trust_weight >= 0.75:
        return "HIGH_UTILITY"
    if trust_weight >= 0.45:
        return "REVIEW"
    return "LOW_SIGNAL"


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_score(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 4B external event enrichment")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ingestion-run-id", help="enrich all normalized events for this ingestion run")
    group.add_argument("--external-event-ids", nargs="+", help="enrich specific normalized external event IDs")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = ExternalEventEnrichmentService()
    if args.ingestion_run_id:
        result = service.enrich_ingestion_run(args.ingestion_run_id, source_ref=args.source_ref)
    else:
        result = service.enrich_external_events(
            args.external_event_ids,
            source_type="manual_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("External event enrichment persistence is unavailable.")
        return 1

    print(
        f"external_event_enrichment_run_id={result.external_event_enrichment_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
