from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.same_market_arbitration import SameMarketSideArbitrator

from decision_autopsy_helpers import prepare_autopsy_fixture


def test_arbitration_autopsy_exposes_latest_conflicts(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("UPDATE paper_sessions SET defense_level=20")
        SameMarketSideArbitrator().arbitrate(
            [_decision("market-autopsy", "YES", 64.0), _decision("market-autopsy", "NO", 61.0)],
            conn=conn,
        )

    payload = SameMarketSideArbitrator().dashboard_summary(limit=5)

    assert payload["status"] == "OK"
    assert payload["counts"]["total_conflicts"] >= 1
    assert payload["counts"]["resolved_conflicts"] >= 1
    latest = payload["items"][0]
    assert latest["market_id"] == "market-autopsy"
    assert latest["selected_side"] == "YES"
    assert latest["rejected_side"] == "NO"


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
        "evidence": {"orderbook_age_seconds": 5, "orderbook_ttl_seconds": 60},
    }
