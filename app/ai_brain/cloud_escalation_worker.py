from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from app.ai_brain.budget_governor import AIBudgetDecision
from app.ai_brain.contracts import AICaseFile, AIRequest
from app.ai_brain.local_ai_worker import AIWorkerResult
from app.ai_brain.redaction import redact_dict, redact_text
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_request_repository import AIRequestRepository


class CloudEscalationWorker:
    def __init__(
        self,
        *,
        enabled: bool = False,
        client: Callable[[AIRequest, AICaseFile], dict[str, Any] | str] | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: AIRequestRepository | None = None,
        target_model: str = "cloud-critical-reasoner",
    ) -> None:
        self.enabled = enabled
        self._client = client
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AIRequestRepository()
        self.target_model = target_model
        self._last_error: str | None = None

    def can_escalate(
        self,
        *,
        budget_decision: AIBudgetDecision,
        local_result: AIWorkerResult | None,
        case_file: AICaseFile | None,
    ) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "cloud_disabled"
        if not budget_decision.cloud_allowed:
            return False, budget_decision.blocked_reason or "budget_blocked_cloud"
        if case_file is not None and case_file.data_completeness_score < 75:
            return False, "low_data_completeness"
        if local_result is not None and local_result.confidence is not None and local_result.confidence >= 0.65:
            return False, "local_confidence_sufficient"
        return True, None

    def escalate(
        self,
        *,
        request: AIRequest,
        ai_request_id: str,
        case_file: AICaseFile,
        budget_decision: AIBudgetDecision,
        local_result: AIWorkerResult | None = None,
    ) -> AIWorkerResult:
        allowed, reason = self.can_escalate(budget_decision=budget_decision, local_result=local_result, case_file=case_file)
        escalation_id = f"ai_esc_{uuid4().hex}"
        self._log_escalation(
            escalation_id=escalation_id,
            ai_request_id=ai_request_id,
            request=request,
            reason=reason or "approved",
            allowed=allowed,
            status="APPROVED" if allowed else "BLOCKED",
            local_confidence=local_result.confidence if local_result else None,
        )
        if not allowed:
            return AIWorkerResult(status="BLOCKED", error_message=reason)
        if self._client is None:
            self._last_error = "cloud client unavailable"
            return AIWorkerResult(status="UNAVAILABLE", error_message=self._last_error)
        try:
            result = self._client(request, case_file)
            parsed = json.loads(result) if isinstance(result, str) else dict(result)
        except Exception:
            self._last_error = "cloud ai call failed"
            self._log_escalation(
                escalation_id=f"ai_esc_{uuid4().hex}",
                ai_request_id=ai_request_id,
                request=request,
                reason="cloud call failed",
                allowed=True,
                status="FAILED",
                local_confidence=local_result.confidence if local_result else None,
            )
            return AIWorkerResult(status="FAILED", error_message=self._last_error)
        output = redact_dict(parsed)
        return AIWorkerResult(
            status="COMPLETED",
            output=output,
            confidence=float(output.get("confidence", 0.0)) if output.get("confidence") is not None else None,
            risk_flags=[str(item) for item in output.get("risk_flags", [])] if isinstance(output.get("risk_flags"), list) else [],
            raw_output_redacted=redact_text(json.dumps(output, sort_keys=True, default=str)),
        )

    def health(self) -> dict[str, Any]:
        return {"cloud_enabled": self.enabled, "status": "AVAILABLE" if self.enabled and self._client else "DISABLED", "last_error": self._last_error}

    def _log_escalation(
        self,
        *,
        escalation_id: str,
        ai_request_id: str,
        request: AIRequest,
        reason: str,
        allowed: bool,
        status: str,
        local_confidence: float | None,
    ) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn:
            self._repository.insert_escalation(
                conn,
                escalation_id=escalation_id,
                ai_request_id=ai_request_id,
                market_id=request.market_id,
                task_type=request.task_type.value,
                from_model=None,
                to_model=self.target_model,
                reason=reason,
                local_confidence=local_confidence,
                escalation_allowed=allowed,
                status=status,
            )
            conn.commit()
