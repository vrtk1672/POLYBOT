from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.candidate_eligibility_recovery import CandidateEligibilityRecoveryService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.side_evidence import DeterministicSideEvidenceService
from app.services.system_power import SystemPowerService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain


def test_recovered_side_can_be_consumed_by_candidate_eligibility_and_intent_gate(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    ids = seed_paper_eligibility_chain("side-consume", side=None)
    SystemPowerService().turn_on(actor="test", reason="side_to_eligibility")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE markets_v2
            SET yes_token_id = 'yes-token',
                no_token_id = 'no-token',
                outcome_tokens_json = %s
            WHERE market_id = %s
            """,
            (Jsonb({"yes": "yes-token", "no": "no-token"}), ids["market_id"]),
        )
        conn.execute(
            """
            UPDATE neuron_signals
            SET evidence_json = %s
            WHERE signal_id = %s
            """,
            (Jsonb({"details": {"sample_token_id": "yes-token"}, "generated_by": "runtime", "is_runtime_generated": True}), ids["signal_id"]),
        )

    blocked = PaperEligibilityService().evaluate_candidates(limit=10)
    assert blocked["eligible_count"] == 0

    side = DeterministicSideEvidenceService().run_recovery(cycle_id="side-consume", limit=10)
    recovered = CandidateEligibilityRecoveryService().run_recovery(cycle_id="side-consume-eligibility", limit=10)

    assert side["sides_recovered"] == 1
    assert recovered["eligible_after"] >= 1
    assert recovered["paper_intents_after"] >= 1
    assert recovered["live_orders_delta"] == 0
    assert recovered["real_orders_delta"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        candidate = conn.execute("SELECT status, side FROM paper_eligibility_candidates ORDER BY id DESC LIMIT 1").fetchone()
        intent = conn.execute("SELECT side, live, execution_allowed, order_intent_created FROM paper_intents ORDER BY id DESC LIMIT 1").fetchone()
    assert candidate["status"] == "ELIGIBLE"
    assert candidate["side"] == "YES"
    assert intent["side"] == "YES"
    assert intent["live"] is False
    assert intent["execution_allowed"] is False
    assert intent["order_intent_created"] is False
