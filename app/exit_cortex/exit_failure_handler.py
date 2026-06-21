from __future__ import annotations

from app.exit_cortex.contracts import ExitFailure


class ExitFailureHandler:
    def failure(self, *, plan, failure_type: str, reason: str, details: dict | None = None, severity: str = "BLOCKING") -> ExitFailure:
        return ExitFailure(exit_plan_id=plan.exit_plan_id if plan else None, order_id=plan.order_id if plan else None, market_id=plan.market_id if plan else None, failure_type=failure_type, severity=severity, reason=reason, recoverable=True, details=details or {})

