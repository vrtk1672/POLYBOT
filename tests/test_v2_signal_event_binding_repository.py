from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_lineage import SignalLineageService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM source_status")


def test_create_signal_with_producer_source_lineage(postgres_test_schema) -> None:
    _clear()
    created = NeuronSignalService().create_signal_with_lineage(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            market_id="market-bind",
            correlation_id="corr-bind",
            status="ACTIVE",
            raw_direction="neutral",
            raw_payload_ref="rules_analysis:bind",
        ),
        {
            "producer_name": "rules_resolution_adapter",
            "producer_component": "tests",
            "source_name": "rules_resolution_truth",
            "market_id": "market-bind",
            "correlation_id": "corr-bind",
            "raw_payload_ref": "rules_analysis:bind",
            "generated_from": "rules_resolution",
        },
    )

    lineage = SignalLineageService().get_signal_lineage(created["signal_id"])
    assert lineage is not None
    assert lineage["lineage"]["producer_name"] == "rules_resolution_adapter"
    assert lineage["lineage"]["correlation_id"] == "corr-bind"
    assert lineage["lineage"]["raw_payload_ref"] == "rules_analysis:bind"


def test_create_signal_without_event_log_id_still_works(postgres_test_schema) -> None:
    _clear()
    created = NeuronSignalService().create_signal_with_lineage(
        {"neuron": "market", "event_type": "source_status_observed", "status": "ACTIVE"},
        {"producer_name": "source_status_adapter", "generated_from": "source_status"},
    )
    lineage = SignalLineageService().get_signal_lineage(created["signal_id"])
    assert lineage is not None
    assert lineage["lineage"]["event_log_id"] is None


def test_lineage_queries_by_correlation_source_and_producer(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().create_signal_with_lineage(
        {
            "neuron": "orderbook",
            "event_type": "source_status_observed",
            "source_name": "polymarket_clob_orderbook",
            "correlation_id": "corr-clob",
            "status": "ACTIVE",
        },
        {
            "producer_name": "clob_source_status_adapter",
            "producer_component": "tests",
            "source_name": "polymarket_clob_orderbook",
            "correlation_id": "corr-clob",
            "generated_from": "source_status",
        },
    )
    service = SignalLineageService()
    assert len(service.list_signals_by_correlation_id("corr-clob")) == 1
    assert len(service.list_signals_by_source("polymarket_clob_orderbook")) == 1
    assert len(service.list_signals_by_producer("clob_source_status_adapter")) == 1


def test_unbound_and_summary_counts_are_accurate(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().create_signal({"neuron": "market", "event_type": "source_status_observed", "status": "ACTIVE"})
    NeuronSignalService().create_signal_with_lineage(
        {"neuron": "rules", "event_type": "rules_resolution_status_observed", "status": "ACTIVE", "correlation_id": "corr-bound"},
        {"producer_name": "rules_resolution_adapter", "generated_from": "rules_resolution", "correlation_id": "corr-bound"},
    )

    service = SignalLineageService()
    assert len(service.list_unbound_signals()) == 1
    summary = service.get_lineage_summary()
    assert summary["total_signals_24h"] == 2
    assert summary["bound_signals_24h"] == 1
    assert summary["unbound_signals_24h"] == 1
    assert summary["bound_pct_24h"] == 50.0


def test_source_status_adapter_creates_lineage_with_source_status_id(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    source = {
        "source_name": "polymarket_gamma",
        "source_type": "market_discovery",
        "configured": True,
        "key_required": False,
        "key_present": False,
        "key_name": None,
        "endpoint_url": "https://gamma-api.polymarket.com/events",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": True,
        "mutation_allowed": False,
        "latency_ms": 10,
        "details_json": {"sample_market_id": "m1"},
        "notes": "test",
    }
    with factory.connect() as conn, conn.transaction():
        SourceStatusRepository().upsert_status(conn, source)

    NeuronSignalService().record_source_status_signals([source])
    item = SignalLineageService().list_signals_by_source("polymarket_gamma")[0]
    assert item["lineage"]["producer_name"] == "source_status_adapter"
    assert item["lineage"]["source_status_id"] is not None


def test_rules_adapter_creates_lineage(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().record_rules_status_signals(
        [{"market_id": "m-rules", "rules_analysis_id": "ra-rules", "resolution_source_status": "AMBIGUOUS"}]
    )
    item = SignalLineageService().list_signals_by_producer("rules_resolution_adapter")[0]
    assert item["lineage"]["generated_from"] == "rules_resolution"
    assert item["lineage"]["source_event_id"] == "ra-rules"


def test_no_duplicate_binding_for_same_signal(postgres_test_schema) -> None:
    _clear()
    service = NeuronSignalService()
    created = service.create_signal(
        {"neuron": "market", "event_type": "source_status_observed", "status": "ACTIVE"}
    )
    signal_id = created["signal_id"]
    lineage = {
        "signal_id": signal_id,
        "producer_name": "source_status_adapter",
        "generated_from": "source_status",
    }
    service.attach_signal_binding(signal_id, lineage)
    service.attach_signal_binding(signal_id, lineage)
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM neuron_signal_bindings WHERE signal_id = %s",
            [signal_id],
        ).fetchone()["count"]
    assert count == 1


def test_lineage_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    SignalLineageService().get_lineage_summary()
    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
