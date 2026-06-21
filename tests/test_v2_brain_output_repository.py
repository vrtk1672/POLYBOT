from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_outputs import BrainOutputService
from app.services.neuron_signals import NeuronSignalService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _signal() -> dict[str, object]:
    return NeuronSignalService().create_signal(
        {
            "neuron": "rules",
            "event_type": "rules_resolution_status_observed",
            "market_id": "market-brain",
            "status": "ACTIVE",
            "raw_direction": "neutral",
        }
    )


def test_brain_output_persists_with_signal_dependency(postgres_test_schema) -> None:
    _clear()
    signal = _signal()
    created = BrainOutputService().create_brain_output_with_dependencies(
        {
            "brain": "context",
            "output_type": "WATCH",
            "market_id": "market-brain",
            "recommendation": "WATCH",
            "confidence": 0.7,
            "urgency": 0.2,
            "status": "ACTIVE",
            "risk_flags": ["resolution_ambiguous"],
        },
        dependencies=[
            {
                "dependency_type": "signal",
                "dependency_id": str(signal["signal_id"]),
                "dependency_role": "primary_evidence",
                "confidence": 1.0,
            }
        ],
    )

    assert created["brain_output_id"].startswith("brain_output_")
    assert created["dependencies"][0]["dependency_id"] == signal["signal_id"]
    fetched = BrainOutputService().get_brain_output(created["brain_output_id"])
    assert fetched is not None
    assert fetched["dependencies"][0]["dependency_type"] == "signal"


def test_reject_missing_signal_dependency_reference(postgres_test_schema) -> None:
    _clear()

    with pytest.raises(ValueError, match="signal dependency does not exist"):
        BrainOutputService().create_brain_output_with_dependencies(
            {"brain": "risk", "output_type": "RISK_WARNING", "recommendation": "CAUTION", "status": "ACTIVE"},
            dependencies=[{"dependency_type": "signal", "dependency_id": "signal_missing"}],
        )


def test_list_outputs_by_market_brain_and_signal_dependency(postgres_test_schema) -> None:
    _clear()
    signal = _signal()
    service = BrainOutputService()
    service.create_brain_output_with_dependencies(
        {
            "brain": "context",
            "output_type": "INTERPRETATION",
            "market_id": "market-brain",
            "recommendation": "WATCH",
            "status": "ACTIVE",
        },
        dependencies=[{"dependency_type": "signal", "dependency_id": str(signal["signal_id"])}],
    )

    assert len(service.list_outputs_by_market("market-brain")) == 1
    assert len(service.list_outputs_by_brain("context")) == 1
    assert len(service.list_outputs_by_signal_dependency(str(signal["signal_id"]))) == 1


def test_conflict_records_can_be_created_and_validated(postgres_test_schema) -> None:
    _clear()
    signal = _signal()
    service = BrainOutputService()
    created = service.create_brain_output_with_dependencies(
        {
            "brain": "no_trade",
            "output_type": "NO_TRADE_HINT",
            "recommendation": "CAUTION",
            "status": "ACTIVE",
        },
        conflicts=[
            {
                "conflicts_with_type": "signal",
                "conflicts_with_id": str(signal["signal_id"]),
                "conflict_type": "source_disagreement",
                "conflict_severity": 0.5,
            }
        ],
    )

    fetched = service.get_brain_output(created["brain_output_id"])
    assert fetched is not None
    assert fetched["conflicts"][0]["conflict_type"] == "source_disagreement"

    with pytest.raises(ValueError, match="signal conflict target does not exist"):
        service.add_conflict(
            created["brain_output_id"],
            {
                "conflicts_with_type": "signal",
                "conflicts_with_id": "signal_missing",
                "conflict_type": "missing_target",
                "conflict_severity": 0.2,
            },
        )


def test_summary_counts_outputs_dependencies_conflicts(postgres_test_schema) -> None:
    _clear()
    signal = _signal()
    service = BrainOutputService()
    service.create_brain_output_with_dependencies(
        {"brain": "context", "output_type": "WATCH", "recommendation": "WATCH", "status": "ACTIVE"},
        dependencies=[{"dependency_type": "signal", "dependency_id": str(signal["signal_id"])}],
    )
    service.create_brain_output({"brain": "memory", "output_type": "MEMORY_NOTE", "recommendation": "WATCH", "status": "EXPIRED"})

    summary = service.get_brain_output_summary()
    assert summary["mock_data"] is False
    assert summary["total_outputs_24h"] == 2
    assert summary["active_outputs"] == 1
    assert summary["expired_outputs"] == 1
    assert summary["outputs_without_dependencies"] == 1
    assert summary["signals_with_outputs"] == 1


def test_brain_output_store_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    BrainOutputService().create_brain_output(
        {"brain": "ai", "output_type": "AI_ANALYSIS", "recommendation": "WATCH", "status": "ACTIVE"}
    )

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
