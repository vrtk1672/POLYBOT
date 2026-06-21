from __future__ import annotations

from datetime import UTC, datetime

from app.neural_mesh.producer_health import ProducerHealth, ProducerHealthSummary


def test_producer_health_contract_serializes_runtime_truth() -> None:
    item = ProducerHealth(
        producer_name="rules_resolution_adapter",
        neuron_name="rules",
        registered=True,
        expected=True,
        observed=True,
        signal_count=3,
        runtime_signal_count=3,
        recent_signal_count=2,
        health_status="healthy",
        health_reason="Runtime Signals are recent.",
        runtime_active=True,
        can_feed_brain=True,
        can_feed_paper=False,
        evidence={"runtime_signal_count": 3},
        last_seen_at=datetime.now(UTC),
    )

    payload = item.to_api_dict()
    assert payload["producer_name"] == "rules_resolution_adapter"
    assert payload["health_status"] == "HEALTHY"
    assert payload["runtime_active"] is True
    assert payload["can_feed_paper"] is False


def test_producer_health_summary_keeps_paper_ready_false() -> None:
    item = ProducerHealth(
        producer_name="dry_run_context",
        health_status="DRY_RUN_ONLY",
        health_reason="Only dry-run evidence observed.",
        observed=True,
        dry_run_only=True,
        can_feed_paper=False,
    )
    summary = ProducerHealthSummary(
        mock_data=False,
        overall_status="degraded",
        paper_ready=False,
        total_producers=1,
        observed_producers=1,
        dry_run_only_producers=1,
        dry_run_only_neurons=["dry_run_context"],
        producer_health=[item],
        neuron_runtime_truth={"dry_run_only": ["dry_run_context"]},
        last_updated=datetime.now(UTC),
    )

    payload = summary.to_api_dict()
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["overall_status"] == "DEGRADED"
    assert payload["dry_run_only_producers"] == 1
