from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.same_market_arbitration import SameMarketSideArbitrator

from decision_autopsy_helpers import prepare_autopsy_fixture


def test_arbitration_details_are_recorded(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("UPDATE paper_sessions SET defense_level=20")
        decisions = [_decision("market-ledger", "YES", 64.0), _decision("market-ledger", "NO", 61.0)]

        SameMarketSideArbitrator().arbitrate(decisions, conn=conn)

        row = conn.execute(
            """
            SELECT market_id, defense_level, selected_side, rejected_side,
                   outcome, yes_arbitration_score, no_arbitration_score
            FROM same_market_side_arbitrations
            WHERE market_id='market-ledger'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row["defense_level"] == 20
    assert row["selected_side"] == "YES"
    assert row["rejected_side"] == "NO"
    assert row["outcome"] == "ARBITRATION_SELECTED_YES"
    assert row["yes_arbitration_score"] > row["no_arbitration_score"]


def _decision(market_id: str, side: str, score: float) -> dict:
    return {
        "decision_id": f"decision-{market_id}-{side}",
        "market_id": market_id,
        "side": side,
        "token_id": f"token-{market_id}-{side}",
        "decision": "ENTER",
        "paper_enter_allowed": True,
        "opportunity_score": score,
        "edge_state": "EDGE_SUPPORTED",
        "thesis_state": "THESIS_SUPPORTED",
        "exit_state": "EXIT_READY",
        "orderbook_state": "FRESH",
        "blockers_json": [],
        "warnings_json": [],
        "required_to_pass_json": [],
        "policy_json": {},
        "evidence": {
            "orderbook_age_seconds": 5,
            "orderbook_ttl_seconds": 60,
            "orderbook_best_bid": 0.40,
            "orderbook_best_ask": 0.42,
        },
    }
