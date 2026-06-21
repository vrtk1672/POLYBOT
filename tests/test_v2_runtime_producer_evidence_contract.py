from __future__ import annotations

import pytest

from app.neural_mesh.runtime_producer_evidence import RuntimeProducerEvidenceItem, RuntimeProducerEvidenceRun


def test_runtime_evidence_item_requires_runtime_non_dry_run_metadata() -> None:
    item = RuntimeProducerEvidenceItem(
        producer_name="source_status_adapter",
        source="polymarket_gamma",
        correlation_id="corr-1",
        raw_payload_ref="source_status:1:polymarket_gamma",
        generated_from="source_status",
    )

    assert item.generated_by == "runtime"
    assert item.is_runtime_generated is True
    assert item.is_dry_run_generated is False


def test_runtime_evidence_item_rejects_dry_run_marker() -> None:
    with pytest.raises(ValueError):
        RuntimeProducerEvidenceItem(
            producer_name="source_status_adapter",
            source="polymarket_gamma",
            correlation_id="corr-1",
            raw_payload_ref="source_status:1:polymarket_gamma",
            is_runtime_generated=False,
            is_dry_run_generated=True,
        )


def test_runtime_evidence_run_cannot_claim_paper_ready_or_execution() -> None:
    with pytest.raises(ValueError):
        RuntimeProducerEvidenceRun(run_id="run-bad", paper_ready_after=True)

    with pytest.raises(ValueError):
        RuntimeProducerEvidenceRun(run_id="run-bad-orders", orders_created=1)
