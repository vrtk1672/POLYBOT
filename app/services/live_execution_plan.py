from __future__ import annotations

from dataclasses import dataclass, field

from app.stage4 import (
    LiveGuard,
    Stage4ExecutionClient,
    build_allowed_universe,
    build_live_order_intent,
    evaluate_execution_policy,
    get_stage4_settings,
    rank_candidates,
)
from app.stage4.config import Stage4Settings
from app.stage4.execution_policy import ExecutionPolicyDecision
from app.stage4.live_guard import LiveGuardDecision
from app.stage4.order_builder import LiveOrderIntent, LiveOrderValidationError


@dataclass(slots=True)
class ExecutionCandidateEvaluation:
    ranked: object
    market_id: str
    decision_stage: str
    status: str
    reason_code: str
    reason_text: str
    token_id: str | None = None
    tick_size: str | None = None
    neg_risk: bool | None = None
    min_order_size: float | None = None
    balance_info: dict[str, object] = field(default_factory=dict)
    collateral_balance: float | None = None
    intent: LiveOrderIntent | None = None
    policy_decision: ExecutionPolicyDecision | None = None
    guard_decision: LiveGuardDecision | None = None


@dataclass(slots=True)
class LiveExecutionPlan:
    source_markets: list[object]
    allowed_universe: list[object]
    ranked_candidates: list[object]
    skipped: list[str]
    open_orders: list[dict[str, object]]
    open_orders_error: str | None
    evaluations: list[ExecutionCandidateEvaluation]

    @property
    def selected(self) -> ExecutionCandidateEvaluation | None:
        for evaluation in self.evaluations:
            if evaluation.status == "WOULD_SUBMIT":
                return evaluation
        return None


def build_live_execution_plan(
    cycle_result,
    *,
    settings: Stage4Settings | None = None,
    execution_client: Stage4ExecutionClient | None = None,
    guard: LiveGuard | None = None,
    live: bool,
    armed: bool,
) -> LiveExecutionPlan:
    effective_settings = settings or get_stage4_settings()
    client = execution_client or Stage4ExecutionClient(effective_settings)
    evaluator = guard or LiveGuard(effective_settings)

    source_limit = effective_settings.live_allowed_universe_top_n if effective_settings.live_use_adaptive_selector else 1
    source_markets = cycle_result.top_scored[:source_limit]
    allowed_universe, skipped = build_allowed_universe(source_markets, cycle_result.recommendations, effective_settings)
    ranked_candidates = rank_candidates(allowed_universe)

    try:
        open_orders = client.get_open_orders()
        open_orders_error = None
    except Exception as exc:
        open_orders = []
        open_orders_error = str(exc)

    evaluations: list[ExecutionCandidateEvaluation] = []
    for ranked in ranked_candidates:
        candidate = ranked.candidate
        token_id = candidate.token_ids[1] if candidate.recommendation.action == "BUY_NO" else candidate.token_ids[0]
        try:
            order_book = client.get_order_book_summary(token_id)
            tick_size = getattr(order_book, "tick_size", None) or "0.01"
            neg_risk = bool(getattr(order_book, "neg_risk", False))
            min_order_size = float(getattr(order_book, "min_order_size", "0") or 0.0)
        except Exception as exc:
            evaluations.append(
                ExecutionCandidateEvaluation(
                    ranked=ranked,
                    market_id=candidate.market.market_id,
                    token_id=token_id,
                    decision_stage="orderbook_lookup",
                    status="BLOCKED",
                    reason_code="orderbook_lookup_failed",
                    reason_text=str(exc),
                )
            )
            continue

        if effective_settings.live_require_orderbook and min_order_size <= 0:
            evaluations.append(
                ExecutionCandidateEvaluation(
                    ranked=ranked,
                    market_id=candidate.market.market_id,
                    token_id=token_id,
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                    min_order_size=min_order_size,
                    decision_stage="orderbook_check",
                    status="BLOCKED",
                    reason_code="unusable_orderbook",
                    reason_text=f"min_order_size={min_order_size}",
                )
            )
            continue

        try:
            balance_info = client.get_balance_allowance(token_id=token_id)
            collateral_balance = float(balance_info["collateral"].get("balance_usd", 0.0))
        except Exception as exc:
            balance_info = {"error": str(exc)}
            collateral_balance = effective_settings.live_max_order_usd

        try:
            intent = build_live_order_intent(
                candidate.item,
                candidate.recommendation,
                bucket=candidate.bucket,
                tick_size=tick_size,
                neg_risk=neg_risk,
                min_order_size=min_order_size,
                max_order_usd=effective_settings.live_max_order_usd,
                balance_hint=collateral_balance,
            )
        except LiveOrderValidationError as exc:
            evaluations.append(
                ExecutionCandidateEvaluation(
                    ranked=ranked,
                    market_id=candidate.market.market_id,
                    token_id=token_id,
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                    min_order_size=min_order_size,
                    balance_info=balance_info,
                    collateral_balance=collateral_balance,
                    decision_stage="intent_build",
                    status="BLOCKED",
                    reason_code=exc.code,
                    reason_text=str(exc),
                )
            )
            continue
        except Exception as exc:
            evaluations.append(
                ExecutionCandidateEvaluation(
                    ranked=ranked,
                    market_id=candidate.market.market_id,
                    token_id=token_id,
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                    min_order_size=min_order_size,
                    balance_info=balance_info,
                    collateral_balance=collateral_balance,
                    decision_stage="intent_build",
                    status="BLOCKED",
                    reason_code="intent_build_failed",
                    reason_text=str(exc),
                )
            )
            continue

        policy_decision = evaluate_execution_policy(
            ranked,
            open_orders=open_orders,
            settings=effective_settings,
            open_orders_error=open_orders_error,
        )
        guard_decision = evaluator.evaluate_order(
            market_id=intent.market_id,
            notional_usd=intent.notional_usd,
            live=live,
            armed=armed,
        )
        combined_reasons = [*policy_decision.reasons, *guard_decision.reasons]
        if combined_reasons:
            evaluations.append(
                ExecutionCandidateEvaluation(
                    ranked=ranked,
                    market_id=candidate.market.market_id,
                    token_id=token_id,
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                    min_order_size=min_order_size,
                    balance_info=balance_info,
                    collateral_balance=collateral_balance,
                    intent=intent,
                    policy_decision=policy_decision,
                    guard_decision=guard_decision,
                    decision_stage="policy_guard",
                    status="BLOCKED",
                    reason_code=_normalize_reason_code(combined_reasons[0]),
                    reason_text="; ".join(combined_reasons),
                )
            )
            continue

        evaluations.append(
            ExecutionCandidateEvaluation(
                ranked=ranked,
                market_id=candidate.market.market_id,
                token_id=token_id,
                tick_size=tick_size,
                neg_risk=neg_risk,
                min_order_size=min_order_size,
                balance_info=balance_info,
                collateral_balance=collateral_balance,
                intent=intent,
                policy_decision=policy_decision,
                guard_decision=guard_decision,
                decision_stage="ready_to_submit",
                status="WOULD_SUBMIT",
                reason_code="would_submit",
                reason_text="candidate passed the live path through the submit boundary",
            )
        )
        break

    return LiveExecutionPlan(
        source_markets=source_markets,
        allowed_universe=allowed_universe,
        ranked_candidates=ranked_candidates,
        skipped=skipped,
        open_orders=open_orders,
        open_orders_error=open_orders_error,
        evaluations=evaluations,
    )


def _normalize_reason_code(reason: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in reason)
    normalized = "_".join(part for part in cleaned.split("_") if part)
    return normalized[:64] or "blocked"
