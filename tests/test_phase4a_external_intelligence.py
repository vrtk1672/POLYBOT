from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.domain.contracts.intelligence_source import IntelligenceSourceContract
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.external_intelligence import (
    ExternalIntelligenceFoundationService,
    IntelligenceIngestionRunResult,
    ManualImportItem,
    main as external_intelligence_main,
)
from app.services.query.external_intelligence_query_service import ExternalIntelligenceQueryService


class FakeHttpxResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class FakeHttpxClient:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self._response = FakeHttpxResponse(text, status_code=status_code)
        self.calls: list[str] = []

    def get(self, url: str):
        self.calls.append(url)
        return self._response


def _register_source(
    *,
    source_key: str,
    source_name: str,
    source_type: str,
    base_url: str | None,
    category: str,
    trust_weight: float,
) -> str:
    run_migrations()
    factory = DatabaseConnectionFactory()
    source_id = str(uuid4())
    with factory.connect() as conn, conn.transaction():
        IntelligenceSourcesRepository().upsert(
            conn,
            IntelligenceSourceContract(
                id=source_id,
                source_key=source_key,
                source_name=source_name,
                source_type=source_type,
                base_url=base_url,
                category=category,
                trust_weight=trust_weight,
                latency_score=0.4,
                noise_score=0.2,
                relevance_scope="sports",
                is_enabled=True,
                metadata_json={"seeded_for": "phase4a_tests"},
            ),
        )
    return source_id


def _manual_items() -> list[ManualImportItem]:
    published = datetime(2026, 4, 19, 10, 0, tzinfo=UTC)
    return [
        ManualImportItem(
            source_event_id="item-1",
            source_url="https://example.com/story?utm_source=rss&id=1",
            source_published_at=published,
            source_title="PSG striker ruled out for tonight",
            raw_content_text="Confirmed injury update before kickoff.",
            raw_payload_json={"headline": "PSG striker ruled out for tonight", "body": "Confirmed injury update before kickoff."},
        )
    ]


def _duplicate_manual_items() -> list[ManualImportItem]:
    published = datetime(2026, 4, 19, 10, 0, tzinfo=UTC)
    return [
        ManualImportItem(
            source_event_id="item-1a",
            source_url="https://example.com/story?id=1&utm_medium=social",
            source_published_at=published,
            source_title="PSG striker ruled out for tonight",
            raw_content_text="Confirmed injury update before kickoff.",
            raw_payload_json={"headline": "PSG striker ruled out for tonight", "body": "Confirmed injury update before kickoff."},
        ),
        ManualImportItem(
            source_event_id="item-1b",
            source_url="https://example.com/story?id=1&utm_campaign=test",
            source_published_at=published,
            source_title="PSG striker ruled out for tonight",
            raw_content_text="Confirmed injury update before kickoff.",
            raw_payload_json={"headline": "PSG striker ruled out for tonight", "body": "Confirmed injury update before kickoff."},
        ),
    ]


def test_external_intelligence_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {
        "intelligence_sources",
        "intelligence_ingestion_runs",
        "external_raw_events",
        "external_events_normalized",
    } <= table_names


def test_successful_manual_ingestion_persists_raw_and_normalized_events(postgres_test_schema) -> None:
    source_id = _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category="sports_news",
        trust_weight=0.73,
    )
    service = ExternalIntelligenceFoundationService()
    result = service.ingest_manual_items(
        source_key="manual_news",
        items=_manual_items(),
        source_ref="phase4a-manual",
    )

    assert result is not None
    assert result.status == "COMPLETED"
    assert result.fetched_count == 1
    assert result.normalized_count == 1
    assert result.deduped_count == 0

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM intelligence_ingestion_runs LIMIT 1").fetchone()
        raw_row = conn.execute("SELECT * FROM external_raw_events LIMIT 1").fetchone()
        normalized_row = conn.execute("SELECT * FROM external_events_normalized LIMIT 1").fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert str(run_row["intelligence_source_id"]) == source_id
    assert run_row["run_type"] == "MANUAL_IMPORT"
    assert raw_row is not None
    assert str(raw_row["intelligence_source_id"]) == source_id
    assert raw_row["source_title"] == "PSG striker ruled out for tonight"
    assert normalized_row is not None
    assert normalized_row["normalized_title"] == "PSG striker ruled out for tonight"
    assert normalized_row["status"] == "READY"
    assert float(normalized_row["trust_weight_snapshot"]) == pytest.approx(0.73, rel=1e-6)
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_dedupe_marks_duplicates(postgres_test_schema) -> None:
    _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category="sports_news",
        trust_weight=0.73,
    )
    service = ExternalIntelligenceFoundationService()
    result = service.ingest_manual_items(
        source_key="manual_news",
        items=_duplicate_manual_items(),
        source_ref="phase4a-dedupe",
    )
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.fetched_count == 2
    assert result.normalized_count == 2
    assert result.deduped_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT status, dedupe_key, metadata_json FROM external_events_normalized ORDER BY created_at ASC"
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["status"] == "READY"
    assert rows[1]["status"] == "DUPLICATE"
    assert rows[0]["dedupe_key"] == rows[1]["dedupe_key"]
    assert rows[1]["metadata_json"]["duplicate_of"] is not None


