"""
V2 Neural Mesh Part 4C-H: Consolidated Mesh Truth Regression Suite.

Validates the full 4C safety/truth chain using pure-Python contract tests:
- Signal Quality (items 1-8)
- Link Coverage contract (items 5-8)
- Lineage Coverage (items 9-12)
- Dry Run Provenance (items 13-17)
- Mesh Blockers contract (items 18-22)
- Producer Health contract (items 23-27)

DB-backed tests are in test_v2_4c_regression_safety.py.
Dashboard tests are in test_v2_4c_dashboard_readiness_regression.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.neural_mesh.mesh_blockers import MeshBlocker, MeshBlockerReport
from app.neural_mesh.producer_health import ProducerHealth, ProducerHealthSummary
from app.services.dry_run_provenance import classify_provenance
from app.services.lineage_coverage import analyze_lineage_context
from app.services.signal_quality import evaluate_signal_context


# ---------------------------------------------------------------------------
# Shared context builder helpers
# ---------------------------------------------------------------------------

def _quality_context(**overrides):
    base = {
        "signal_id": "regression-truth",
        "status": "ACTIVE",
        "source_name": "rules_resolution_truth",
        "binding_source_name": "rules_resolution_truth",
        "correlation_id": "corr-regression",
        "binding_correlation_id": "corr-regression",
        "raw_payload_ref": "rules:regression",
        "binding_raw_payload_ref": "rules:regression",
        "market_id": "regression-market",
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
        "used_by_brain_output": False,
        "used_by_coordinator": False,
        "has_evidence_rows": False,
        "has_non_dry_run_market_link": True,
    }
    base.update(overrides)
    return base


def _lineage_context(**overrides):
    now = datetime.now(UTC)
    base = {
        "signal_id": "regression-lineage",
        "source_name": "rules_resolution_truth",
        "correlation_id": "corr-lineage",
        "raw_payload_ref": "rules:lineage",
        "evidence_json": {"resolution_status": "clear"},
        "signal_created_at": now,
        "binding_id": 1,
        "producer_name": "rules_resolution_adapter",
        "binding_source_name": "rules_resolution_truth",
        "binding_correlation_id": "corr-lineage-binding",
        "binding_raw_payload_ref": "rules:lineage-binding",
        "generated_from": "rules_resolution",
        "lineage_json": {"raw_payload_policy": "reference_only"},
        "binding_created_at": now,
        "event_log_id": None,
        "source_event_id": "evt-regression",
        "source_status_id": None,
        "quality_is_dry_run_generated": False,
        "quality_is_runtime_generated": True,
        "quality_is_stale": False,
    }
    base.update(overrides)
    return base


# ===========================================================================
# Signal Quality — tests 1-4
# ===========================================================================

def test_quality_score_is_deterministic() -> None:
    """Test 1: Same context always produces the same score."""
    ctx = _quality_context()
    r1 = evaluate_signal_context(ctx)
    r2 = evaluate_signal_context(ctx)
    assert r1.quality_score == r2.quality_score
    assert r1.quality_status == r2.quality_status


def test_quality_status_matches_expected_thresholds() -> None:
    """Test 2: Full-metadata signal is GOOD with high score."""
    result = evaluate_signal_context(_quality_context())
    assert result.quality_status == "GOOD"
    assert result.quality_score >= 0.8


def test_stale_signal_cannot_feed_paper() -> None:
    """Test 3: Stale signal blocks Paper readiness."""
    ctx = _quality_context(
        created_at=datetime.now(UTC) - timedelta(hours=3),
        stale_after_seconds=60,
    )
    result = evaluate_signal_context(ctx)
    assert result.quality_status == "STALE"
    assert result.is_stale is True
    assert result.can_feed_brain is False
    assert result.can_feed_paper is False


def test_missing_required_fields_reduce_readiness() -> None:
    """Test 4: Missing source + lineage + market reduces readiness substantially."""
    ctx = _quality_context(
        source_name=None,
        binding_source_name=None,
        has_binding=False,
        market_id=None,
        linked_to_market=False,
        has_non_dry_run_market_link=False,
        evidence_json={},
        has_evidence_rows=False,
    )
    result = evaluate_signal_context(ctx)
    assert result.quality_score < 0.6
    assert result.can_feed_paper is False


# ===========================================================================
# Market / Link readiness — tests 5-8
# ===========================================================================

def test_signal_without_market_id_cannot_become_paper_ready() -> None:
    """Test 5: No market_id means can_feed_paper=False and market_id in missing_fields."""
    result = evaluate_signal_context(
        _quality_context(market_id=None, linked_to_market=False, has_non_dry_run_market_link=False)
    )
    assert "market_id" in result.missing_fields
    assert result.can_feed_paper is False


def test_signal_without_market_link_remains_blocked() -> None:
    """Test 6: No market link means quality_status=UNLINKED and can_feed_paper=False."""
    result = evaluate_signal_context(
        _quality_context(linked_to_market=False, has_non_dry_run_market_link=False)
    )
    assert result.quality_status == "UNLINKED"
    assert result.can_feed_paper is False


def test_suggested_links_do_not_mutate_actual_links_by_default() -> None:
    """Test 8: Dry-run signals produce BLOCKED suggested link actions, not applied links."""
    from app.neural_mesh.link_coverage import SignalLinkCoverageAnalysis
    analysis = SignalLinkCoverageAnalysis(
        signal_id="regression-dry-run",
        linkability_status="DRY_RUN_ONLY",
        primary_unlinked_reason="DRY_RUN_ONLY",
        suggested_link_action="BLOCKED_DRY_RUN_ONLY",
        can_auto_link=False,
    )
    assert analysis.can_auto_link is False
    assert analysis.suggested_link_action == "BLOCKED_DRY_RUN_ONLY"


def test_unlinked_reason_is_captured_in_analysis() -> None:
    """Test 7: Unlinked reason field is always present and valid."""
    from app.neural_mesh.link_coverage import SignalLinkCoverageAnalysis

    for reason in ("MISSING_MARKET_ID", "MISSING_ENTITY", "STALE_SIGNAL", "DRY_RUN_ONLY", "NO_MATCHER_AVAILABLE"):
        analysis = SignalLinkCoverageAnalysis(
            signal_id="regression-unlinked",
            linkability_status="NOT_LINKABLE",
            primary_unlinked_reason=reason,
            suggested_link_action="NONE",
            can_auto_link=False,
        )
        assert analysis.primary_unlinked_reason == reason


# ===========================================================================
# Lineage Coverage — tests 9-12
# ===========================================================================

def test_signal_without_producer_is_weak_and_blocked() -> None:
    """Test 9: Missing producer makes lineage unbound."""
    result = analyze_lineage_context(_lineage_context(producer_name=None))
    assert result.primary_unbound_reason == "MISSING_PRODUCER"
    assert result.can_feed_paper_by_lineage is False


def test_missing_lineage_fields_are_reported() -> None:
    """Test 10: Each missing lineage field is recorded individually."""
    result = analyze_lineage_context(
        _lineage_context(correlation_id=None, binding_correlation_id=None)
    )
    assert "MISSING_CORRELATION_ID" in result.missing_lineage_fields


def test_dry_run_lineage_does_not_count_as_paper_evidence() -> None:
    """Test 11: Dry-run lineage is blocked from Paper regardless of completeness."""
    result = analyze_lineage_context(
        _lineage_context(
            producer_name="mesh_dry_run",
            quality_is_dry_run_generated=True,
            quality_is_runtime_generated=False,
            evidence_json={"generated_by": "mesh_dry_run"},
        )
    )
    assert result.lineage_status == "DRY_RUN_ONLY"
    assert result.can_feed_paper_by_lineage is False


def test_runtime_lineage_improves_trust_but_does_not_flip_paper_ready() -> None:
    """Test 12: High-trust lineage is informational only; does not set global paper_ready."""
    result = analyze_lineage_context(_lineage_context())
    assert result.lineage_trust_score >= 0.85
    assert result.can_feed_paper_by_lineage is True
    assert 0.0 <= result.lineage_trust_score <= 1.0


# ===========================================================================
# Dry Run Provenance — tests 13-17
# ===========================================================================

def test_brain_output_dry_run_is_marked_dry_run_only() -> None:
    """Test 13: Brain Output with generated_by=dry_run gets DRY_RUN_ONLY status."""
    analysis = classify_provenance({
        "object_type": "BRAIN_OUTPUT",
        "object_id": "regression-bo-1",
        "generated_by": "mesh_dry_run",
        "producer_name": "risk",
    })
    assert analysis.provenance_status == "DRY_RUN_ONLY"
    assert analysis.is_dry_run_generated is True
    assert analysis.can_feed_paper_by_provenance is False


def test_coordinator_decision_with_dry_run_id_is_marked_dry_run_only() -> None:
    """Test 14: Coordinator Decision with dry_run_id gets DRY_RUN_ONLY status."""
    analysis = classify_provenance({
        "object_type": "COORDINATOR_DECISION",
        "object_id": "regression-coord-1",
        "dry_run_id": "dry_run_regression",
    })
    assert analysis.provenance_status == "DRY_RUN_ONLY"
    assert analysis.is_dry_run_generated is True
    assert analysis.can_feed_paper_by_provenance is False


def test_dry_run_evidence_is_blocked_from_paper() -> None:
    """Test 17: Any dry-run provenance cannot feed Paper evidence."""
    for obj_type in ("BRAIN_OUTPUT", "COORDINATOR_DECISION", "SIGNAL"):
        analysis = classify_provenance({
            "object_type": obj_type,
            "object_id": f"regression-{obj_type.lower()}",
            "generated_by": "dry_run",
        })
        assert analysis.can_feed_paper_by_provenance is False, (
            f"{obj_type} with dry_run provenance must not feed Paper"
        )


def test_unknown_provenance_also_blocked_from_paper() -> None:
    """Test 17b: Unknown provenance cannot feed Paper (conservative blocking)."""
    analysis = classify_provenance({
        "object_type": "BRAIN_OUTPUT",
        "object_id": "regression-unknown",
    })
    assert analysis.provenance_status == "UNKNOWN"
    assert analysis.can_feed_paper_by_provenance is False


def test_dry_run_provenance_confidence_is_high_when_explicit() -> None:
    """Test 13b: Explicit dry_run metadata produces high confidence classification."""
    analysis = classify_provenance({
        "object_type": "BRAIN_OUTPUT",
        "object_id": "regression-explicit-dry-run",
        "generated_by": "mesh_dry_run",
        "producer_name": "rules",
    })
    assert analysis.provenance_confidence >= 0.9


# ===========================================================================
# Mesh Blockers — tests 18-22
# ===========================================================================

def test_paper_ready_false_when_critical_blockers_exist() -> None:
    """Test 18: Report with CRITICAL active blockers must have paper_ready=False."""
    blocker = MeshBlocker(
        code="NO_EXIT_FOUNDATION",
        active=True,
        severity="CRITICAL",
        category="EXIT",
        reason="No Exit Foundation exists.",
        evidence={"exit_foundation_present": False},
        source="exit_foundation_audit",
        recommended_next_step="Build Exit Foundation before enabling Paper.",
        blocks_paper=True,
    )
    report = MeshBlockerReport(
        mock_data=False,
        paper_ready=False,
        overall_status="BLOCKED",
        blocked_by=[blocker.code],
        blockers=[blocker],
        info=[],
        counts={"critical": 1, "active_blockers": 1},
        last_updated=datetime.now(UTC),
    )
    payload = report.to_api_dict()
    assert payload["paper_ready"] is False
    assert payload["overall_status"] == "BLOCKED"


def test_blocked_by_contains_dry_run_brain_and_coordinator_blockers() -> None:
    """Test 19: Dry-run-only Brain/Coordinator blockers appear in blocked_by."""
    brain_blocker = MeshBlocker(
        code="BRAIN_OUTPUTS_DRY_RUN_ONLY",
        active=True,
        severity="CRITICAL",
        category="BRAIN",
        reason="Brain Outputs are dry-run-only.",
        evidence={"brain_outputs_runtime": 0, "brain_outputs_dry_run": 48},
        source="dry_run_provenance",
        recommended_next_step="Implement runtime brain producer adapters.",
        blocks_paper=True,
    )
    coord_blocker = MeshBlocker(
        code="COORDINATOR_DECISIONS_DRY_RUN_ONLY",
        active=True,
        severity="CRITICAL",
        category="COORDINATOR",
        reason="Coordinator Decisions are dry-run-only.",
        evidence={"coordinator_runtime": 0, "coordinator_dry_run": 12},
        source="dry_run_provenance",
        recommended_next_step="Enable runtime coordinator cycle.",
        blocks_paper=True,
    )
    report = MeshBlockerReport(
        mock_data=False,
        paper_ready=False,
        overall_status="BLOCKED",
        blocked_by=[brain_blocker.code, coord_blocker.code],
        blockers=[brain_blocker, coord_blocker],
        info=[],
        counts={"critical": 2, "active_blockers": 2},
        last_updated=datetime.now(UTC),
    )
    payload = report.to_api_dict()
    assert "BRAIN_OUTPUTS_DRY_RUN_ONLY" in payload["blocked_by"]
    assert "COORDINATOR_DECISIONS_DRY_RUN_ONLY" in payload["blocked_by"]


def test_blocker_evidence_is_present_and_not_empty() -> None:
    """Test 21: Every active blocker must have non-empty evidence."""
    for code, evidence in (
        ("BRAIN_OUTPUTS_DRY_RUN_ONLY", {"brain_outputs_runtime": 0}),
        ("NO_EXIT_FOUNDATION", {"exit_foundation_present": False}),
        ("SIGNAL_LINKING_TOO_LOW", {"link_coverage_pct": 0.14}),
    ):
        blocker = MeshBlocker(
            code=code,
            active=True,
            severity="CRITICAL",
            category="BRAIN",
            reason="test",
            evidence=evidence,
            source="test_source",
            recommended_next_step="test",
            blocks_paper=True,
        )
        payload = blocker.to_api_dict()
        assert payload["evidence"], f"Blocker {code} must have non-empty evidence"


def test_live_disabled_is_info_not_readiness_failure() -> None:
    """Test 22: LIVE_DISABLED blocker has severity INFO and does not block Paper alone."""
    blocker = MeshBlocker(
        code="LIVE_DISABLED",
        active=True,
        severity="INFO",
        category="RUNTIME",
        reason="Live trading is disabled by default. This is expected.",
        evidence={"live_trading_enabled": False},
        source="runtime_config",
        recommended_next_step="No action needed; live trading requires explicit certification.",
        blocks_paper=False,
    )
    payload = blocker.to_api_dict()
    assert payload["severity"] == "INFO"
    assert payload["blocks_paper"] is False


# ===========================================================================
# Producer Health — tests 23-27
# ===========================================================================

def test_dry_run_only_producers_are_detected() -> None:
    """Test 23: A producer with only dry-run signals has health_status=DRY_RUN_ONLY."""
    item = ProducerHealth(
        producer_name="dry_run_adapter",
        neuron_name="dry_run_context",
        registered=True,
        expected=False,
        observed=True,
        signal_count=5,
        runtime_signal_count=0,
        dry_run_signal_count=5,
        health_status="DRY_RUN_ONLY",
        health_reason="Only dry-run Signals observed.",
        dry_run_only=True,
        runtime_active=False,
        can_feed_brain=True,
        can_feed_paper=False,
        evidence={"dry_run_signal_count": 5, "runtime_signal_count": 0},
    )
    payload = item.to_api_dict()
    assert payload["health_status"] == "DRY_RUN_ONLY"
    assert payload["dry_run_only"] is True
    assert payload["runtime_active"] is False
    assert payload["can_feed_paper"] is False


def test_silent_expected_neurons_are_detected() -> None:
    """Test 24: A registered expected producer with zero signals has silent_expected=True."""
    item = ProducerHealth(
        producer_name="whale_scanner",
        neuron_name="whale",
        registered=True,
        expected=True,
        observed=False,
        signal_count=0,
        health_status="SILENT",
        health_reason="Expected producer has emitted no Signals.",
        silent_expected=True,
        runtime_active=False,
        can_feed_brain=False,
        can_feed_paper=False,
        evidence={"signal_count": 0},
    )
    payload = item.to_api_dict()
    assert payload["health_status"] == "SILENT"
    assert payload["silent_expected"] is True
    assert payload["can_feed_paper"] is False


def test_degraded_producers_are_detected() -> None:
    """Test 25: A producer with stale signals and low quality is DEGRADED."""
    item = ProducerHealth(
        producer_name="news_adapter",
        neuron_name="news",
        registered=True,
        expected=True,
        observed=True,
        signal_count=10,
        runtime_signal_count=2,
        stale_signal_count=8,
        avg_quality_score=0.35,
        health_status="DEGRADED",
        health_reason="Majority of Signals are stale; quality below threshold.",
        degraded=True,
        runtime_active=False,
        can_feed_brain=False,
        can_feed_paper=False,
        evidence={"stale_signal_count": 8, "avg_quality_score": 0.35},
    )
    payload = item.to_api_dict()
    assert payload["health_status"] == "DEGRADED"
    assert payload["degraded"] is True
    assert payload["can_feed_paper"] is False


def test_producer_health_never_flips_paper_ready() -> None:
    """Test 27: ProducerHealthSummary must always have paper_ready=False."""
    for status in ("HEALTHY", "DEGRADED", "DRY_RUN_ONLY", "SILENT", "MISSING"):
        item = ProducerHealth(
            producer_name="test_producer",
            health_status=status,
            health_reason="test",
            can_feed_paper=False,
        )
        summary = ProducerHealthSummary(
            mock_data=False,
            overall_status=status,
            paper_ready=False,
            total_producers=1,
            producer_health=[item],
            neuron_runtime_truth={},
            last_updated=datetime.now(UTC),
        )
        assert summary.to_api_dict()["paper_ready"] is False, (
            f"paper_ready must be False for status={status}"
        )


def test_runtime_active_producers_count_matches_evidence() -> None:
    """Test 26: runtime_active_producers in summary matches actual runtime_active producers."""
    active = ProducerHealth(
        producer_name="runtime_producer",
        health_status="HEALTHY",
        health_reason="Runtime Signals are recent.",
        runtime_active=True,
        can_feed_paper=False,
    )
    dry_run = ProducerHealth(
        producer_name="dry_run_producer",
        health_status="DRY_RUN_ONLY",
        health_reason="Only dry-run.",
        dry_run_only=True,
        can_feed_paper=False,
    )
    summary = ProducerHealthSummary(
        mock_data=False,
        overall_status="DEGRADED",
        paper_ready=False,
        total_producers=2,
        runtime_active_producers=1,
        dry_run_only_producers=1,
        producer_health=[active, dry_run],
        neuron_runtime_truth={"runtime_active": ["runtime_producer"], "dry_run_only": ["dry_run_producer"]},
        last_updated=datetime.now(UTC),
    )
    payload = summary.to_api_dict()
    assert payload["runtime_active_producers"] == 1
    assert payload["dry_run_only_producers"] == 1
    assert payload["paper_ready"] is False
