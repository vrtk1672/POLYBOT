from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.domain.contracts.intelligence_source import IntelligenceSourceContract
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.external_event_enrichment import (
    ENRICHMENT_VERSION,
    ExternalEventEnrichmentRunResult,
    ExternalEventEnrichmentService,
    main as enrichment_main,
)
from app.services.external_intelligence import (
    ExternalIntelligenceFoundationService,
    ManualImportItem,
)
from app.services.query.external_event_enrichment_query_service import (
    ExternalEventEnrichmentQueryService,
)


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
                metadata_json={"seeded_for": "phase4b_tests"},
            ),
        )
    return source_id


def _ingest_manual_items(items: list[ManualImportItem], *, trust_weight: float = 0.73) -> tuple[str, str]:
    source_id = _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category="sports_news",
        trust_weight=trust_weight,
    )
    service = ExternalIntelligenceFoundationService()
    result = service.ingest_manual_items(
        source_key="manual_news",
        items=items,
        source_ref="phase4b-manual",
    )
    assert result is not None
    return source_id, result.intelligence_ingestion_run_id


def _load_normalized_rows() -> list[dict[str, object]]:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM external_events_normalized ORDER BY created_at ASC").fetchall()]


def _base_item(
    *,
    source_event_id: str,
    title: str,
    content: str,
    published_at: datetime | None,
    source_url: str = "https://example.com/story/1",
) -> ManualImportItem:
    return ManualImportItem(
        source_event_id=source_event_id,
        source_url=source_url,
        source_published_at=published_at,
        source_title=title,
        raw_content_text=content,
        raw_payload_json={"headline": title, "body": content},
    )


def test_external_event_enrichment_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"external_event_enrichment_runs", "external_event_enrichments"} <= table_names


def test_successful_enrichment_run_persists_correctly(postgres_test_schema) -> None:
    source_id, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
            )
        ]
    )
    normalized_rows = _load_normalized_rows()
    service = ExternalEventEnrichmentService()
    result = service.enrich_external_events(
        [str(normalized_rows[0]["id"])],
        source_type="phase4b_test",
        source_ref=ingestion_run_id,
        intelligence_ingestion_run_id=ingestion_run_id,
    )

    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM external_event_enrichment_runs LIMIT 1").fetchone()
        enrichment_row = conn.execute("SELECT * FROM external_event_enrichments LIMIT 1").fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert str(run_row["intelligence_ingestion_run_id"]) == ingestion_run_id
    assert run_row["enrichment_version"] == ENRICHMENT_VERSION
    assert enrichment_row is not None
    assert str(enrichment_row["intelligence_source_id"]) == source_id
    assert enrichment_row["normalized_title_snapshot"] == "PSG striker ruled out for tonight"
    assert enrichment_row["topic_class"] == "SPORTS"
    assert enrichment_row["subtopic_class"] == "TEAM_NEWS"
    assert enrichment_row["status"] == "SUCCESS"
    assert float(enrichment_row["trust_weight_snapshot"]) == pytest.approx(0.73, rel=1e-6)
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_logic_behaves_as_expected(postgres_test_schema) -> None:
    _, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
            )
        ]
    )
    normalized_rows = _load_normalized_rows()
    service = ExternalEventEnrichmentService()
    service.enrich_ingestion_run(ingestion_run_id)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        enrichment = conn.execute("SELECT * FROM external_event_enrichments LIMIT 1").fetchone()

    assert enrichment is not None
    entities = enrichment["entities_json"]
    assert "PSG" in entities["organizations"]
    assert "Paris" in entities["locations"]
    assert "injury" in entities["keywords"]
    assert enrichment["contradiction_hint_class"] == "STRONG"
    assert enrichment["novelty_hint_class"] == "NEW"
    assert enrichment["usability_hint_class"] == "REVIEW"


