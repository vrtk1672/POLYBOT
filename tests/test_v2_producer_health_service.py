from __future__ import annotations

from datetime import UTC, datetime

from app.services.producer_health import build_producer_health_summary


def _registered() -> list[dict[str, object]]:
    return [
        {"producer_name": "silent_adapter", "neuron_name": "rules", "enabled": True, "expected_signal_types": ["rules_resolution_status_observed"], "is_required_for_paper": True},
        {"producer_name": "runtime_adapter", "neuron_name": "market", "enabled": True, "expected_signal_types": ["source_status_observed"], "is_required_for_paper": True},
    ]


def _registry_neurons() -> list[dict[str, object]]:
    return [
        {"neuron_name": "rules", "enabled": True, "expected_signal_types": ["rules_resolution_status_observed"], "is_required_for_paper": True},
        {"neuron_name": "market", "enabled": True, "expected_signal_types": ["source_status_observed"], "is_required_for_paper": True},
        {"neuron_name": "exit", "enabled": True, "expected_signal_types": [], "is_required_for_paper": True},
    ]


def _observed(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    row: dict[str, object] = {
        "producer_name": "runtime_adapter",
        "neuron_name": "market",
        "signal_count": 3,
        "runtime_signal_count": 3,
        "dry_run_signal_count": 0,
        "recent_signal_count": 2,
        "stale_signal_count": 0,
        "lineage_complete_count": 3,
        "lineage_unbound_count": 0,
        "avg_quality_score": 0.82,
        "brain_signal_count": 2,
        "paper_signal_count": 0,
        "first_seen_at": now,
        "last_seen_at": now,
    }
    row.update(overrides)
    return row


def _by_producer(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["producer_name"]): item for item in payload["producer_health"]}  # type: ignore[index]


def test_registered_expected_producer_with_no_signals_is_silent() -> None:
    payload = build_producer_health_summary(_registered(), [_observed()], [], _registry_neurons()).to_api_dict()

    silent = _by_producer(payload)["silent_adapter"]
    assert silent["health_status"] == "SILENT"
    assert silent["silent_expected"] is True
    assert "rules" in payload["silent_expected_neurons"]


def test_observed_runtime_recent_producer_is_healthy() -> None:
    payload = build_producer_health_summary(_registered(), [_observed()], [], _registry_neurons()).to_api_dict()

    item = _by_producer(payload)["runtime_adapter"]
    assert item["health_status"] == "HEALTHY"
    assert item["runtime_active"] is True
    assert payload["runtime_active_producers"] == 1


def test_dry_run_only_producer_cannot_feed_paper() -> None:
    payload = build_producer_health_summary(
        [],
        [_observed(producer_name="dry_adapter", runtime_signal_count=0, dry_run_signal_count=4, recent_signal_count=0)],
        [{"producer_name": "dry_adapter", "brain_output_count": 1, "coordinator_decision_count": 1, "dry_run_output_count": 2}],
        [],
    ).to_api_dict()

    item = _by_producer(payload)["dry_adapter"]
    assert item["health_status"] == "DRY_RUN_ONLY"
    assert item["dry_run_only"] is True
    assert item["can_feed_paper"] is False


def test_stale_only_producer_is_degraded() -> None:
    payload = build_producer_health_summary([], [_observed(producer_name="stale_adapter", stale_signal_count=3)], [], []).to_api_dict()

    item = _by_producer(payload)["stale_adapter"]
    assert item["health_status"] == "DEGRADED"
    assert item["health_reason"] == "STALE_OUTPUT_HIGH"


def test_incomplete_lineage_producer_is_degraded() -> None:
    payload = build_producer_health_summary([], [_observed(producer_name="lineage_adapter", lineage_unbound_count=1)], [], []).to_api_dict()

    item = _by_producer(payload)["lineage_adapter"]
    assert item["health_status"] == "DEGRADED"
    assert item["health_reason"] == "LINEAGE_INCOMPLETE"


def test_low_quality_producer_is_degraded() -> None:
    payload = build_producer_health_summary([], [_observed(producer_name="weak_adapter", avg_quality_score=0.42)], [], []).to_api_dict()

    item = _by_producer(payload)["weak_adapter"]
    assert item["health_status"] == "DEGRADED"
    assert item["health_reason"] == "QUALITY_LOW"


def test_unregistered_observed_producer_is_reported() -> None:
    payload = build_producer_health_summary([], [_observed(producer_name="external_adapter")], [], []).to_api_dict()

    item = _by_producer(payload)["external_adapter"]
    assert item["registered"] is False
    assert item["observed"] is True
    assert item["health_status"] == "HEALTHY"


def test_unknown_producer_is_unknown_and_not_paper_eligible() -> None:
    payload = build_producer_health_summary([], [_observed(producer_name="")], [], []).to_api_dict()

    item = _by_producer(payload)["unknown"]
    assert item["health_status"] == "UNKNOWN"
    assert item["can_feed_paper"] is False
