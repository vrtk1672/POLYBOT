from __future__ import annotations

from app.services.dry_run_provenance import classify_provenance


def test_explicit_generated_by_dry_run_becomes_dry_run_only() -> None:
    analysis = classify_provenance({"object_type": "BRAIN_OUTPUT", "object_id": "bo1", "generated_by": "mesh_dry_run", "producer_name": "risk"})

    assert analysis.generated_by == "dry_run"
    assert analysis.provenance_status == "DRY_RUN_ONLY"
    assert analysis.can_feed_paper_by_provenance is False


def test_explicit_dry_run_id_becomes_dry_run_only() -> None:
    analysis = classify_provenance({"object_type": "COORDINATOR_DECISION", "object_id": "coord1", "dry_run_id": "dry_1"})

    assert analysis.provenance_status == "DRY_RUN_ONLY"
    assert analysis.is_dry_run_generated is True


def test_generated_by_runtime_becomes_runtime_verified() -> None:
    analysis = classify_provenance({"object_type": "SIGNAL", "object_id": "sig1", "generated_by": "runtime", "producer_name": "rules"})

    assert analysis.generated_by == "runtime"
    assert analysis.provenance_status == "RUNTIME_VERIFIED"
    assert analysis.can_feed_brain_by_provenance is True


def test_generated_by_adapter_becomes_adapter_generated() -> None:
    analysis = classify_provenance({"object_type": "SIGNAL", "object_id": "sig2", "generated_by": "adapter", "producer_name": "rules_adapter"})

    assert analysis.generated_by == "adapter"
    assert analysis.provenance_status == "ADAPTER_GENERATED"


def test_generated_by_manual_becomes_manual_generated() -> None:
    analysis = classify_provenance({"object_type": "SIGNAL", "object_id": "sig3", "generated_by": "manual"})

    assert analysis.generated_by == "manual"
    assert analysis.provenance_status == "MANUAL_GENERATED"


def test_missing_provenance_becomes_unknown() -> None:
    analysis = classify_provenance({"object_type": "BRAIN_OUTPUT", "object_id": "bo-unknown"})

    assert analysis.generated_by == "unknown"
    assert analysis.provenance_status == "UNKNOWN"
    assert analysis.can_feed_paper_by_provenance is False


def test_mixed_runtime_and_dry_run_is_mixed_low_confidence() -> None:
    analysis = classify_provenance(
        {
            "object_type": "SIGNAL",
            "object_id": "sig-mixed",
            "generated_by": "runtime",
            "metadata_json": {"generated_by": "mesh_dry_run"},
        }
    )

    assert analysis.provenance_status == "MIXED"
    assert analysis.provenance_confidence == 0.4
