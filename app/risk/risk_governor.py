from __future__ import annotations

from typing import Any

from app.risk.contracts import RiskBreach
from app.risk.attack_mode_gate import AttackModeGate
from app.risk.contracts import RiskGovernorState
from app.risk.risk_breach_detector import RiskBreachDetector
from app.risk.risk_limit_manager import RiskLimitManager


class RiskGovernor:
    def __init__(self) -> None:
        self.limits = RiskLimitManager()
        self.detector = RiskBreachDetector()
        self.attack_gate = AttackModeGate()

    def rebuild(self, *, runtime_mode: str | None = None, payload: dict[str, Any] | None = None) -> RiskGovernorState:
        payload = payload or {}
        limits = self.limits.as_dict()
        state = RiskGovernorState(
            runtime_mode=runtime_mode or payload.get("runtime_mode"),
            kill_switch_active=bool(payload.get("kill_switch_active", False)),
            cooldown_active=bool(payload.get("cooldown_active", False)),
            daily_pnl_usd=float(payload.get("daily_pnl_usd") or 0.0),
            weekly_pnl_usd=float(payload.get("weekly_pnl_usd") or 0.0),
            daily_loss_usd=max(float(payload.get("daily_loss_usd") or 0.0), 0.0),
            weekly_loss_usd=max(float(payload.get("weekly_loss_usd") or 0.0), 0.0),
            open_positions_count=int(payload.get("open_positions_count") or 0),
            open_exposure_usd=float(payload.get("open_exposure_usd") or 0.0),
            max_daily_loss_usd=float(payload.get("max_daily_loss_usd") or limits["MAX_DAILY_LOSS"]),
            max_weekly_loss_usd=float(payload.get("max_weekly_loss_usd") or limits["MAX_WEEKLY_LOSS"]),
            max_open_positions=int(payload.get("max_open_positions") or limits["MAX_OPEN_POSITIONS"]),
            max_total_exposure_usd=float(payload.get("max_total_exposure_usd") or limits["MAX_TOTAL_EXPOSURE"]),
            max_engine_loss=payload.get("max_engine_loss") or {},
            max_market_family_exposure=payload.get("max_market_family_exposure") or {"*": 250.0},
            active_cooldowns=payload.get("active_cooldowns") or [],
            manual_overrides=payload.get("manual_overrides") or [],
            data_confidence=float(payload.get("data_confidence") or (0.85 if payload else 0.35)),
            insufficient_data=bool(payload.get("insufficient_data", False)),
            insufficient_data_reasons=list(payload.get("insufficient_data_reasons") or []),
        )
        breaches = self.detector.detect_governor_breaches(state)
        engine_losses = payload.get("engine_losses") or {}
        engine_limits = payload.get("max_engine_loss") or {}
        for engine, observed in engine_losses.items():
            limit = float(engine_limits.get(engine, engine_limits.get("*", 25.0)) or 25.0)
            if float(observed or 0.0) >= limit:
                breaches.append(RiskBreach(breach_type="MAX_ENGINE_LOSS", severity="BLOCKING", engine=str(engine).upper(), observed_value=float(observed or 0.0), limit_value=limit, blocked=True, explanation="engine loss limit reached"))
        state.active_breaches = [breach.model_dump(mode="json") for breach in breaches]
        if breaches and state.governor_status == "OK":
            state.governor_status = "BLOCKED"
        attack_allowed, _ = self.attack_gate.evaluate(
            state=state,
            attack_bank_available=float(payload.get("attack_bank_available") or 0.0),
            approval=bool(payload.get("attack_mode_approval", False)),
        )
        state.attack_mode_allowed = attack_allowed
        return state
