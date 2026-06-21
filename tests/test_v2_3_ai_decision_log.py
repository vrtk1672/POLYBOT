from __future__ import annotations

from app.ai_brain.contracts import AIRequest, AIResponse, AITaskType
from app.ai_brain.decision_log import AIDecisionLog
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_ai_decision_logged_with_risk_flags_and_no_order_intent(postgres_test_schema) -> None:
    run_migrations()
    request = AIRequest(task_type=AITaskType.RULES_SUMMARY, market_id="m1", input_payload={"rules": "text"})
    response = AIResponse(
        ai_request_id="ai_req_test",
        task_type=AITaskType.RULES_SUMMARY,
        model_name="qwen3:14b",
        structured_output={"summary": "uncertain"},
        confidence=0.4,
        risk_flags=["wording_risk"],
    )
    decision_id = AIDecisionLog().log_decision(request=request, response=response, ai_request_id="ai_req_test")
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM ai_decision_logs WHERE ai_decision_id = %s", (decision_id,)).fetchone()
        order_events = conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type='order.intent.created'").fetchone()
    assert row["risk_flags_json"] == ["wording_risk"]
    assert row["cannot_trade_reason"]
    assert order_events["count"] == 0
