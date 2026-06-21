from __future__ import annotations

from app.no_trade.contracts import NORMALIZED_REASONS, NoTradeReason


class NoTradeReasonClassifier:
    _ALIASES = {
        "low edge": "low_edge",
        "weak_trigger": "low_edge",
        "bad_liquidity": "low_liquidity",
        "low depth": "low_liquidity",
        "missing_exit_liquidity": "bad_exit_quality",
        "poor_exit_quality": "bad_exit_quality",
        "bad_rules": "bad_rules",
        "ambiguous_rules": "bad_rules",
        "wording": "high_wording_risk",
        "capital_not_allowed": "no_capital",
        "capital_blocked": "no_capital",
        "governor": "governor_block",
        "risk_governor_blocks": "governor_block",
        "missing risk": "missing_risk_approval",
        "missing exit": "missing_exit_plan",
        "slippage": "high_slippage",
        "spread": "wide_spread",
        "priced": "already_priced_in",
        "cooldown": "cooldown",
        "kill": "kill_switch",
        "stale": "stale_data",
        "ai": "ai_uncertainty",
        "correlation": "high_correlation",
    }

    def classify(self, value: str | None, *, source_layer: str = "system", source_field: str | None = None) -> NoTradeReason:
        raw = str(value or "").strip().lower()
        normalized = raw.replace("-", "_").replace(" ", "_")
        if normalized not in NORMALIZED_REASONS:
            for needle, mapped in self._ALIASES.items():
                if needle in raw or needle in normalized:
                    normalized = mapped
                    break
        insufficient = normalized not in NORMALIZED_REASONS or not raw
        if insufficient:
            normalized = "unknown_reason"
        hard = normalized in {"low_liquidity", "wide_spread", "bad_rules", "high_wording_risk", "high_correlation", "no_capital", "bad_exit_quality", "high_slippage", "governor_block", "missing_exit_plan", "missing_risk_approval", "cooldown", "kill_switch"}
        severity = "BLOCKING" if hard else "WARNING" if normalized in {"low_edge", "already_priced_in", "ai_uncertainty", "stale_data", "insufficient_data", "unknown_reason"} else "INFO"
        return NoTradeReason(
            reason=normalized,
            severity=severity,
            source_layer=source_layer,
            source_field=source_field,
            hard_block=hard,
            explanation=f"Classified no-trade reason '{raw or 'unknown'}' as {normalized}.",
        )
