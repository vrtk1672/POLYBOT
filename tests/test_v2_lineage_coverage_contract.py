from __future__ import annotations

from datetime import UTC, datetime

from app.services.lineage_coverage import analyze_lineage_context


def _context(**overrides):
    now = datetime.now(UTC)
    base = {
        "signal_id": "lineage-contract",
        "source_name": "rules_resolution_truth",
        "correlation_id": "corr-signal",
        "raw_payload_ref": "rules:signal",
        "evidence_json": {"resolution_status": "clear"},
        "signal_created_at": now,
        "binding_id": 1,
        "producer_name": "rules_resolution_adapter",
        "binding_source_name": "rules_resolution_truth",
        "binding_correlation_id": "corr-binding",
        "binding_raw_payload_ref": "rules:binding",
        "generated_from": "rules_resolution",
        "lineage_json": {"raw_payload_policy": "reference_only"},
        "binding_created_at": now,
        "event_log_id": None,
        "source_event_id": "evt-1",
        "source_status_id": None,
        "quality_is_dry_run_generated": False,
        "quality_is_runtime_generated": True,
        "quality_is_stale": False,
    }
    base.update(overrides)
    return base


def test_complete_runtime_lineage_becomes_runtime_verified() -> None:
    analysis = analyze_lineage_context(_context())

    assert analysis.lineage_status in {"COMPLETE", "RUNTIME_VERIFIED"}
    assert analysis.lineage_trust_score >= 0.85
    assert analysis.is_bound is True
    assert analysis.can_feed_brain_by_lineage is True
    assert analysis.can_feed_paper_by_lineage is True


def test_missing_producer_returns_missing_producer() -> None:
    analysis = analyze_lineage_context(_context(producer_name=None))

    assert analysis.primary_unbound_reason == "MISSING_PRODUCER"
    assert "MISSING_PRODUCER" in analysis.missing_lineage_fields
    assert analysis.can_feed_paper_by_lineage is False


def test_missing_source_returns_missing_source() -> None:
    analysis = analyze_lineage_context(_context(source_name=None, binding_source_name=None))

    assert analysis.primary_unbound_reason == "MISSING_SOURCE"
    assert "MISSING_SOURCE" in analysis.missing_lineage_fields


def test_missing_correlation_id_returns_missing_correlation_id() -> None:
    analysis = analyze_lineage_context(_context(correlation_id=None, binding_correlation_id=None))

    assert analysis.primary_unbound_reason == "MISSING_CORRELATION_ID"
    assert "MISSING_CORRELATION_ID" in analysis.missing_lineage_fields


def test_missing_raw_payload_ref_returns_missing_raw_payload_ref() -> None:
    analysis = analyze_lineage_context(_context(raw_payload_ref=None, binding_raw_payload_ref=None))

    assert analysis.primary_unbound_reason == "MISSING_RAW_PAYLOAD_REF"
    assert "MISSING_RAW_PAYLOAD_REF" in analysis.missing_lineage_fields


def test_missing_generated_from_returns_missing_generated_from() -> None:
    analysis = analyze_lineage_context(_context(generated_from=None))

    assert analysis.primary_unbound_reason == "MISSING_GENERATED_FROM"
    assert "MISSING_GENERATED_FROM" in analysis.missing_lineage_fields


def test_dry_run_only_lineage_is_blocked_from_paper_evidence() -> None:
    analysis = analyze_lineage_context(
        _context(
            producer_name="mesh_dry_run",
            quality_is_dry_run_generated=True,
            quality_is_runtime_generated=False,
            evidence_json={"generated_by": "mesh_dry_run"},
        )
    )

    assert analysis.lineage_status == "DRY_RUN_ONLY"
    assert analysis.primary_unbound_reason == "DRY_RUN_ONLY"
    assert analysis.can_feed_paper_by_lineage is False


def test_unknown_origin_becomes_stale_or_unknown_or_unbound() -> None:
    analysis = analyze_lineage_context(
        _context(
            binding_id=None,
            producer_name=None,
            source_name=None,
            binding_source_name=None,
            generated_from=None,
            raw_payload_ref=None,
            binding_raw_payload_ref=None,
            event_log_id=None,
            source_event_id=None,
            source_status_id=None,
        )
    )

    assert analysis.lineage_status in {"UNBOUND", "STALE_OR_UNKNOWN"}
    assert analysis.primary_unbound_reason in {"UNKNOWN_ORIGIN", "MISSING_PRODUCER"}


def test_trust_score_is_clamped() -> None:
    analysis = analyze_lineage_context(_context(quality_is_dry_run_generated=True, quality_is_runtime_generated=True))

    assert 0.0 <= analysis.lineage_trust_score <= 1.0
