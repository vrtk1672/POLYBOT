from __future__ import annotations

from typing import Any

from app.capital.contracts import CapitalState, non_negative
from app.services.capital_allocator import PaperCapitalSource


class CapitalStateBuilder:
    def build(self, *, runtime_mode: str | None = None, manual_payload: dict[str, Any] | None = None) -> CapitalState:
        if manual_payload is not None:
            return self._from_manual(runtime_mode=runtime_mode, payload=manual_payload)
        return self._from_paper(runtime_mode=runtime_mode)

    def _from_manual(self, *, runtime_mode: str | None, payload: dict[str, Any]) -> CapitalState:
        total = non_negative(payload.get("total_capital_usd"))
        available = non_negative(payload.get("available_capital_usd"), total)
        realized = max(float(payload.get("realized_pnl_usd") or 0.0), 0.0)
        survival = non_negative(payload.get("survival_reserve_usd"), total * 0.20)
        cash = non_negative(payload.get("cash_reserve_usd"), total * 0.10)
        profit_pocket = non_negative(payload.get("profit_pocket_usd"), realized)
        attack_bank = non_negative(payload.get("attack_bank_usd"), min(profit_pocket * 0.30, profit_pocket))
        reasons = list(payload.get("insufficient_data_reasons") or [])
        insufficient = bool(payload.get("insufficient_data", False))
        if total <= 0:
            insufficient = True
            reasons.append("missing_total_capital")
        return CapitalState(
            runtime_mode=runtime_mode,
            total_capital_usd=total,
            base_capital_usd=non_negative(payload.get("base_capital_usd"), max(total - realized, 0.0)),
            available_capital_usd=available,
            locked_capital_usd=non_negative(payload.get("locked_capital_usd")),
            open_exposure_usd=non_negative(payload.get("open_exposure_usd")),
            survival_reserve_usd=survival,
            cash_reserve_usd=cash,
            profit_pocket_usd=profit_pocket,
            attack_bank_usd=attack_bank,
            realized_pnl_usd=max(float(payload.get("realized_pnl_usd") or 0.0), 0.0),
            unrealized_pnl_usd=payload.get("unrealized_pnl_usd"),
            daily_pnl_usd=payload.get("daily_pnl_usd"),
            weekly_pnl_usd=payload.get("weekly_pnl_usd"),
            loss_streak_count=int(non_negative(payload.get("loss_streak_count"))),
            win_streak_count=int(non_negative(payload.get("win_streak_count"))),
            source_type=str(payload.get("source_type") or "MANUAL_SMOKE"),
            source_ref=payload.get("source_ref"),
            data_confidence=payload.get("data_confidence", 0.85),
            insufficient_data=insufficient,
            insufficient_data_reasons=reasons,
        )

    def _from_paper(self, *, runtime_mode: str | None) -> CapitalState:
        snapshot = PaperCapitalSource().snapshot()
        reserve_target = non_negative(snapshot.metadata.get("reserve_target_usd"), snapshot.reserved_cash_usd)
        realized_positive = max(snapshot.realized_pnl_usd, 0.0)
        return CapitalState(
            runtime_mode=runtime_mode,
            total_capital_usd=snapshot.total_equity_usd,
            base_capital_usd=max(snapshot.total_equity_usd - realized_positive, 0.0),
            available_capital_usd=snapshot.available_cash_usd,
            locked_capital_usd=snapshot.pending_notional_usd,
            open_exposure_usd=snapshot.deployed_notional_usd,
            survival_reserve_usd=round(max(snapshot.total_equity_usd * 0.20, reserve_target), 6),
            cash_reserve_usd=round(max(snapshot.total_equity_usd * 0.10, reserve_target), 6),
            profit_pocket_usd=realized_positive,
            attack_bank_usd=0.0,
            realized_pnl_usd=realized_positive,
            unrealized_pnl_usd=snapshot.unrealized_pnl_usd,
            loss_streak_count=0,
            win_streak_count=0,
            source_type=f"PAPER_{snapshot.source_status}",
            source_ref=snapshot.source_mode,
            data_confidence=0.85 if snapshot.source_status == "READY" else 0.35,
            insufficient_data=snapshot.source_status not in {"READY", "DB_DISABLED"},
            insufficient_data_reasons=[] if snapshot.total_equity_usd > 0 else ["missing_capital_data"],
        )

