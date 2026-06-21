from __future__ import annotations

from app.strategy.contracts import EngineRejection


class EngineRejectionBuilder:
    def build(self, engine: str, reasons: list[str], *, hard: bool = False, severity: str | None = None) -> EngineRejection:
        reason = reasons[0] if reasons else "engine_rejected"
        return EngineRejection(
            engine=engine,
            rejection_reason=reason,
            severity=severity or ("BLOCKING" if hard else "WARNING"),
            source_type="strategy_engine",
            hard_block=hard,
            explanation="; ".join(reasons) if reasons else reason,
        )

