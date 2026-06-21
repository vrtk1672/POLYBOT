from __future__ import annotations

from typing import Any


class CancelConditionEvaluator:
    def evaluate(self, *, cancel_if: dict[str, Any], current: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if cancel_if.get("spread_widens") is not None and float(current.get("spread_bps") or 0.0) > float(cancel_if["spread_widens"]):
            reasons.append("spread_widens")
        if cancel_if.get("fill_rate_too_low") is not None and float(current.get("fill_rate") or 1.0) < float(cancel_if["fill_rate_too_low"]):
            reasons.append("fill_rate_too_low")
        if cancel_if.get("depth_drops") is not None and float(current.get("depth_2c") or 0.0) < float(cancel_if["depth_drops"]):
            reasons.append("depth_drops")
        if cancel_if.get("risk_governor_blocks") and str(current.get("governor_status") or "OK").upper() in {"KILL", "BLOCKED", "COOLDOWN"}:
            reasons.append("risk_governor_blocks")
        if cancel_if.get("ttl_expired") and current.get("ttl_expired"):
            reasons.append("ttl_expired")
        if cancel_if.get("slippage_too_high") is not None and float(current.get("slippage_bps") or 0.0) > float(cancel_if["slippage_too_high"]):
            reasons.append("slippage_too_high")
        if cancel_if.get("score_drops") is not None and float(current.get("score") or 1.0) < float(cancel_if["score_drops"]):
            reasons.append("score_drops")
        if cancel_if.get("news_reversal") and current.get("news_reversal"):
            reasons.append("news_reversal")
        return bool(reasons), reasons

