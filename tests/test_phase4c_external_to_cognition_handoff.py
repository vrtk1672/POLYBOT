from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.domain.contracts.intelligence_source import IntelligenceSourceContract
from app.repositories.intelligence_sources_repository import IntelligenceSourcesRepository
from app.services.external_event_enrichment import ExternalEventEnrichmentService
from app.services.external_intelligence import ExternalIntelligenceFoundationService, ManualImportItem
from app.services.external_to_cognition_handoff import (
    CognitionHandoffRunResult,
    ExternalToCognitionHandoffService,
    main as handoff_main,
)
from app.services.query.cognition_handoff_query_service import CognitionHandoffQueryService


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
                metadata_json={"seeded_for": "phase4c_tests"},
            ),
        )
    return source_id


def _manual_item(
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


def _seed_enrichments(
    items: list[ManualImportItem],
    *,
    trust_weight: float = 0.73,
    category: str = "sports_news",
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    _register_source(
        source_key="manual_news",
        source_name="Manual News",
        source_type="MANUAL_IMPORT",
        base_url=None,
        category=category,
        trust_weight=trust_weight,
    )
    intake = ExternalIntelligenceFoundationService()
    ingestion = intake.ingest_manual_items(
        source_key="manual_news",
        items=items,
        source_ref="phase4c-manual",
    )
    assert ingestion is not None
    enrichment_service = ExternalEventEnrichmentService()
    enrichment = enrichment_service.enrich_ingestion_run(ingestion.intelligence_ingestion_run_id)
    assert enrichment is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        normalized_rows = [
            dict(row)
            for row in conn.execute("SELECT * FROM external_events_normalized ORDER BY created_at ASC").fetchall()
        ]
        enrichment_rows = [
            dict(row)
            for row in conn.execute("SELECT * FROM external_event_enrichments ORDER BY created_at ASC").fetchall()
        ]
    return ingestion.intelligence_ingestion_run_id, normalized_rows, enrichment_rows


def test_cognition_handoff_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"cognition_handoff_runs", "cognition_handoff_candidates"} <= table_names


def test_successful_handoff_run_persists_correctly(postgres_test_schema) -> None:
    ingestion_run_id, _, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime.now(UTC),
            )
        ]
    )
    service = ExternalToCognitionHandoffService()
    result = service.evaluate_enrichment_run(enrichment_rows[0]["external_event_enrichment_run_id"])
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.sent_count == 0
    assert result.held_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM cognition_handoff_runs LIMIT 1").fetchone()
        candidate_row = conn.execute("SELECT * FROM cognition_handoff_candidates LIMIT 1").fetchone()
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()

    assert run_row is not None
    assert str(run_row["external_event_enrichment_run_id"]) == str(enrichment_rows[0]["external_event_enrichment_run_id"])
    assert candidate_row is not None
    assert str(candidate_row["external_event_enrichment_id"]) == str(enrichment_rows[0]["id"])
    assert candidate_row["handoff_decision_class"] == "HOLD_FOR_REVIEW"
    assert candidate_row["handoff_priority_class"] == "NORMAL"
    assert candidate_row["linked_interpretation_run_id"] is None
    assert candidate_row["linked_interpretation_id"] is None
    assert live_orders == []
    assert paper_orders == []


def test_deterministic_handoff_decisions_behave_as_expected(postgres_test_schema) -> None:
    _, _, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1",
                title="Court ruling reverses minister vote challenge",
                content="Court ruling reverses a minister challenge and legal appeal escalates.",
                published_at=datetime.now(UTC),
            )
        ],
        trust_weight=0.82,
        category="legal_news",
    )
    service = ExternalToCognitionHandoffService()
    result = service.evaluate_enrichments([str(enrichment_rows[0]["id"])], source_type="phase4c_test")
    assert result is not None
    assert result.sent_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        candidate = conn.execute("SELECT * FROM cognition_handoff_candidates LIMIT 1").fetchone()
    assert candidate is not None
    assert candidate["handoff_decision_class"] == "SEND_TO_INTERPRETER"
    assert candidate["handoff_priority_class"] == "HIGH"
    assert candidate["handoff_reason_code"] == "high_utility_recent"


