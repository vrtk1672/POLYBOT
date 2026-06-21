from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import anthropic
import httpx

from app.config import Settings, get_settings
from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.intelligence_source import IntelligenceSourceContract
from app.repositories.external_events_normalized_repository import ExternalEventsNormalizedRepository
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.alerts import AlertEventService
from app.services.external_event_enrichment import ExternalEventEnrichmentService
from app.services.external_intelligence import ExternalIntelligenceFoundationService
from app.services.external_to_cognition_handoff import ExternalToCognitionHandoffService
from app.services.whale_scoring import WhaleScoringService

logger = logging.getLogger(__name__)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class RuntimeIntelligenceRefreshResult:
    news_run_ids: list[str]
    enrichment_run_ids: list[str]
    handoff_run_ids: list[str]
    whale_scoring_run_id: str | None
    ai_digest_alert_id: str | None


class RuntimeIntelligenceService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        db_settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        http_client: httpx.Client | None = None,
        cognition_client: anthropic.Anthropic | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._db_settings = db_settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._db_settings)
        self._foundation = ExternalIntelligenceFoundationService(
            settings=self._db_settings,
            connection_factory=self._factory,
            http_client=http_client,
        )
        self._enrichment = ExternalEventEnrichmentService(
            settings=self._db_settings,
            connection_factory=self._factory,
        )
        self._handoff = ExternalToCognitionHandoffService(
            settings=self._db_settings,
            connection_factory=self._factory,
        )
        self._whale_scoring = WhaleScoringService(
            settings=self._db_settings,
            connection_factory=self._factory,
        )
        self._alerts = AlertEventService(settings=self._settings, connection_factory=self._factory)
        self._sources = IntelligenceSourcesRepository()
        self._normalized = ExternalEventsNormalizedRepository()
        self._cognition_client = cognition_client
        self._last_news_refresh_at: datetime | None = None
        self._last_whale_refresh_at: datetime | None = None
        self._last_ai_refresh_at: datetime | None = None

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def refresh(
        self,
        *,
        cycle_id: str | None,
        scored_markets: list[object],
    ) -> RuntimeIntelligenceRefreshResult | None:
        if not self.enabled:
            return None

        self._ensure_default_sources()
        news_run_ids: list[str] = []
        enrichment_run_ids: list[str] = []
        handoff_run_ids: list[str] = []
        whale_scoring_run_id: str | None = None
        ai_digest_alert_id: str | None = None
        recent_news_rows: list[dict[str, object]] = []

        if self._settings.intelligence_news_enabled and self._due(
            self._last_news_refresh_at,
            interval_seconds=self._settings.intelligence_refresh_interval_seconds,
        ):
            news_run_ids, recent_news_rows = self._refresh_news(cycle_id=cycle_id)
            self._last_news_refresh_at = datetime.now(UTC)
            if recent_news_rows:
                enrichment_run_ids, handoff_run_ids = self._refresh_news_enrichment_and_handoff(
                    cycle_id=cycle_id,
                    recent_news_rows=recent_news_rows,
                )

        if self._due(
            self._last_whale_refresh_at,
            interval_seconds=self._settings.intelligence_whale_refresh_interval_seconds,
        ):
            whale_scoring_run_id = self._refresh_whales(cycle_id=cycle_id)
            self._last_whale_refresh_at = datetime.now(UTC)

        if recent_news_rows and self._settings.intelligence_ai_enabled and self._ai_available() and self._due(
            self._last_ai_refresh_at,
            interval_seconds=self._settings.intelligence_refresh_interval_seconds,
        ):
            ai_digest_alert_id = self._emit_ai_digest(cycle_id=cycle_id, recent_news_rows=recent_news_rows)
            self._last_ai_refresh_at = datetime.now(UTC)

        return RuntimeIntelligenceRefreshResult(
            news_run_ids=news_run_ids,
            enrichment_run_ids=enrichment_run_ids,
            handoff_run_ids=handoff_run_ids,
            whale_scoring_run_id=whale_scoring_run_id,
            ai_digest_alert_id=ai_digest_alert_id,
        )

    def _ensure_default_sources(self) -> None:
        default_sources = [
            IntelligenceSourceContract(
                id=str(uuid4()),
                source_key="ap_top_news",
                source_name="Associated Press Top News",
                source_type="OFFICIAL_SITE",
                base_url="https://apnews.com/hub/ap-top-news",
                category="global_news",
                trust_weight=0.95,
                latency_score=0.75,
                noise_score=0.10,
                relevance_scope="global_macro_politics_markets",
                is_enabled=True,
                metadata_json={
                    "tier": "TIER_1",
                    "runtime_parser": "ap_top_news_hub_v1",
                    "max_items": self._settings.intelligence_news_max_items_per_source,
                    "integration_status": "active",
                },
            ),
            IntelligenceSourceContract(
                id=str(uuid4()),
                source_key="reuters_world",
                source_name="Reuters World",
                source_type="OFFICIAL_SITE",
                base_url="https://www.reuters.com/world/",
                category="global_news",
                trust_weight=0.99,
                latency_score=0.90,
                noise_score=0.05,
                relevance_scope="global_macro_politics_markets",
                is_enabled=False,
                metadata_json={
                    "tier": "TIER_1",
                    "integration_status": "disabled_access_blocked",
                    "reason": "Official public endpoint returned an access/auth block during runtime verification.",
                },
            ),
            IntelligenceSourceContract(
                id=str(uuid4()),
                source_key="bloomberg_markets",
                source_name="Bloomberg Markets",
                source_type="OFFICIAL_SITE",
                base_url="https://www.bloomberg.com/markets",
                category="global_finance",
                trust_weight=0.99,
                latency_score=0.90,
                noise_score=0.05,
                relevance_scope="macro_finance_markets",
                is_enabled=False,
                metadata_json={
                    "tier": "TIER_1",
                    "integration_status": "disabled_access_blocked",
                    "reason": "Official public endpoint returned an access block during runtime verification.",
                },
            ),
            IntelligenceSourceContract(
                id=str(uuid4()),
                source_key="ft_news_feed",
                source_name="Financial Times News Feed",
                source_type="OFFICIAL_SITE",
                base_url="https://www.ft.com/news-feed",
                category="global_finance",
                trust_weight=0.98,
                latency_score=0.85,
                noise_score=0.07,
                relevance_scope="macro_finance_markets",
                is_enabled=False,
                metadata_json={
                    "tier": "TIER_1",
                    "integration_status": "disabled_access_blocked",
                    "reason": "Official public endpoint returned a security block during runtime verification.",
                },
            ),
        ]
        for source in default_sources:
            self._foundation.register_source(source)

    def _refresh_news(self, *, cycle_id: str | None) -> tuple[list[str], list[dict[str, object]]]:
        run_ids: list[str] = []
        recent_rows: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            enabled_sources = self._sources.list_enabled(conn)
        for source in enabled_sources:
            source_type = str(source["source_type"])
            if source_type not in {"RSS", "OFFICIAL_SITE", "NEWS_SITE"}:
                continue
            result = self._foundation.ingest_registered_source(
                source_key=str(source["source_key"]),
                source_ref=cycle_id or "runtime.intelligence",
            )
            if result is None:
                continue
            run_ids.append(result.intelligence_ingestion_run_id)
            with self._factory.connect() as conn:
                rows = self._normalized.list_by_ingestion_run_id(conn, result.intelligence_ingestion_run_id)
            recent_rows.extend(dict(row) for row in rows if str(row["status"]) == "READY")
        return run_ids, recent_rows

    def _refresh_news_enrichment_and_handoff(
        self,
        *,
        cycle_id: str | None,
        recent_news_rows: list[dict[str, object]],
    ) -> tuple[list[str], list[str]]:
        if not recent_news_rows:
            return [], []
        enrichment_run_ids: list[str] = []
        handoff_run_ids: list[str] = []
        event_ids = [str(row["id"]) for row in recent_news_rows]
        enrichment = self._enrichment.enrich_external_events(
            event_ids,
            source_type="runtime_news_refresh",
            source_ref=cycle_id or "runtime.intelligence",
        )
        if enrichment is None:
            return enrichment_run_ids, handoff_run_ids
        enrichment_run_ids.append(enrichment.external_event_enrichment_run_id)
        handoff = self._handoff.evaluate_enrichment_run(
            enrichment.external_event_enrichment_run_id,
            source_ref=cycle_id or "runtime.intelligence",
        )
        if handoff is not None:
            handoff_run_ids.append(handoff.cognition_handoff_run_id)
        return enrichment_run_ids, handoff_run_ids

    def _refresh_whales(self, *, cycle_id: str | None) -> str | None:
        try:
            result = self._whale_scoring.score_recent_markets(
                window_hours=24,
                limit_markets=25,
                source_ref=cycle_id or "runtime.intelligence",
            )
        except Exception as exc:
            logger.info("runtime_whale_refresh_skipped error=%s", exc)
            return None
        if result is None:
            logger.info("runtime_whale_refresh_noop reason=no_recent_market_ids")
            return None
        logger.info(
            "runtime_whale_refresh_complete run_id=%s status=%s input=%s success=%s failure=%s",
            result.whale_scoring_run_id,
            result.status,
            result.input_count,
            result.success_count,
            result.failure_count,
        )
        return None if result is None else result.whale_scoring_run_id

    def _emit_ai_digest(self, *, cycle_id: str | None, recent_news_rows: list[dict[str, object]]) -> str | None:
        contexts = [
            {
                "title": str(row["normalized_title"]),
                "summary": str(row["normalized_summary"]),
                "source_category": str(row["source_category"]),
                "canonical_url": row["canonical_url"],
                "published_at": _iso(row["published_at"]),
                "created_at": _iso(row["created_at"]),
            }
            for row in recent_news_rows[: self._settings.intelligence_ai_max_events]
        ]
        if not contexts:
            return None
        client = self._cognition_client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1200,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{
                "type": "text",
                "text": (
                    "You are POLYBOT's runtime intelligence digest layer. "
                    "Summarize only what materially matters for market awareness. "
                    "Return only a single JSON object and no markdown fences or prose outside JSON. "
                    "Required keys: summary_text, relevance_level, contradiction_risk, operator_takeaway, watch_items."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": json.dumps({"events": contexts}, ensure_ascii=False)}],
        )
        text_blocks = [str(block.text) for block in response.content if hasattr(block, "text") and block.text]
        raw_text = "\n".join(text_blocks).strip()
        payload, fallback_used, fallback_reason = _build_ai_digest_payload(raw_text=raw_text, contexts=contexts)
        logger.info(
            "runtime_ai_digest_result fallback_used=%s reason=%s text_blocks=%s raw_chars=%s",
            fallback_used,
            fallback_reason,
            len(text_blocks),
            len(raw_text),
        )
        alert = self._alerts.emit_alert(
            event_class="AI_INTELLIGENCE_DIGEST",
            severity_class="INFO",
            title="Runtime AI intelligence digest",
            body_text=str(payload.get("summary_text") or "AI digest completed"),
            dedupe_key=_sha256_json({"events": contexts, "summary": payload}),
            source_ref=cycle_id or "runtime.intelligence",
            payload_json={
                "purpose": "runtime_news_digest",
                "model_name": "claude-opus-4-6",
                "events_count": len(contexts),
                "digest": payload,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
            },
        )
        return alert.alert_event_id

    def _ai_available(self) -> bool:
        return self._cognition_client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))

    @staticmethod
    def _due(last_refreshed_at: datetime | None, *, interval_seconds: int) -> bool:
        if last_refreshed_at is None:
            return True
        return datetime.now(UTC) - last_refreshed_at >= timedelta(seconds=interval_seconds)


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None if value is None else str(value)


