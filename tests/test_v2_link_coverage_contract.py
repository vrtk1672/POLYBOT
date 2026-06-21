from __future__ import annotations

from app.services.link_coverage import LinkCoverageService


def _service() -> LinkCoverageService:
    return LinkCoverageService()


def _context(**overrides):
    base = {
        "signal_id": "link-coverage-contract",
        "neuron": "rules",
        "event_type": "rules_resolution_status_observed",
        "source_name": "rules_resolution_truth",
        "binding_source_name": "rules_resolution_truth",
        "producer_name": "rules_resolution_adapter",
        "generated_from": "rules_resolution",
        "market_id": None,
        "signal_status": "ACTIVE",
        "evidence_json": {"resolution_status": "clear"},
        "raw_payload_ref": "rules:contract",
        "binding_raw_payload_ref": "rules:contract",
        "entity_count": 0,
        "evidence_count": 1,
        "linked_to_market": False,
        "linked_to_position": False,
        "has_signal_entity": False,
        "has_event_entity": False,
        "quality_is_dry_run_generated": False,
        "quality_is_runtime_generated": True,
        "quality_is_stale": False,
        "quality_can_feed_brain": True,
        "quality_can_feed_paper": False,
        "signal_created_at": None,
        "stale_after_seconds": None,
        "expires_at": None,
    }
    base.update(overrides)
    return base


class _Repo:
    def __init__(self, *, market_exists: bool = False, candidate=None) -> None:
        self._market_exists = market_exists
        self._candidate = candidate

    def market_exists(self, _conn, _market_id: str) -> bool:
        return self._market_exists

    def find_entity_market_candidate(self, _conn, _signal_id: str):
        return self._candidate


def test_already_linked_signal_gets_linked_status() -> None:
    service = _service()
    service._repository = _Repo()

    analysis = service._analyze_context(None, _context(linked_to_market=True))

    assert analysis.linkability_status == "LINKED"
    assert analysis.primary_unlinked_reason == "ALREADY_LINKED"
    assert analysis.suggested_link_action == "NONE"


def test_unlinked_signal_missing_market_and_entity_is_not_linkable() -> None:
    service = _service()
    service._repository = _Repo()

    analysis = service._analyze_context(None, _context())

    assert analysis.linkability_status == "NOT_LINKABLE"
    assert analysis.primary_unlinked_reason == "MISSING_ENTITY"
    assert "MISSING_MARKET_ID" in analysis.missing_fields
    assert "MISSING_ENTITY" in analysis.unlinked_reasons


def test_stale_signal_is_blocked_from_linking() -> None:
    service = _service()
    service._repository = _Repo(market_exists=True)

    analysis = service._analyze_context(None, _context(market_id="m1", quality_is_stale=True))

    assert analysis.linkability_status == "STALE"
    assert analysis.suggested_link_action == "BLOCKED_STALE"
    assert analysis.can_auto_link is False


def test_dry_run_only_signal_is_blocked_from_production_linking() -> None:
    service = _service()
    service._repository = _Repo(market_exists=True)

    analysis = service._analyze_context(None, _context(market_id="m1", quality_is_dry_run_generated=True, quality_is_runtime_generated=False))

    assert analysis.linkability_status == "DRY_RUN_ONLY"
    assert analysis.suggested_link_action == "BLOCKED_DRY_RUN_ONLY"
    assert analysis.can_auto_link is False


def test_explicit_existing_market_id_creates_safe_candidate() -> None:
    service = _service()
    service._repository = _Repo(market_exists=True)

    analysis = service._analyze_context(None, _context(market_id="m1"))

    assert analysis.linkability_status == "LINKABLE"
    assert analysis.suggested_market_id == "m1"
    assert analysis.suggested_market_confidence == 0.95
    assert analysis.suggested_link_action == "SAFE_TO_LINK_EXISTING_MARKET_ID"
    assert analysis.can_auto_link is True


def test_weak_matcher_evidence_is_blocked() -> None:
    service = _service()
    service._repository = _Repo(candidate={"market_id": "m2", "confidence": 0.4, "entity_id": "entity-low"})

    analysis = service._analyze_context(None, _context(has_signal_entity=True))

    assert analysis.linkability_status == "NEEDS_MORE_EVIDENCE"
    assert analysis.primary_unlinked_reason == "WEAK_MATCHER_EVIDENCE"
    assert analysis.suggested_link_action == "BLOCKED_WEAK_EVIDENCE"


def test_no_matcher_is_reported() -> None:
    service = _service()
    service._repository = _Repo(candidate=None)

    analysis = service._analyze_context(None, _context(has_signal_entity=True))

    assert analysis.linkability_status == "NEEDS_MORE_EVIDENCE"
    assert analysis.primary_unlinked_reason == "NO_MATCHER_AVAILABLE"
    assert analysis.suggested_link_action == "BLOCKED_NO_MATCHER"