def test_duplicate_and_stale_events_are_skipped_truthfully(postgres_test_schema) -> None:
    _, _, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1a",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff.",
                published_at=datetime.now(UTC),
                source_url="https://example.com/story?id=1&utm_source=a",
            ),
            _manual_item(
                source_event_id="item-1b",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff.",
                published_at=datetime.now(UTC),
                source_url="https://example.com/story?id=1&utm_source=b",
            ),
        ]
    )
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        stale_cutoff = datetime.now(UTC) - timedelta(days=4)
        conn.execute(
            "UPDATE external_events_normalized SET published_at = %s WHERE id = %s",
            (stale_cutoff, str(enrichment_rows[0]["external_event_id"])),
        )
        conn.execute(
            "UPDATE external_event_enrichments SET novelty_hint_class = 'STALE' WHERE id = %s",
            (str(enrichment_rows[0]["id"]),),
        )
        conn.execute(
            "UPDATE external_event_enrichments SET novelty_hint_class = 'RECENT_DUPLICATE' WHERE id = %s",
            (str(enrichment_rows[1]["id"]),),
        )

    service = ExternalToCognitionHandoffService()
    result = service.evaluate_enrichments([str(row["id"]) for row in enrichment_rows], source_type="phase4c_test")
    assert result is not None
    assert result.skipped_count == 2

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT handoff_decision_class, handoff_reason_code FROM cognition_handoff_candidates ORDER BY created_at ASC"
        ).fetchall()
    decisions = sorted((str(row["handoff_decision_class"]), str(row["handoff_reason_code"])) for row in rows)
    assert decisions == [
        ("SKIP_DUPLICATE", "duplicate_recent"),
        ("SKIP_STALE", "stale_event"),
    ]


def test_bad_input_is_handled_honestly(postgres_test_schema) -> None:
    _, _, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime.now(UTC),
            )
        ]
    )
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE external_event_enrichments SET status = 'ENRICHMENT_ERROR' WHERE id = %s",
            (str(enrichment_rows[0]["id"]),),
        )

    service = ExternalToCognitionHandoffService()
    result = service.evaluate_enrichments([str(enrichment_rows[0]["id"])], source_type="phase4c_test")
    assert result is not None
    assert result.status == "COMPLETED_WITH_ERRORS"
    assert result.failure_count == 1

    with factory.connect() as conn:
        candidate = conn.execute("SELECT * FROM cognition_handoff_candidates LIMIT 1").fetchone()
    assert candidate is not None
    assert candidate["status"] == "HANDOFF_ERROR"
    assert candidate["error_text"] is not None


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    _, normalized_rows, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime.now(UTC),
            )
        ]
    )
    service = ExternalToCognitionHandoffService()
    result = service.evaluate_enrichments([str(enrichment_rows[0]["id"])], source_type="phase4c_test")
    assert result is not None

    queries = CognitionHandoffQueryService()
    summary = queries.get_cognition_handoff_run_summary(result.cognition_handoff_run_id)
    assert summary is not None
    assert summary["candidate_count"] == 1
    assert summary["decision_counts"]["HOLD_FOR_REVIEW"] == 1

    rows = queries.list_handoff_candidates_for_run(result.cognition_handoff_run_id)
    assert len(rows) == 1
    candidate_id = str(rows[0]["id"])
    details = queries.get_handoff_candidate_details(candidate_id)
    assert details is not None
    assert details["handoff_decision_class"] == "HOLD_FOR_REVIEW"

    by_event = queries.list_handoff_candidates_for_external_event(str(normalized_rows[0]["id"]))
    assert len(by_event) == 1

    pending = queries.list_pending_handoff_candidates(limit=5)
    assert len(pending) == 1


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeHandoffService:
        def evaluate_enrichments(self, enrichment_ids, *, source_type: str, source_ref: str | None = None, external_event_enrichment_run_id: str | None = None):  # noqa: ANN001,E501
            called["enrichment_ids"] = enrichment_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            return CognitionHandoffRunResult(
                cognition_handoff_run_id="handoff-run-cli-test",
                status="COMPLETED",
                input_count=len(enrichment_ids),
                sent_count=1,
                held_count=0,
                skipped_count=0,
                failure_count=0,
            )

        def evaluate_enrichment_run(self, external_event_enrichment_run_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["external_event_enrichment_run_id"] = external_event_enrichment_run_id
            called["source_ref"] = source_ref
            return CognitionHandoffRunResult(
                cognition_handoff_run_id="handoff-run-cli-test",
                status="COMPLETED",
                input_count=1,
                sent_count=1,
                held_count=0,
                skipped_count=0,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.external_to_cognition_handoff.ExternalToCognitionHandoffService", FakeHandoffService)

    exit_code = handoff_main(
        ["--external-event-enrichment-ids", "enrichment-1", "--source-ref", "cli-test"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["enrichment_ids"] == ["enrichment-1"]
    assert called["source_ref"] == "cli-test"
    assert "handoff-run-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    _, _, enrichment_rows = _seed_enrichments(
        [
            _manual_item(
                source_event_id="item-1",
                title="PSG striker ruled out for tonight",
                content="Confirmed injury update before kickoff in Paris.",
                published_at=datetime.now(UTC),
            )
        ]
    )
    service = ExternalToCognitionHandoffService()
    service.evaluate_enrichments([str(enrichment_rows[0]["id"])], source_type="phase4c_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
