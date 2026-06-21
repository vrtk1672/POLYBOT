from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.signal_quality import SignalQualityEvaluation
from app.repositories.signal_quality_repository import SignalQualityRepository
from app.services.link_coverage import LinkCoverageService
from app.services.neuron_signals import NeuronSignalService


def _prepare(*, dry_run: bool = False, stale: bool = False) -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM markets_v2")
        conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES ('safety-market', 'Will safety market resolve?', 'safety-market')")
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="safety-link-signal",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="mesh_dry_run" if dry_run else "rules_resolution_truth",
            status="STALE" if stale else "ACTIVE",
            market_id="safety-market",
            confidence=0.8,
            strength=0.8,
            evidence={"generated_by": "mesh_dry_run"} if dry_run else {"resolution_status": "clear"},
            raw_payload_ref="rules:safety",
        )
    )
    if dry_run or stale:
        with DatabaseConnectionFactory().connect() as conn, conn.transaction():
            SignalQualityRepository().upsert_evaluation(
                conn,
                SignalQualityEvaluation(
                    signal_id=str(signal["signal_id"]),
                    quality_score=0.6,
                    quality_status="STALE" if stale else "DRY_RUN_ONLY",
                    missing_fields=["production_market_link"],
                    readiness_reason="blocked evidence",
                    can_feed_brain=not stale,
                    can_feed_paper=False,
                    has_market_id=True,
                    has_source=True,
                    has_evidence=True,
                    is_dry_run_generated=dry_run,
                    is_runtime_generated=not dry_run,
                    is_stale=stale,
                ),
            )
    return signal


def test_stale_suggestion_is_not_applied_even_when_apply_requested(postgres_test_schema) -> None:
    signal = _prepare(stale=True)

    result = LinkCoverageService().analyze_signal(str(signal["signal_id"]), create_suggestions=True, apply_safe_links=True)

    assert result is not None
    assert result["suggested_link_action"] == "BLOCKED_STALE"
    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
    assert links == 0


def test_dry_run_suggestion_is_not_applied_even_when_apply_requested(postgres_test_schema) -> None:
    signal = _prepare(dry_run=True)

    result = LinkCoverageService().analyze_signal(str(signal["signal_id"]), create_suggestions=True, apply_safe_links=True)

    assert result is not None
    assert result["suggested_link_action"] == "BLOCKED_DRY_RUN_ONLY"
    with DatabaseConnectionFactory().connect() as conn:
        links = conn.execute("SELECT COUNT(*) AS count FROM signal_market_links").fetchone()["count"]
    assert links == 0


def test_link_coverage_does_not_create_orders_or_enable_paper(postgres_test_schema) -> None:
    signal = _prepare()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = _safety_counts(conn)

    LinkCoverageService().analyze_signal(str(signal["signal_id"]), create_suggestions=True, apply_safe_links=False)

    with factory.connect() as conn:
        after = _safety_counts(conn)
    assert after == before


def _safety_counts(conn) -> dict[str, int]:
    return {
        "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
        "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
        "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        "order_intents": _table_count(conn, "order_intents"),
        "execution_allowed": int(conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"]),
    }


def _table_count(conn, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
