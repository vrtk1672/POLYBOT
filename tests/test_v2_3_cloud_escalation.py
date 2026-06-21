from __future__ import annotations

from app.ai_brain.budget_governor import AIBudgetDecision
from app.ai_brain.cloud_escalation_worker import CloudEscalationWorker
from app.ai_brain.contracts import AICaseFile, AIRequest, AITaskType
from app.ai_brain.local_ai_worker import AIWorkerResult


def test_cloud_disabled_by_default_and_budget_block_prevents_cloud() -> None:
    worker = CloudEscalationWorker()
    request = AIRequest(task_type=AITaskType.TRAP_PRECHECK, input_payload={"x": 1})
    case_file = AICaseFile(data_completeness_score=95, allowed_for_ai=True)
    disabled = worker.escalate(
        request=request,
        ai_request_id="ai_req_test",
        case_file=case_file,
        budget_decision=AIBudgetDecision(True, cloud_allowed=True, local_allowed=True),
    )
    assert disabled.status == "BLOCKED"
    budget_block = CloudEscalationWorker(enabled=True).escalate(
        request=request,
        ai_request_id="ai_req_test",
        case_file=case_file,
        budget_decision=AIBudgetDecision(True, blocked_reason="budget", cloud_allowed=False, local_allowed=True),
    )
    assert budget_block.status == "BLOCKED"


def test_low_completeness_prevents_cloud() -> None:
    worker = CloudEscalationWorker(enabled=True, client=lambda *_args: {"summary": "cloud"})
    allowed, reason = worker.can_escalate(
        budget_decision=AIBudgetDecision(True, cloud_allowed=True, local_allowed=True),
        local_result=None,
        case_file=AICaseFile(data_completeness_score=40),
    )
    assert allowed is False
    assert reason == "low_data_completeness"


def test_explicit_allowed_mocked_cloud_call_works() -> None:
    worker = CloudEscalationWorker(enabled=True, client=lambda *_args: {"summary": "cloud", "confidence": 0.7, "risk_flags": []})
    result = worker.escalate(
        request=AIRequest(task_type=AITaskType.TRAP_PRECHECK, input_payload={"x": 1}),
        ai_request_id="ai_req_test",
        case_file=AICaseFile(data_completeness_score=95, allowed_for_ai=True),
        budget_decision=AIBudgetDecision(True, cloud_allowed=True, local_allowed=True),
        local_result=AIWorkerResult(status="COMPLETED", confidence=0.2),
    )
    assert result.status == "COMPLETED"
    assert result.output["summary"] == "cloud"