def test_failed_fetch_is_recorded_honestly(postgres_test_schema) -> None:
    _register_source(
        source_key="rss_news",
        source_name="RSS News",
        source_type="RSS",
        base_url="https://example.com/rss.xml",
        category="sports_news",
        trust_weight=0.66,
    )
    service = ExternalIntelligenceFoundationService(http_client=FakeHttpxClient("boom", status_code=500))
    result = service.ingest_rss_source(source_key="rss_news", source_ref="phase4a-rss")

    assert result is not None
    assert result.status == "FAILED"
    assert result.failed_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM intelligence_ingestion_runs LIMIT 1").fetchone()
        raw_rows = conn.execute("SELECT * FROM external_raw_events").fetchall()
        normalized_rows = conn.execute("SELECT * FROM external_events_normalized").fetchall()

    assert run_row is not None
    assert run_row["status"] == "FAILED"
    assert raw_rows == []
    assert normalized_rows == []


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category="sports_news",
        trust_weight=0.73,
    )
    service = ExternalIntelligenceFoundationService()
    result = service.ingest_manual_items(
        source_key="manual_news",
        items=_duplicate_manual_items(),
        source_ref="phase4a-query",
    )
    assert result is not None

    queries = ExternalIntelligenceQueryService()
    sources = queries.list_intelligence_sources()
    assert len(sources) == 1
    assert sources[0]["source_key"] == "manual_news"

    summary = queries.get_ingestion_run_summary(result.intelligence_ingestion_run_id)
    assert summary is not None
    assert summary["raw_count"] == 2
    assert summary["normalized_count"] == 2
    assert summary["normalized_status_counts"]["DUPLICATE"] == 1

    raw_rows = queries.list_raw_events_for_run(result.intelligence_ingestion_run_id)
    assert len(raw_rows) == 2
    normalized_rows = queries.list_normalized_events_for_run(result.intelligence_ingestion_run_id)
    assert len(normalized_rows) == 2

    recent = queries.list_recent_normalized_events(limit=5)
    assert len(recent) == 2

    dedupe_key = str(normalized_rows[0]["dedupe_key"])
    duplicates = queries.find_duplicates_by_dedupe_key(dedupe_key)
    assert len(duplicates) == 2


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}
    payload_path = tmp_path / "manual_events.json"
    payload_path.write_text(
        json.dumps(
            [
                {
                    "source_event_id": "manual-1",
                    "source_url": "https://example.com/story/1",
                    "source_published_at": "2026-04-19T10:00:00Z",
                    "source_title": "Manual imported event",
                    "raw_content_text": "Imported content",
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakeFoundationService:
        def ingest_manual_items(self, *, source_key: str, items, source_ref: str | None = None):  # noqa: ANN001
            called["source_key"] = source_key
            called["item_count"] = len(items)
            called["source_ref"] = source_ref
            return IntelligenceIngestionRunResult(
                intelligence_ingestion_run_id="ingestion-run-cli-test",
                status="COMPLETED",
                fetched_count=len(items),
                normalized_count=len(items),
                deduped_count=0,
                failed_count=0,
            )

        def ingest_rss_source(self, *, source_key: str, source_ref: str | None = None):  # noqa: ANN001
            called["source_key"] = source_key
            called["source_ref"] = source_ref
            return IntelligenceIngestionRunResult(
                intelligence_ingestion_run_id="ingestion-run-cli-test",
                status="COMPLETED",
                fetched_count=1,
                normalized_count=1,
                deduped_count=0,
                failed_count=0,
            )

    monkeypatch.setattr("app.services.external_intelligence.ExternalIntelligenceFoundationService", FakeFoundationService)

    exit_code = external_intelligence_main(
        ["--manual-import-json", str(payload_path), "--source-key", "manual_news", "--source-ref", "cli-test"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["source_key"] == "manual_news"
    assert called["item_count"] == 1
    assert called["source_ref"] == "cli-test"
    assert "ingestion-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category="sports_news",
        trust_weight=0.73,
    )
    service = ExternalIntelligenceFoundationService()
    service.ingest_manual_items(
        source_key="manual_news",
        items=_manual_items(),
        source_ref="phase4a-isolation",
    )

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