def test_duplicate_derived_novelty_is_persisted(postgres_test_schema) -> None:
    _, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1a",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
                source_url="https://example.com/story?id=1&utm_source=a",
            ),
            _base_item(
                source_event_id="item-1b",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
                source_url="https://example.com/story?id=1&utm_source=b",
            ),
        ]
    )
    normalized_rows = _load_normalized_rows()
    service = ExternalEventEnrichmentService()
    result = service.enrich_ingestion_run(ingestion_run_id)
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT novelty_hint_class, status, explanation_json FROM external_event_enrichments ORDER BY created_at ASC"
        ).fetchall()
    assert len(rows) == 2
    novelty_by_status = {str(row["status"]): str(row["novelty_hint_class"]) for row in rows}
    assert novelty_by_status["SUCCESS"] in {"NEW", "RECENT_DUPLICATE"}
    normalized_statuses = [row["status"] for row in _load_normalized_rows()]
    assert normalized_statuses == ["READY", "DUPLICATE"]
    sorted_novelties = sorted(str(row["novelty_hint_class"]) for row in rows)
    assert sorted_novelties == ["NEW", "RECENT_DUPLICATE"]


def test_bad_normalized_input_is_handled_honestly(postgres_test_schema) -> None:
    _, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1",
                title="Valid title",
                content="   ",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
            )
        ]
    )
    normalized_rows = _load_normalized_rows()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE external_events_normalized SET normalized_summary = '' WHERE id = %s",
            (str(normalized_rows[0]["id"]),),
        )

    service = ExternalEventEnrichmentService()
    result = service.enrich_ingestion_run(ingestion_run_id)
    assert result is not None
    assert result.status == "COMPLETED_WITH_ERRORS"
    assert result.failure_count == 1

    with factory.connect() as conn:
        enrichment = conn.execute("SELECT * FROM external_event_enrichments LIMIT 1").fetchone()
    assert enrichment is not None
    assert enrichment["status"] == "ENRICHMENT_ERROR"
    assert enrichment["error_text"] is not None


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    _, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
            )
        ]
    )
    normalized_rows = _load_normalized_rows()
    service = ExternalEventEnrichmentService()
    result = service.enrich_ingestion_run(ingestion_run_id)
    assert result is not None

    queries = ExternalEventEnrichmentQueryService()
    summary = queries.get_external_event_enrichment_run_summary(result.external_event_enrichment_run_id)
    assert summary is not None
    assert summary["enrichment_count"] == 1
    assert summary["status_counts"]["SUCCESS"] == 1
    assert summary["topic_counts"]["SPORTS"] == 1

    rows = queries.list_enrichments_for_run(result.external_event_enrichment_run_id)
    assert len(rows) == 1
    enrichment_id = str(rows[0]["id"])
    details = queries.get_enrichment_details(enrichment_id)
    assert details is not None
    assert details["topic_class"] == "SPORTS"

    by_event = queries.list_enrichments_for_external_event(str(normalized_rows[0]["id"]))
    assert len(by_event) == 1

    by_topic = queries.find_enrichments_by_topic("SPORTS", limit=5)
    assert len(by_topic) == 1


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeEnrichmentService:
        def enrich_external_events(self, external_event_ids, *, source_type: str, source_ref: str | None = None, intelligence_ingestion_run_id: str | None = None):  # noqa: ANN001,E501
            called["external_event_ids"] = external_event_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return ExternalEventEnrichmentRunResult(
                external_event_enrichment_run_id="enrichment-run-cli-test",
                status="COMPLETED",
                input_count=len(external_event_ids),
                success_count=len(external_event_ids),
                failure_count=0,
            )

        def enrich_ingestion_run(self, intelligence_ingestion_run_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["intelligence_ingestion_run_id"] = intelligence_ingestion_run_id
            called["source_ref"] = source_ref
            return ExternalEventEnrichmentRunResult(
                external_event_enrichment_run_id="enrichment-run-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.external_event_enrichment.ExternalEventEnrichmentService", FakeEnrichmentService)

    exit_code = enrichment_main(
        ["--external-event-ids", "event-1", "--source-ref", "cli-test"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["external_event_ids"] == ["event-1"]
    assert called["source_ref"] == "cli-test"
    assert "enrichment-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    _, ingestion_run_id = _ingest_manual_items(
        [
            _base_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
            )
        ]
    )
    service = ExternalEventEnrichmentService()
    service.enrich_ingestion_run(ingestion_run_id)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
