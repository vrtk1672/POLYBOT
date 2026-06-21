from __future__ import annotations

from decimal import Decimal

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_defense import record_learning_decision

from decision_autopsy_helpers import prepare_autopsy_fixture


def test_defense_20_learning_decision_reprocess_is_idempotent(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    decision = {
        "decision_id": "decision-defense-idempotent",
        "market_id": "market-defense-idempotent",
        "side": "YES",
        "opportunity_score": Decimal("55.46"),
        "blockers_json": [],
        "evidence": {
            "paper_defense": {
                "defense_level": 20,
                "base_threshold": 60,
                "adjusted_threshold": 42,
                "strict_verdict": "BLOCKED",
                "effective_verdict": "ALLOWED_FOR_LEARNING",
                "strict_blockers": ["THESIS_NOT_SUPPORTED"],
                "effective_blockers": [],
                "ignored_blockers": ["THESIS_NOT_SUPPORTED"],
                "softened_blockers": ["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
                "fallback_requirements": ["FALLBACK_LEARNING_EXIT"],
                "exit_plan_type": "FALLBACK_LEARNING",
            }
        },
    }

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        record_learning_decision(conn, decision)
        record_learning_decision(conn, decision)
        row = conn.execute(
            """
            SELECT COUNT(*) AS count,
                   SUM(jsonb_array_length(ignored_blockers_json)) AS ignored,
                   SUM(jsonb_array_length(softened_blockers_json)) AS softened
            FROM paper_learning_ledger
            WHERE runtime_decision_id='decision-defense-idempotent'
            """
        ).fetchone()

    assert int(row["count"]) == 1
    assert int(row["ignored"]) == 1
    assert int(row["softened"]) == 1

