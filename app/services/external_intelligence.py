from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse
from uuid import uuid4
from xml.etree import ElementTree

import httpx

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.external_event_normalized import ExternalEventNormalizedContract
from app.domain.contracts.external_raw_event import ExternalRawEventContract
from app.domain.contracts.intelligence_ingestion_run import (
    IntelligenceIngestionRunCloseContract,
    IntelligenceIngestionRunOpenContract,
)
from app.domain.contracts.intelligence_source import IntelligenceSourceContract
from app.repositories.external_events_normalized_repository import ExternalEventsNormalizedRepository
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.recorders.external_event_normalized_recorder import ExternalEventNormalizedRecorder
from app.services.recorders.external_raw_event_recorder import ExternalRawEventRecorder
from app.services.recorders.intelligence_ingestion_run_recorder import IntelligenceIngestionRunRecorder

logger = logging.getLogger(__name__)

NORMALIZATION_VERSION = "phase4a-external-intelligence-v1"


@dataclass(slots=True)
class ManualImportItem:
    source_event_id: str | None
    source_url: str | None
    source_published_at: datetime | None
    source_title: str | None
    raw_content_text: str | None
    raw_payload_json: dict[str, object]


@dataclass(slots=True)
class IntelligenceIngestionRunResult:
    intelligence_ingestion_run_id: str
    status: str
    fetched_count: int
    normalized_count: int
    deduped_count: int
    failed_count: int


