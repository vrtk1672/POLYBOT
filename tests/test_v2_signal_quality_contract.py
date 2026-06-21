from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.signal_quality import evaluate_signal_context


def _context(**overrides):
    base = {
        "signal_id": "signal_quality_contract",
        "status": "ACTIVE",
        "source_name": "rules_resolution_truth",
        "binding_source_name": "rules_resolution_truth",
        "correlation_id": "corr_contract",
        "binding_correlation_id": "corr_contract",
        "raw_payload_ref": "rules:1",
        "binding_raw_payload_ref": "rules:1",
        "market_id": "market-contract",
        "confidence": 0.9,
        "strength": 0.8,
        "freshness_seconds": 0,
        "stale_after_seconds": 3600,
        "expires_at": None,
        "created_at": datetime.now(UTC),
        "evidence_json": {"resolution_status": "clear"},
        "evidence_count": 0,
        "has_binding": True,
        "producer_name": "rules_resolution_adapter",
        "generated_from": "rules_resolution",
        "linked_to_market": True,
        "linked_to_position": False,
        "used_by_brain_output": True,
        "used_by_coordinator": True,
        "has_evidence_rows": False,
        "has_non_dry_run_market_link": True,
    }
    base.update(overrides)
    return base


def test_full_metadata_signal_is_good_and_high_score() -> None:
    evaluation = evaluate_signal_context(_context())

    assert evaluation.quality_status == "GOOD"
    assert evaluation.quality_score >= 0.8
    assert evaluation.can_feed_brain is True
    assert evaluation.can_feed_paper is True


def test_signal_without_market_id_gets_missing_field() -> None:
    evaluation = evaluate_signal_context(_context(market_id=None, linked_to_market=False, has_non_dry_run_market_link=False))

    assert "market_id" in evaluation.missing_fields
    assert evaluation.can_feed_paper is False


def test_signal_without_lineage_is_capped_and_cannot_feed_paper() -> None:
    evaluation = evaluate_signal_context(_context(has_binding=False))

    assert evaluation.quality_status == "UNBOUND"
    assert evaluation.quality_score <= 0.6
    assert evaluation.can_feed_paper is False


def test_signal_without_market_link_cannot_feed_paper() -> None:
    evaluation = evaluate_signal_context(_context(linked_to_market=False, has_non_dry_run_market_link=False))

    assert evaluation.quality_status == "UNLINKED"
    assert evaluation.quality_score <= 0.65
    assert "linked_to_market" in evaluation.missing_fields
    assert evaluation.can_feed_paper is False


def test_signal_without_evidence_cannot_feed_paper() -> None:
    evaluation = evaluate_signal_context(_context(evidence_json={}, has_evidence_rows=False))

    assert "evidence" in evaluation.missing_fields
    assert evaluation.quality_score <= 0.75
    assert evaluation.can_feed_paper is False


def test_stale_signal_gets_stale_status_and_penalty() -> None:
    evaluation = evaluate_signal_context(
        _context(created_at=datetime.now(UTC) - timedelta(hours=2), stale_after_seconds=60)
    )

    assert evaluation.quality_status == "STALE"
    assert evaluation.is_stale is True
    assert evaluation.can_feed_brain is False
    assert evaluation.can_feed_paper is False


def test_dry_run_generated_signal_is_capped_and_cannot_feed_paper() -> None:
    evaluation = evaluate_signal_context(_context(source_name="mesh_dry_run", generated_from="mesh_dry_run", producer_name="mesh_dry_run"))

    assert evaluation.quality_status == "DRY_RUN_ONLY"
    assert evaluation.quality_score <= 0.7
    assert evaluation.is_dry_run_generated is True
    assert evaluation.can_feed_paper is False


def test_runtime_signal_can_feed_brain_with_enough_quality() -> None:
    evaluation = evaluate_signal_context(_context(linked_to_market=False, has_non_dry_run_market_link=False))

    assert evaluation.is_runtime_generated is True
    assert evaluation.can_feed_brain is True
    assert evaluation.can_feed_paper is False


def test_quality_score_clamps_between_zero_and_one() -> None:
    evaluation = evaluate_signal_context(
        _context(
            status="STALE",
            source_name=None,
            binding_source_name=None,
            has_binding=False,
            market_id=None,
            linked_to_market=False,
            has_non_dry_run_market_link=False,
            evidence_json={},
            confidence=None,
            strength=None,
            freshness_seconds=None,
            stale_after_seconds=None,
        )
    )

    assert 0.0 <= evaluation.quality_score <= 1.0
