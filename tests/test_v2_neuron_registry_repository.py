from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_registry import NeuronRegistryService
from app.services.neuron_signals import NeuronSignalService


def _clear_mesh() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM neuron_health")
        conn.execute("DELETE FROM source_status")


def test_default_neurons_are_seeded(postgres_test_schema) -> None:
    _clear_mesh()
    service = NeuronRegistryService()

    service.ensure_default_neurons()
    neurons = service.list_neurons()
    names = {item["neuron_name"] for item in neurons}

    assert {"market", "orderbook", "rules", "resolution", "news", "social", "whale", "ai"} <= names
    assert len(neurons) >= 15


def test_disabled_neuron_reports_disabled(postgres_test_schema) -> None:
    _clear_mesh()
    service = NeuronRegistryService()

    news = service.get_neuron("news")

    assert news is not None
    assert news["registry"]["enabled"] is False
    assert news["health"]["health_status"] == "DISABLED"


def test_recent_signal_reports_active_and_counts(postgres_test_schema) -> None:
    _clear_mesh()
    NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="ACTIVE",
            market_id="market-registry",
            raw_direction="neutral",
        )
    )

    rules = NeuronRegistryService().get_neuron("rules")

    assert rules is not None
    assert rules["health"]["health_status"] == "ACTIVE"
    assert rules["stats"]["signals_24h"] == 1
    assert rules["stats"]["last_signal_at"] is not None


def test_old_signal_reports_stale(postgres_test_schema) -> None:
    _clear_mesh()
    NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="market",
            event_type="source_status_observed",
            status="ACTIVE",
            raw_direction="neutral",
            created_at=datetime.now(UTC) - timedelta(hours=2),
            stale_after_seconds=60,
        )
    )

    market = NeuronRegistryService().get_neuron("market")

    assert market is not None
    assert market["health"]["health_status"] == "STALE"
    assert market["health"]["is_stale"] is True


def test_missing_expected_neuron_reports_missing(postgres_test_schema) -> None:
    _clear_mesh()

    liquidity = NeuronRegistryService().get_neuron("liquidity")

    assert liquidity is not None
    assert liquidity["health"]["health_status"] == "MISSING"


def test_neuron_registry_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear_mesh()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    NeuronRegistryService().get_neuron_mesh_summary()

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
