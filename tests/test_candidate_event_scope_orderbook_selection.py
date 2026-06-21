from __future__ import annotations

from app.control_center.candidate_event_correlation import _candidate_token
from app.services.trade_opportunity_score import score_actionability_item
from tests_support_strict_actionability import qualified_actionability_item


def test_valid_candidate_scoped_event_clears_candidate_event_scope_blocker() -> None:
    score = score_actionability_item(qualified_actionability_item())

    assert "candidate_event_scope_not_actionable" not in score["hard_blockers"]
    assert score["candidate_event_scope"] == "CANDIDATE_SCOPED"
    assert score["candidate_event_link_state"] == "LINKED_TO_CANDIDATE"
    assert score["token_side_match"] is True


def test_market_level_event_does_not_clear_candidate_scope() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            candidate_event_scope="MARKET_SCOPED_ONLY",
            candidate_event_actionability_scope="MARKET_SCOPED_ONLY",
            candidate_event_link_state="MARKET_LEVEL_ONLY_WITH_REASON",
        )
    )

    assert "candidate_event_scope_not_actionable" in score["hard_blockers"]
    assert "missing_candidate_event_link" in score["hard_blockers"]


def test_token_side_mismatch_remains_hard_blocker() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            candidate_event_scope="NOT_ACTIONABLE",
            candidate_event_actionability_scope="NOT_ACTIONABLE",
            candidate_event_link_state="TOKEN_SIDE_MISMATCH",
        )
    )

    assert "candidate_event_scope_not_actionable" in score["hard_blockers"]
    assert "token_side_mismatch" in score["hard_blockers"]
    assert score["token_side_match"] is False


def test_fresh_candidate_orderbook_clears_stale_orderbook_blocker() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            candidate_trusted_orderbook_state="TRUSTED_FRESH_FOR_CANDIDATE",
            candidate_price_path_state="CANDIDATE_PRICE_READY",
            selected_orderbook_snapshot_id="ob-fresh",
        )
    )

    assert "stale_orderbook" not in score["hard_blockers"]
    assert score["orderbook_freshness_state"] == "TRUSTED_FRESH_FOR_CANDIDATE"
    assert score["selected_orderbook_snapshot_id"] == "ob-fresh"


def test_stale_candidate_orderbook_remains_hard_blocker() -> None:
    score = score_actionability_item(
        qualified_actionability_item(
            candidate_trusted_orderbook_state="TRUSTED_STALE_FOR_CANDIDATE",
            candidate_price_path_state="CANDIDATE_STALE_ORDERBOOK",
        )
    )

    assert "stale_orderbook" in score["hard_blockers"]


def test_candidate_token_uses_trusted_link_before_market_fallback() -> None:
    assert (
        _candidate_token(
            {
                "side": "YES",
                "expected_token_id": None,
                "trusted_expected_token_id": "trusted-yes",
                "trusted_orderbook_token_id": "trusted-ob",
                "yes_token_id": "market-yes",
            }
        )
        == "trusted-yes"
    )


def test_candidate_token_uses_market_side_when_candidate_column_missing() -> None:
    assert (
        _candidate_token(
            {
                "side": "NO",
                "expected_token_id": None,
                "trusted_expected_token_id": None,
                "trusted_orderbook_token_id": None,
                "yes_token_id": "market-yes",
                "no_token_id": "market-no",
            }
        )
        == "market-no"
    )
