from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.decision_autopsy import DecisionAutopsyService

from decision_autopsy_helpers import SESSION_ID, prepare_autopsy_fixture, seed_runtime_decision


def test_enter_without_intent_with_expected_skip_is_not_bug_suspect(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-expected-skip",
        market_id="market-skip",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            f"""
            INSERT INTO no_trade_log (
                no_trade_id, market_id, side, candidate_engine, source_layer,
                source_record_id, decision_status, primary_reason, reasons_json,
                risk_flags_json, decision_confidence, data_confidence,
                insufficient_data, insufficient_data_reasons_json, explanation,
                eligibility_id, no_trade_reason, no_trade_category, blockers,
                missing_requirements, evidence, source_status, generated_by,
                producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                'no_trade_decision-expected-skip_{SESSION_ID}','market-skip','YES',
                'PAPER_INTENT_GATE','paper_intent_gate','decision-expected-skip',
                'NO_TRADE','DUPLICATE_OPEN_PAPER_EXPOSURE',
                '["DUPLICATE_OPEN_PAPER_EXPOSURE"]'::jsonb,'[]'::jsonb,0,0,
                false,'[]'::jsonb,'duplicate current session exposure',
                'decision-expected-skip','DUPLICATE_OPEN_PAPER_EXPOSURE',
                'ELIGIBILITY_BLOCKED','["DUPLICATE_OPEN_PAPER_EXPOSURE"]'::jsonb,
                '[]'::jsonb,%s,'ELIGIBLE','runtime','no_trade_ledger',
                true,false
            )
            """,
            (Jsonb({"paper_runtime_decision_id": "decision-expected-skip", "paper_session_id": SESSION_ID, "duplicate_scope": "CURRENT_SESSION"}),),
        )

    item = DecisionAutopsyService().enter_autopsy()["items"][0]

    assert item["runtime_decision_id"] == "decision-expected-skip"
    assert item["is_bug_suspect"] is False
    assert item["intent_gate_evaluation"]["intent_skip_reason"] == "DUPLICATE_OPEN_PAPER_EXPOSURE"
    assert item["intent_gate_evaluation"]["duplicate_scope"] == "CURRENT_SESSION"
