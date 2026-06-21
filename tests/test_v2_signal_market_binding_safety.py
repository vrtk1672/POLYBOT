from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_market_binding import SignalMarketBindingRecoveryService


def test_binding_recovery_creates_no_executable_artifacts(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("signal_market_binding_candidates", "signal_market_binding_recovery_runs", "signal_market_links", "neuron_signals", "markets_v2"):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
        conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES ('safe-market', 'Safe market?', 'safe-market')")
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="safe-signal",
            neuron="market",
            event_type="source_status_observed",
            source_name="polymarket_gamma",
            market_id="safe-market",
            confidence=0.8,
            strength=0.7,
            evidence={"generated_by": "runtime", "is_runtime_generated": True},
            raw_payload_ref="safe:payload",
            status="ACTIVE",
        )
    )

    result = SignalMarketBindingRecoveryService().recover_market_bindings(limit=10, apply_safe_links=True)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        paper_orders = conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]
        order_intents_exists = conn.execute("SELECT to_regclass('order_intents') AS table_name").fetchone()["table_name"]
    assert paper_orders == 0
    assert order_intents_exists is None

