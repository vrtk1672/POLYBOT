from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.thesis_profiles import ThesisProfile
from app.repositories.thesis_profile_repository import ThesisProfileRepository, thesis_profile_from_row


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "thesis_profile_evidence_items",
            "thesis_profile_runs",
            "thesis_profiles",
            "coordinator_decision_inputs",
            "coordinator_decisions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")


def test_repository_persists_thesis_profile_and_evidence(postgres_test_schema) -> None:
    _prepare()
    profile = ThesisProfile(
        thesis_id="thesis-repo",
        market_id="market-repo",
        status="COMPLETE",
        thesis_type="RUNTIME_COORDINATOR_THESIS",
        why_now="Runtime coordinator evidence exists.",
        confidence=0.9,
        evidence={"source": "test"},
        invalidation_rules=["invalidate_if_orderbook_becomes_stale"],
        risk_notes=["NO_RISK_CORE"],
        source_coordinator_decision_id="coord-repo",
        source_brain_output_ids=["brain-repo"],
        source_signal_ids=["signal-repo"],
        orderbook_snapshot_id=1,
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row, created = ThesisProfileRepository().upsert_profile(conn, profile)
        ThesisProfileRepository().record_evidence_items(conn, profile)
        evidence_count = conn.execute("SELECT COUNT(*) AS count FROM thesis_profile_evidence_items").fetchone()["count"]

    assert created is True
    assert thesis_profile_from_row(row).thesis_id == "thesis-repo"
    assert row["paper_candidate_allowed"] is False
    assert evidence_count == 4