class ExternalIntelligenceFoundationService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        http_client: httpx.Client | None = None,
        normalization_version: str = NORMALIZATION_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._http_client = http_client
        self._normalization_version = normalization_version
        self._sources_repo = IntelligenceSourcesRepository()
        self._normalized_repo = ExternalEventsNormalizedRepository()
        self._run_recorder = IntelligenceIngestionRunRecorder()
        self._raw_recorder = ExternalRawEventRecorder()
        self._normalized_recorder = ExternalEventNormalizedRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def register_source(self, source: IntelligenceSourceContract) -> None:
        if not self.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._sources_repo.upsert(conn, source)

    def ingest_manual_items(
        self,
        *,
        source_key: str,
        items: list[ManualImportItem],
        source_ref: str | None = None,
    ) -> IntelligenceIngestionRunResult | None:
        if not self.enabled:
            return None
        if not items:
            raise ValueError("at least one manual import item is required")
        return self._ingest_source_items(
            source_key=source_key,
            run_type="MANUAL_IMPORT",
            source_ref=source_ref,
            items=items,
        )

    def ingest_rss_source(
        self,
        *,
        source_key: str,
        source_ref: str | None = None,
    ) -> IntelligenceIngestionRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            source = self._sources_repo.get_by_key(conn, source_key)
        if source is None:
            raise ValueError(f"intelligence source not found: {source_key}")
        if str(source["source_type"]) != "RSS":
            raise ValueError(f"source is not RSS: {source_key}")
        base_url = source["base_url"]
        if not base_url:
            raise ValueError(f"RSS source missing base_url: {source_key}")
        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        try:
            items = self._fetch_rss_items(str(base_url))
        except Exception as exc:
            logger.exception("external_intelligence_rss_fetch_failed source_key=%s", source_key)
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    IntelligenceIngestionRunOpenContract(
                        id=run_id,
                        intelligence_source_id=str(source["id"]),
                        run_type="RSS_FETCH",
                        status="OPEN",
                        started_at=started_at,
                        metadata_json={"source_ref": source_ref or str(base_url)},
                    ),
                )
                self._run_recorder.close_run(
                    conn,
                    IntelligenceIngestionRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        fetched_count=0,
                        normalized_count=0,
                        deduped_count=0,
                        failed_count=1,
                        metadata_json={"error": str(exc), "source_key": source_key},
                    ),
                )
            return IntelligenceIngestionRunResult(
                intelligence_ingestion_run_id=run_id,
                status="FAILED",
                fetched_count=0,
                normalized_count=0,
                deduped_count=0,
                failed_count=1,
            )
        return self._ingest_source_items(
            source_key=source_key,
            run_type="RSS_FETCH",
            source_ref=source_ref or str(base_url),
            items=items,
            preset_run_id=run_id,
            preset_started_at=started_at,
        )

    def ingest_registered_source(
        self,
        *,
        source_key: str,
        source_ref: str | None = None,
    ) -> IntelligenceIngestionRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            source = self._sources_repo.get_by_key(conn, source_key)
        if source is None:
            raise ValueError(f"intelligence source not found: {source_key}")
        if not bool(source["is_enabled"]):
            raise ValueError(f"intelligence source is disabled: {source_key}")
        source_type = str(source["source_type"])
        if source_type == "RSS":
            return self.ingest_rss_source(source_key=source_key, source_ref=source_ref)
        if source_type in {"OFFICIAL_SITE", "NEWS_SITE"}:
            base_url = source["base_url"]
            if not base_url:
                raise ValueError(f"official source missing base_url: {source_key}")
            run_id = str(uuid4())
            started_at = datetime.now(UTC)
            try:
                items = self._fetch_official_site_items(
                    source_key=source_key,
                    base_url=str(base_url),
                    source_metadata=dict(source.get("metadata_json") or {}),
                )
            except Exception as exc:
                logger.exception("external_intelligence_site_fetch_failed source_key=%s", source_key)
                with self._factory.connect() as conn, conn.transaction():
                    self._run_recorder.open_run(
                        conn,
                        IntelligenceIngestionRunOpenContract(
                            id=run_id,
                            intelligence_source_id=str(source["id"]),
                            run_type="SITE_FETCH",
                            status="OPEN",
                            started_at=started_at,
                            metadata_json={"source_ref": source_ref or str(base_url)},
                        ),
                    )
                    self._run_recorder.close_run(
                        conn,
                        IntelligenceIngestionRunCloseContract(
                            id=run_id,
                            status="FAILED",
                            ended_at=datetime.now(UTC),
                            fetched_count=0,
                            normalized_count=0,
                            deduped_count=0,
                            failed_count=1,
                            metadata_json={"error": str(exc), "source_key": source_key},
                        ),
                    )
                return IntelligenceIngestionRunResult(
                    intelligence_ingestion_run_id=run_id,
                    status="FAILED",
                    fetched_count=0,
                    normalized_count=0,
                    deduped_count=0,
                    failed_count=1,
                )
            return self._ingest_source_items(
                source_key=source_key,
                run_type="SITE_FETCH",
                source_ref=source_ref or str(base_url),
                items=items,
                preset_run_id=run_id,
                preset_started_at=started_at,
            )
        raise ValueError(f"unsupported intelligence source type for runtime ingestion: {source_type}")

    def _ingest_source_items(
        self,
        *,
        source_key: str,
        run_type: str,
        source_ref: str | None,
        items: list[ManualImportItem],
        preset_run_id: str | None = None,
        preset_started_at: datetime | None = None,
    ) -> IntelligenceIngestionRunResult:
        run_id = preset_run_id or str(uuid4())
        started_at = preset_started_at or datetime.now(UTC)
        fetched_count = 0
        normalized_count = 0
        deduped_count = 0
        failed_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                source = self._sources_repo.get_by_key(conn, source_key)
                if source is None:
                    raise ValueError(f"intelligence source not found: {source_key}")

                self._run_recorder.open_run(
                    conn,
                    IntelligenceIngestionRunOpenContract(
                        id=run_id,
                        intelligence_source_id=str(source["id"]),
                        run_type=run_type,
                        status="OPEN",
                        started_at=started_at,
                        metadata_json={
                            "source_ref": source_ref,
                            "normalization_version": self._normalization_version,
                        },
                    ),
                )
                opened_run = True

                for item in items:
                    raw_contract = self._build_raw_contract(
                        run_id=run_id,
                        source=source,
                        item=item,
                    )
                    self._raw_recorder.record(conn, raw_contract)
                    fetched_count += 1

                    normalized_contract = self._build_normalized_contract(
                        conn=conn,
                        source=source,
                        raw_event=raw_contract,
                        item=item,
                    )
                    self._normalized_recorder.record(conn, normalized_contract)
                    normalized_count += 1
                    if normalized_contract.status == "DUPLICATE":
                        deduped_count += 1

                status = "COMPLETED" if failed_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    IntelligenceIngestionRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        fetched_count=fetched_count,
                        normalized_count=normalized_count,
                        deduped_count=deduped_count,
                        failed_count=failed_count,
                        metadata_json={
                            "source_key": source_key,
                            "source_ref": source_ref,
                            "normalization_version": self._normalization_version,
                        },
                    ),
                )

            return IntelligenceIngestionRunResult(
                intelligence_ingestion_run_id=run_id,
                status=status,
                fetched_count=fetched_count,
                normalized_count=normalized_count,
                deduped_count=deduped_count,
                failed_count=failed_count,
            )
        except Exception as exc:
            logger.exception("external_intelligence_ingestion_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                source = self._sources_repo.get_by_key(conn, source_key)
                source_id = str(source["id"]) if source is not None else None
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        IntelligenceIngestionRunOpenContract(
                            id=run_id,
                            intelligence_source_id=source_id,
                            run_type=run_type,
                            status="OPEN",
                            started_at=started_at,
                            metadata_json={"source_ref": source_ref},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    IntelligenceIngestionRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        fetched_count=fetched_count,
                        normalized_count=normalized_count,
                        deduped_count=deduped_count,
                        failed_count=max(1, len(items)),
                        metadata_json={"error": str(exc), "source_key": source_key},
                    ),
                )
            return IntelligenceIngestionRunResult(
                intelligence_ingestion_run_id=run_id,
                status="FAILED",
                fetched_count=fetched_count,
                normalized_count=normalized_count,
                deduped_count=deduped_count,
                failed_count=max(1, len(items)),
            )

    def _build_raw_contract(
        self,
        *,
        run_id: str,
        source: dict[str, object],
        item: ManualImportItem,
    ) -> ExternalRawEventContract:
        payload = _json_safe(item.raw_payload_json)
        raw_hash = _sha256_text(
            json.dumps(
                {
                    "source_event_id": item.source_event_id,
                    "source_url": item.source_url,
                    "source_title": item.source_title,
                    "raw_content_text": item.raw_content_text,
                    "raw_payload_json": payload,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return ExternalRawEventContract(
            id=str(uuid4()),
            intelligence_ingestion_run_id=run_id,
            intelligence_source_id=str(source["id"]),
            source_event_id=item.source_event_id,
            source_url=item.source_url,
            source_published_at=item.source_published_at,
            source_title=item.source_title,
            raw_content_text=item.raw_content_text,
            raw_payload_json=payload,
            raw_hash=raw_hash,
            fetched_at=datetime.now(UTC),
        )

    def _build_normalized_contract(
        self,
        *,
        conn,
        source: dict[str, object],
        raw_event: ExternalRawEventContract,
        item: ManualImportItem,
    ) -> ExternalEventNormalizedContract:
        normalized_title = _normalize_title(item.source_title or item.raw_content_text or "untitled external event")
        canonical_url = _canonicalize_url(item.source_url)
        normalized_summary = _normalize_summary(item.raw_content_text, item.raw_payload_json, normalized_title)
        canonical_hash = _sha256_text(
            json.dumps(
                {
                    "title": normalized_title,
                    "canonical_url": canonical_url,
                    "summary": normalized_summary,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        dedupe_key = _sha256_text(
            json.dumps(
                {
                    "title": normalized_title.casefold(),
                    "published_at": item.source_published_at.isoformat() if item.source_published_at else None,
                    "canonical_url": canonical_url,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        duplicates = self._normalized_repo.find_by_dedupe_key(conn, dedupe_key)
        status = "DUPLICATE" if duplicates else "READY"
        duplicate_of = str(duplicates[0]["id"]) if duplicates else None

        return ExternalEventNormalizedContract(
            id=str(uuid4()),
            external_raw_event_id=raw_event.id,
            intelligence_source_id=str(source["id"]),
            normalized_title=normalized_title,
            normalized_summary=normalized_summary,
            published_at=item.source_published_at,
            canonical_url=canonical_url,
            canonical_hash=canonical_hash,
            event_language="en",
            source_category=str(source["category"]),
            trust_weight_snapshot=_normalize_score(float(source["trust_weight"])),
            dedupe_key=dedupe_key,
            normalization_version=self._normalization_version,
            status=status,
            metadata_json={
                "raw_hash": raw_event.raw_hash,
                "source_key": str(source["source_key"]),
                "duplicate_of": duplicate_of,
            },
        )

    def _fetch_rss_items(self, base_url: str) -> list[ManualImportItem]:
        client = self._http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        response = client.get(base_url)
        response.raise_for_status()
        return _parse_rss_items(response.text)

    def _fetch_official_site_items(
        self,
        *,
        source_key: str,
        base_url: str,
        source_metadata: dict[str, object],
    ) -> list[ManualImportItem]:
        client = self._http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        response = client.get(base_url, headers={"User-Agent": "POLYBOT/0.1 (+runtime intelligence)"})
        response.raise_for_status()
        parser_name = str(source_metadata.get("runtime_parser") or "").strip().lower()
        max_items = int(source_metadata.get("max_items") or 10)
        if parser_name == "ap_top_news_hub_v1":
            return _parse_ap_top_news_items(response.text, max_items=max_items)
        raise ValueError(f"no official site parser configured for source_key={source_key}")


def _parse_rss_items(xml_text: str) -> list[ManualImportItem]:
    root = ElementTree.fromstring(xml_text)
    items: list[ManualImportItem] = []
    for node in root.findall(".//item"):
        title = _xml_text(node.find("title"))
        link = _xml_text(node.find("link"))
        guid = _xml_text(node.find("guid"))
        description = _xml_text(node.find("description"))
        pub_date = _parse_datetime(_xml_text(node.find("pubDate")))
        payload = {
            "title": title,
            "link": link,
            "guid": guid,
            "description": description,
            "pubDate": _xml_text(node.find("pubDate")),
        }
        items.append(
            ManualImportItem(
                source_event_id=guid or link or title,
                source_url=link,
                source_published_at=pub_date,
                source_title=title,
                raw_content_text=description,
                raw_payload_json=payload,
            )
        )
    return items


def _parse_ap_top_news_items(html_text: str, *, max_items: int) -> list[ManualImportItem]:
    pattern = re.compile(r'<a[^>]+href="(https://apnews\.com/article/[^"]+)"[^>]*>(.*?)</a>', re.S)
    seen_urls: set[str] = set()
    items: list[ManualImportItem] = []
    for href, body in pattern.findall(html_text):
        title = re.sub(r"<[^>]+>", " ", body)
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 25:
            continue
        if title.isdigit():
            continue
        canonical_url = _canonicalize_url(href)
        if not canonical_url or canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        items.append(
            ManualImportItem(
                source_event_id=canonical_url,
                source_url=canonical_url,
                source_published_at=None,
                source_title=title[:300],
                raw_content_text=title[:500],
                raw_payload_json={
                    "title": title[:300],
                    "link": canonical_url,
                    "parser": "ap_top_news_hub_v1",
                },
            )
        )
        if len(items) >= max_items:
            break
    return items


def _xml_text(node: ElementTree.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip() or None


def _normalize_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:300]


def _normalize_summary(raw_content_text: str | None, payload: dict[str, object], title: str) -> str:
    candidate = raw_content_text or str(payload.get("summary") or payload.get("description") or title)
    cleaned = re.sub(r"<[^>]+>", " ", candidate)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500]


def _canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = sorted(
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.startswith("utm_")
    )
    canonical = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query="&".join(f"{k}={v}" for k, v in query),
        fragment="",
    )
    normalized = urlunparse(canonical)
    return normalized.rstrip("/")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_score(value: float) -> float:
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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def _load_manual_import_items(path: str) -> list[ManualImportItem]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manual import file must be a JSON array")
    items: list[ManualImportItem] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("manual import rows must be JSON objects")
        items.append(
            ManualImportItem(
                source_event_id=_as_optional_str(row.get("source_event_id")),
                source_url=_as_optional_str(row.get("source_url")),
                source_published_at=_parse_datetime(_as_optional_str(row.get("source_published_at"))),
                source_title=_as_optional_str(row.get("source_title")),
                raw_content_text=_as_optional_str(row.get("raw_content_text")),
                raw_payload_json=_json_safe(dict(row)),
            )
        )
    return items


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 4A external intelligence ingestion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manual-import-json", help="path to a JSON array of external source items")
    group.add_argument("--rss-source-key", help="registered RSS source_key to fetch")
    parser.add_argument("--source-key", help="registered source_key for manual import mode")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = ExternalIntelligenceFoundationService()
    if args.manual_import_json:
        if not args.source_key:
            raise SystemExit("--source-key is required with --manual-import-json")
        items = _load_manual_import_items(args.manual_import_json)
        result = service.ingest_manual_items(
            source_key=args.source_key,
            items=items,
            source_ref=args.source_ref or args.manual_import_json,
        )
    else:
        result = service.ingest_rss_source(
            source_key=args.rss_source_key,
            source_ref=args.source_ref,
        )

    if result is None:
        print("External intelligence persistence is unavailable.")
        return 1

    print(
        f"intelligence_ingestion_run_id={result.intelligence_ingestion_run_id} "
        f"status={result.status} "
        f"fetched={result.fetched_count} "
        f"normalized={result.normalized_count} "
        f"deduped={result.deduped_count} "
        f"failed={result.failed_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
