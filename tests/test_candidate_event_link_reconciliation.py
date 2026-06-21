from __future__ import annotations

from app.control_center.paper_actionability import _reconcile_strict_actionability

from tests_support_strict_actionability import qualified_actionability_item


def test_missing_candidate_event_link_blocks_strict_actionability() -> None:
    item = qualified_actionability_item(
        candidate_event_scope="NOT_ACTIONABLE",
        candidate_event_actionability_scope="NOT_ACTIONABLE",
        candidate_event_link_state="STALE_CANDIDATE_LINK",
        blockers=["MISSING_CANDIDATE_EVENT_LINK"],
    )

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_EVENT_SCOPE"
    assert reconciled["would_require_paper_simulation_on"] is False


def test_token_side_mismatch_blocks_strict_actionability() -> None:
    item = qualified_actionability_item(candidate_event_link_state="TOKEN_SIDE_MISMATCH")

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH"
    assert "TOKEN_SIDE_MISMATCH" in reconciled["blockers"]


def test_market_level_event_cannot_satisfy_candidate_actionability() -> None:
    item = qualified_actionability_item(
        candidate_event_scope="MARKET_SCOPED_ONLY",
        candidate_event_actionability_scope="MARKET_SCOPED_ONLY",
        candidate_event_link_state="MARKET_LEVEL_ONLY_WITH_REASON",
    )

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_EVENT_SCOPE"
