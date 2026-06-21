from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def test_signal_repository_persists_and_lists_signals(postgres_test_schema) -> None:
    _clear()
    service = NeuronSignalService()

    service.create_signal(
        NeuronSignal(
            neuron="market",
            event_type="source_status_observed",
            source_name="polymarket_gamma",
            status="ACTIVE",
            raw_direction="neutral",
            market_id="market-a",
            confidence=1.0,
            evidence={"runtime_status": "ACTIVE"},
        )
    )
    service.create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="DEGRADED",
            raw_direction="neutral",
            market_id="market-b",
            confidence=0.55,
            stale_after_seconds=0,
            evidence={"resolution_source_status": "AMBIGUOUS"},
        )
    )

    recent = service.list_recent_signals(limit=10)
    assert len(recent) == 2
    assert all(item["signal_id"].startswith("signal_") for item in recent)

    by_market = service.list_market_signals("market-a")
    assert len(by_market) == 1
    assert by_market[0]["neuron"] == "market"

    by_neuron = service.list_neuron_signals("rules")
    assert len(by_neuron) == 1
    assert by_neuron[0]["market_id"] == "market-b"


def test_signal_summary_counts_stale_and_unprocessed(postgres_test_schema) -> None:
    _clear()
    service = NeuronSignalService()
    created = service.create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="STALE",
            market_id="market-stale",
            raw_direction="neutral",
            evidence={"resolution_source_status": "MISSING"},
        )
    )

    summary = service.get_signal_summary(limit=10)
    assert summary["total_signals_24h"] == 1
    assert summary["signals_per_minute"] >= 0
    assert summary["unprocessed_signals"] == 1
    assert len(summary["stale_signals"]) == 1

    service.mark_processed(created["signal_id"])
    summary = service.get_signal_summary(limit=10)
    assert summary["unprocessed_signals"] == 0


def test_signal_store_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
        }

    NeuronSignalService().create_signal(
        NeuronSignal(neuron="ai", event_type="source_status_observed", status="DISABLED")
    )

    with factory.connect() as conn:
        after = {
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
        }

    assert after == before
