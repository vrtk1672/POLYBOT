from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.repositories.signal_market_binding_repository import SignalMarketBindingRepository
from app.services.neuron_signals import NeuronSignalService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "signal_market_binding_candidates",
            "signal_market_binding_recovery_runs",
            "signal_suggested_market_links",
            "signal_link_coverage_analysis",
            "signal_market_links",
            "signal_position_links",
            "signal_quality_evaluations",
            "signal_processing_states",
            "neuron_signal_bindings",
            "neuron_signals",
            "markets_v2",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")


def test_repository_persists_link_evidence(postgres_test_schema) -> None:
    _prepare()
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="repo-signal",
            neuron="market",
            event_type="source_status_observed",
            source_name="polymarket_gamma",
            market_id="repo-market",
            confidence=0.8,
            strength=0.7,
            evidence={"generated_by": "runtime", "is_runtime_generated": True},
            raw_payload_ref="repo:payload",
            status="ACTIVE",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES ('repo-market', 'Repo market?', 'repo-market')")
        created = SignalMarketBindingRepository().apply_link(
            conn,
            signal_id="repo-signal",
            market_id="repo-market",
            confidence=0.95,
            reason="repo evidence",
            evidence={"method": "explicit_market_id"},
            method="explicit_market_id",
            runtime_link=True,
        )
        row = conn.execute("SELECT * FROM signal_market_links WHERE signal_id='repo-signal'").fetchone()

    assert created is True
    assert row["link_confidence"] == row["confidence"]
    assert row["link_evidence_json"]["method"] == "explicit_market_id"
    assert row["is_auto_linked"] is True
    assert row["is_runtime_link"] is True