def _sha256_json(payload: dict[str, Any]) -> str:
    import hashlib

    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_ai_digest_payload(
    *,
    raw_text: str,
    contexts: list[dict[str, object]],
) -> tuple[dict[str, object], bool, str]:
    parsed_payload: Any = None
    parse_reason = "structured_json"
    candidates = _candidate_json_strings(raw_text)
    for candidate in candidates:
        parsed_payload = _safe_json_load(candidate)
        if isinstance(parsed_payload, dict):
            break
    else:
        parsed_payload = None

    if isinstance(parsed_payload, dict):
        return _normalize_ai_digest_payload(parsed_payload), False, parse_reason

    if not raw_text.strip():
        parse_reason = "empty_text"
    elif candidates:
        parse_reason = "malformed_json"
    else:
        parse_reason = "plain_text"
    return _fallback_ai_digest_payload(raw_text=raw_text, contexts=contexts, reason=parse_reason), True, parse_reason


def _candidate_json_strings(raw_text: str) -> list[str]:
    text = raw_text.strip()
    if not text:
        return []

    candidates: list[str] = [text]
    fence_match = _JSON_BLOCK_RE.search(text)
    if fence_match:
        fenced = fence_match.group(1).strip()
        if fenced:
            candidates.append(fenced)

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            candidates.append(text[index : index + end])
            break

    deduped: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _safe_json_load(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_ai_digest_payload(payload: dict[str, Any]) -> dict[str, object]:
    summary_text = str(payload.get("summary_text") or "").strip()
    operator_takeaway = str(payload.get("operator_takeaway") or "").strip()
    if not summary_text:
        summary_text = operator_takeaway or "AI digest completed."
    if not operator_takeaway:
        operator_takeaway = summary_text

    relevance = str(payload.get("relevance_level") or "UNKNOWN").strip().upper() or "UNKNOWN"
    contradiction_risk = str(payload.get("contradiction_risk") or "UNKNOWN").strip().upper() or "UNKNOWN"
    watch_items_raw = payload.get("watch_items")
    if isinstance(watch_items_raw, list):
        watch_items = [str(item).strip() for item in watch_items_raw if str(item).strip()]
    elif isinstance(watch_items_raw, str) and watch_items_raw.strip():
        watch_items = [watch_items_raw.strip()]
    else:
        watch_items = []

    return {
        "summary_text": summary_text,
        "relevance_level": relevance,
        "contradiction_risk": contradiction_risk,
        "operator_takeaway": operator_takeaway,
        "watch_items": watch_items,
    }


def _fallback_ai_digest_payload(
    *,
    raw_text: str,
    contexts: list[dict[str, object]],
    reason: str,
) -> dict[str, object]:
    trimmed_text = " ".join(raw_text.split())
    summary_text = trimmed_text[:280].strip(" .")
    if not summary_text:
        summary_text = f"AI digest response was empty; preserving runtime continuity for {len(contexts)} event(s)."
    else:
        summary_text = f"AI digest fallback used: {summary_text}"

    watch_items = [str(item.get("title") or "").strip() for item in contexts[:3] if str(item.get("title") or "").strip()]
    return {
        "summary_text": summary_text,
        "relevance_level": "UNKNOWN",
        "contradiction_risk": "UNKNOWN",
        "operator_takeaway": "Structured AI digest unavailable; review underlying news context directly if needed.",
        "watch_items": watch_items,
        "fallback_reason": reason,
        "raw_text_preview": trimmed_text[:280] if trimmed_text else None,
    }
