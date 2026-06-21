from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.risk.contracts import RiskGateDecision, RiskGateInput, RiskGovernorState, reproducibility_hash
from app.risk.cooldown_manager import CooldownManager
from app.risk.correlation_checker import CorrelationChecker
from app.risk.exposure_checker import ExposureChecker
from app.risk.risk_limit_manager import RiskLimitManager


class RiskGate:
    def __init__(self) -> None:
        self.limit_manager = RiskLimitManager()
        self.exposure = ExposureChecker()
        self.correlation = CorrelationChecker()
        self.cooldowns = CooldownManager()

    def evaluate(self, payload: RiskGateInput, *, run_id: str | None = None) -> RiskGateDecision:
        run_id = run_id or f"risk_gate_{uuid4().hex}"
        limits = self.limit_manager.as_dict()
        limits.update(payload.risk_limits or {})
        governor = payload.governor_state
        if isinstance(governor, dict):
            governor = RiskGovernorState(**governor)
        if governor is None:
            governor = RiskGovernorState(governor_status="INSUFFICIENT_DATA", insufficient_data=True, insufficient_data_reasons=["missing_governor_state"])

        route = payload.strategy_route or {}
        allocation = payload.capital_allocation or {}
        technical = payload.technical_truth or {}
        contract = route.get("engine_contract_json") or route.get("contract") or {}

        block_reasons: list[str] = []
        warnings: list[str] = []
        checks = {
            "liquidity_ok": True,
            "slippage_ok": True,
            "wording_risk_ok": True,
            "correlation_ok": True,
            "exposure_ok": True,
            "engine_budget_ok": True,
            "confidence_ok": True,
            "exit_plan_ok": True,
            "governor_ok": True,
        }
        if governor.governor_status == "KILL" or governor.kill_switch_active:
            checks["governor_ok"] = False
            block_reasons.append("governor_kill")
        elif governor.governor_status in {"BLOCKED", "INSUFFICIENT_DATA"}:
            checks["governor_ok"] = False
            block_reasons.append(f"governor_{governor.governor_status.lower()}")

        cooldown_blocked, cooldown_reason = self.cooldowns.active_blocks(engine=payload.engine, market_family=payload.market_family, cooldowns=governor.active_cooldowns)
        if cooldown_blocked:
            block_reasons.append(cooldown_reason or "active_cooldown")

        if route.get("selected_engine") == "NO_TRADE" or route.get("route_status") in {"NO_TRADE", "BLOCKED", "INSUFFICIENT_DATA"}:
            block_reasons.append("strategy_route_not_risk_eligible")
        if not allocation:
            block_reasons.append("missing_capital_allocation")
        elif allocation.get("allocation_status") in {"BLOCKED", "INSUFFICIENT_DATA", "DRY_RUN"} or float(allocation.get("approved_size_usd") or 0) <= 0:
            block_reasons.append("capital_allocation_not_risk_eligible")

        exit_plan = payload.exit_plan_candidate or contract.get("exit_conditions") or {}
        if not exit_plan and not (route.get("target_exit") and route.get("stop_loss")) and not (contract.get("target_exit") and contract.get("stop_loss")):
            checks["exit_plan_ok"] = False
            block_reasons.append("missing_exit_plan")

        approved_size = float(allocation.get("approved_size_usd") or route.get("max_position_size_usd") or contract.get("max_position_size_usd") or 0)
        max_loss = float(allocation.get("max_loss_usd") or route.get("max_loss_usd") or contract.get("max_loss_usd") or 0)
        if max_loss > float(limits["MAX_TRADE_LOSS"]):
            block_reasons.append("max_trade_loss_breach")

        liquidity_quality = _deep_number(technical, ("liquidity_quality", "exit_quality_score", "exit_quality", "liquidity_signal.exit_quality_score"), 1.0)
        if liquidity_quality < 0.30:
            checks["liquidity_ok"] = False
            block_reasons.append("bad_liquidity")
        slippage_bps = _deep_number(technical, ("expected_slippage_bps", "slippage_bps", "liquidity_signal.expected_slippage_bps"), 0.0)
        if slippage_bps > float(limits["MAX_SLIPPAGE"]):
            checks["slippage_ok"] = False
            block_reasons.append("high_slippage")
        wording_risk = max(float(payload.rules_risk.get("wording_risk") or 0.0), float(payload.opportunity_score.get("wording_risk") or 0.0), _deep_number(route, ("wording_risk",), 0.0))
        if wording_risk > float(limits["MAX_WORDING_RISK"]):
            checks["wording_risk_ok"] = False
            block_reasons.append("high_wording_risk")
        confidence = max(float(route.get("route_confidence") or 0.0), float(payload.opportunity_score.get("confidence") or 0.0))
        if confidence < float(limits["MIN_CONFIDENCE"]):
            checks["confidence_ok"] = False
            block_reasons.append("low_confidence")
        if float(allocation.get("engine_budget_after_usd") or 0) < 0:
            checks["engine_budget_ok"] = False
            block_reasons.append("engine_budget_breach")

        exposure_ok, exposure_reason = self.exposure.check(open_exposure_usd=governor.open_exposure_usd, proposed_size_usd=approved_size, max_total_exposure_usd=governor.max_total_exposure_usd)
        if not exposure_ok:
            checks["exposure_ok"] = False
            block_reasons.append(exposure_reason or "exposure_breach")
        corr_ok, corr_reason = self.correlation.check(
            market_family=payload.market_family,
            family_exposure=payload.market_memory.get("family_exposure") or {},
            proposed_size_usd=approved_size,
            max_family_exposure=governor.max_market_family_exposure or {"*": 250.0},
        )
        if not corr_ok:
            checks["correlation_ok"] = False
            block_reasons.append(corr_reason or "correlation_breach")

        if payload.data_completeness_score < 0.25:
            block_reasons.append("insufficient_data")

        hard = [reason for reason in block_reasons if reason in {"governor_kill", "missing_exit_plan", "bad_liquidity", "strategy_route_not_risk_eligible", "capital_allocation_not_risk_eligible"}]
        override = payload.manual_override or {}
        override_used = False
        if override and not hard and block_reasons:
            override_used = True
            warnings.append("manual_override_used_for_soft_risk")
            block_reasons = []
        elif override and hard:
            warnings.append("manual_override_cannot_bypass_hard_block")

        if block_reasons:
            decision = "INSUFFICIENT_DATA" if set(block_reasons) == {"insufficient_data"} or "missing_capital_allocation" in block_reasons else "BLOCKED"
        elif governor.governor_status == "COOLDOWN":
            decision = "COOLDOWN"
        else:
            decision = "APPROVED"

        penalty = min(len(block_reasons) * 0.12, 0.95)
        risk_score = max(0.0, min(1.0, 0.25 + penalty + (slippage_bps / 10000.0) + wording_risk))
        hash_payload = {
            "market_id": payload.market_id,
            "engine": payload.engine,
            "route": route,
            "allocation": allocation,
            "block_reasons": block_reasons,
            "limits": limits,
        }
        return RiskGateDecision(
            run_id=run_id,
            market_id=payload.market_id,
            market_family=payload.market_family,
            side=payload.side,
            engine=payload.engine,
            decision=decision,  # type: ignore[arg-type]
            risk_score=risk_score,
            max_loss_usd=max_loss,
            approved_max_loss_usd=max_loss if decision == "APPROVED" else 0,
            approved_position_size_usd=approved_size if decision == "APPROVED" else 0,
            block_reasons=block_reasons,
            warnings=warnings,
            constraints={"limits": limits, "not_executable_order": True, "gate_approval_only": True},
            manual_override_used=override_used,
            override_id=override.get("override_id"),
            explanation="risk gate approved policy record" if decision == "APPROVED" else "risk gate blocked or constrained the proposal",
            reproducibility_hash=reproducibility_hash(hash_payload),
            **checks,
        )


def _deep_number(payload: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        current: Any = payload
        parts = key.split(".")
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            try:
                return float(current)
            except (TypeError, ValueError):
                continue
    return default

