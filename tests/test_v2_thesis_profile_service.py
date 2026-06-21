from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.thesis_profiles import ThesisProfileService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "thesis_profile_evidence_items",
            "thesis_profile_runs",
            "thesis_profiles",
            "orderbook_snapshots",
            "signal_market_links",
            "brain_output_dependencies",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_outputs",
            "neuron_signals",
            "markets_v2",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_runtime_decision(
    decision_id: str = "coord-runtime",
    *,
    final_state: str = "REVIEW_REQUIRED",
    market_id: str | None = "market-runtime",
    source_signal: bool = True,
    signal_link: bool = True,
    orderbook: bool = True,
    dry_run: bool = False,
    confidence: float = 0.75,
) -> None:
    generated_by = "dry_run" if dry_run else "runtime"
    metadata = {
        "generated_by": generated_by,
        "producer_name": "runtime_coordinator_adapter",
        "is_runtime_generated": not dry_run,
        "is_dry_run_generated": dry_run,
        "source_brain_output_ids": [f"brain-{decision_id}"],
        "source_signal_ids": [f"signal-{decision_id}"] if source_signal else [],
        "missing_requirements": [],
    }
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if market_id:
            conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES (%s, 'Runtime market?', %s)", (market_id, market_id))
        conn.execute(
            """
            INSERT INTO coordinator_decisions (
                coordinator_decision_id, market_id, final_state, primary_reason,
                confidence, execution_allowed, approved_actions_json, blocked_actions_json,
                required_reviews_json, risk_flags_json, source_brain_count,
                input_output_count, conflict_count, status, metadata_json, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, 'Runtime coordinator test decision.',
                %s, false, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                '[]'::jsonb, 1, 1, 0, 'ACTIVE', %s::jsonb, now(), now()
            )
            """,
            (decision_id, market_id, final_state, confidence, __import__("json").dumps(metadata)),
        )
        if source_signal:
            conn.execute(
                """
                INSERT INTO neuron_signals (
                    signal_id, neuron, event_type, source_name, market_id,
                    confidence, strength, evidence_json, status, created_at, updated_at
                )
                VALUES (%s, 'market', 'source_status_observed', 'runtime_source', %s, 0.8, 0.7, '{}'::jsonb, 'ACTIVE', now(), now())
                """,
                (f"signal-{decision_id}", market_id),
            )
            conn.execute(
                """
                INSERT INTO brain_outputs (
                    brain_output_id, brain, output_type, market_id, recommendation,
                    confidence, risk_flags_json, metadata_json, generated_by, status,
                    created_at, updated_at
                )
                VALUES (%s, 'runtime_brain_adapter', 'CAUTION', %s, 'WEAK_SIGNAL', 0.7, '[]'::jsonb, '{}'::jsonb, 'runtime', 'ACTIVE', now(), now())
                """,
                (f"brain-{decision_id}", market_id),
            )
            conn.execute(
                """
                INSERT INTO coordinator_decision_inputs (coordinator_decision_id, brain_output_id, brain, input_confidence)
                VALUES (%s, %s, 'runtime_brain_adapter', 0.7)
                """,
                (decision_id, f"brain-{decision_id}"),
            )
            conn.execute(
                """
                INSERT INTO brain_output_dependencies (brain_output_id, dependency_type, dependency_id, created_at)
                VALUES (%s, 'signal', %s, now())
                """,
                (f"brain-{decision_id}", f"signal-{decision_id}"),
            )
            if signal_link and market_id:
                conn.execute(
                    "INSERT INTO signal_market_links (signal_id, market_id, link_type, link_status, confidence, reason, created_by) VALUES (%s, %s, 'test', 'confirmed', 0.95, 'test', 'test')",
                    (f"signal-{decision_id}", market_id),
                )
        if orderbook and market_id:
            conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, best_bid, best_ask, spread, source,
                    snapshot_status, is_stale, collected_at, created_at
                )
                VALUES (%s, %s, 0.45, 0.48, 0.03, 'test', 'OK', false, now(), now())
                """,
                (f"book-{decision_id}", market_id),
            )


def test_runtime_coordinator_decision_can_create_complete_thesis(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision()

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["mock_data"] is False
    assert result["coordinator_decisions_checked"] == 1
    assert result["thesis_profiles_created"] == 1
    assert result["complete_thesis_count"] == 1
    assert result["paper_ready_after"] is False
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM thesis_profiles").fetchone()
    assert row["status"] == "COMPLETE"
    assert row["paper_candidate_allowed"] is False


def test_dry_run_coordinator_decision_is_ignored(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision("coord-dry", dry_run=True)

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["coordinator_decisions_checked"] == 0
    assert result["thesis_profiles_created"] == 0


def test_missing_market_id_creates_incomplete_thesis(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision("coord-missing-market", market_id=None, orderbook=False, signal_link=False)

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["thesis_profiles_created"] == 1
    assert result["complete_thesis_count"] == 0
    assert result["incomplete_thesis_count"] == 1
    assert result["missing_market_count"] == 1


def test_missing_orderbook_creates_incomplete_thesis(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision("coord-missing-book", orderbook=False)

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["incomplete_thesis_count"] == 1
    assert result["missing_orderbook_count"] == 1


def test_missing_signal_market_binding_creates_incomplete_thesis(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision("coord-missing-binding", signal_link=False)

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["incomplete_thesis_count"] == 1
    assert result["missing_binding_count"] == 1


def test_no_trade_coordinator_creates_blocked_thesis(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_decision("coord-no-trade", final_state="NO_TRADE")

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    assert result["blocked_thesis_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM thesis_profiles").fetchone()
    assert row["thesis_type"] == "BLOCKED_NO_TRADE_THESIS"
