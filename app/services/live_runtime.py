from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.services.execution_adapters import build_execution_adapter
from app.services.execution_contract import ExecutionAdapter, ExecutionIntent, ExecutionResult
from app.services.live_execution_plan import ExecutionCandidateEvaluation, build_live_execution_plan
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.recorders.execution_memory import ExecutionMemoryPersistenceService
from app.stage4 import LiveGuard, Stage4ExecutionClient, get_stage4_settings

logger = logging.getLogger(__name__)

OPEN_LIVE_ORDER_STATUSES = {"SUBMISSION_REQUESTED", "SUBMITTED", "LIVE", "OPEN", "PARTIALLY_FILLED"}
OPEN_LIVE_POSITION_STATUSES = {"OPEN", "EXIT_PENDING"}


@dataclass(slots=True)
class LiveTradingRunResult:
    cycle_id: str | None
    evaluated_count: int
    persisted_count: int
    selected_market_id: str | None


class LiveStage4InspectionClient:
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)

    def get_open_orders(self) -> list[dict[str, object]]:
        open_exposures: list[dict[str, object]] = []
        try:
            open_exposures.extend(dict(row) for row in self._execution_client.get_open_orders())
        except Exception as exc:
            logger.info("live_open_order_exchange_inspection_failed error=%s", exc)
        if not self._factory.enabled:
            return open_exposures
        with self._factory.connect() as conn:
            order_rows = conn.execute(
                """
                SELECT market_id, updated_at AS created_at, 'ORDER' AS exposure_type
                FROM live_orders
                WHERE status = ANY(%s)
                """,
                (list(OPEN_LIVE_ORDER_STATUSES),),
            ).fetchall()
            position_rows = conn.execute(
                """
                SELECT market_id, updated_at AS created_at, 'POSITION' AS exposure_type
                FROM positions
                WHERE closed_at IS NULL
                  AND current_status = ANY(%s)
                """,
                (list(OPEN_LIVE_POSITION_STATUSES),),
            ).fetchall()
        open_exposures.extend(dict(row) for row in order_rows)
        open_exposures.extend(dict(row) for row in position_rows)
        return open_exposures

    def get_order_book_summary(self, token_id: str):
        return self._execution_client.get_order_book_summary(token_id)

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
        return self._execution_client.get_balance_allowance(token_id=token_id)

    def auth_context(self) -> dict[str, object]:
        return self._execution_client.auth_context()

    def create_signed_order(self, intent):
        return self._execution_client.create_signed_order(intent)

    def submit_order(self, intent):
        return self._execution_client.submit_order(intent)

    def get_order_status(self, order_id: str) -> dict[str, object]:
        return self._execution_client.get_order_status(order_id)


class LiveTradingService:
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
        guard: LiveGuard | None = None,
        execution_adapter: ExecutionAdapter | None = None,
        execution_memory: ExecutionMemoryPersistenceService | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._inspection_client = LiveStage4InspectionClient(
            settings=self._settings,
            connection_factory=self._factory,
            execution_client=execution_client,
        )
        self._guard = guard or LiveGuard(self._stage4_settings)
        self._execution_adapter = execution_adapter or build_execution_adapter(
            backend_target="live",
            settings=self._stage4_settings,
            execution_client=execution_client,
        )
        self._execution_memory = execution_memory or ExecutionMemoryPersistenceService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._governor = StateGovernor(connection_factory=self._factory)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def record_cycle(self, cycle_result) -> LiveTradingRunResult | None:
        if not self.enabled:
            return None
        if not self._governor.can_execute(RuntimeAction.SEND_LIVE_ORDER):
            logger.warning("live_runtime_blocked_by_runtime_mode cycle_id=%s", getattr(cycle_result, "cycle_id", None))
            return LiveTradingRunResult(
                cycle_id=getattr(cycle_result, "cycle_id", None),
                evaluated_count=0,
                persisted_count=0,
                selected_market_id=None,
            )

        plan = build_live_execution_plan(
            cycle_result,
            settings=self._stage4_settings,
            execution_client=self._inspection_client,
            guard=self._guard,
            live=True,
            armed=True,
        )
        logger.info(
            "live_runtime_plan cycle_id=%s selected=%s evaluations=%s details=%s",
            cycle_result.cycle_id,
            plan.selected.market_id if plan.selected is not None else None,
            len(plan.evaluations),
            [
                {
                    "market_id": evaluation.market_id,
                    "decision_stage": evaluation.decision_stage,
                    "status": evaluation.status,
                    "reason_code": evaluation.reason_code,
                    "reason_text": evaluation.reason_text,
                    "has_intent": evaluation.intent is not None,
                }
                for evaluation in plan.evaluations[:5]
            ],
        )
        persisted_count = 0
        selected_market_id: str | None = None
        selected_market_for_state = next(
            (evaluation.market_id for evaluation in plan.evaluations if evaluation.intent is not None),
            None,
        )
        cage_state = self._load_cage_state(market_id=selected_market_for_state)

        for evaluation in plan.evaluations:
            if evaluation.intent is None:
                logger.info(
                    "live_runtime_evaluation_skipped cycle_id=%s market_id=%s stage=%s status=%s reason=%s detail=%s",
                    cycle_result.cycle_id,
                    evaluation.market_id,
                    evaluation.decision_stage,
                    evaluation.status,
                    evaluation.reason_code,
                    evaluation.reason_text,
                )
                continue
            execution_intent = self._build_execution_intent(
                cycle_id=cycle_result.cycle_id,
                evaluation=evaluation,
            )
            order_handle = self._execution_memory.record_submission_requested(
                cycle_id=cycle_result.cycle_id,
                intent=evaluation.intent,
                raw_request={
                    "execution_contract": execution_intent.to_payload(),
                    "live_cage": cage_state,
                    "decision_stage": evaluation.decision_stage,
                },
            )
            if order_handle is None:
                logger.info(
                    "live_runtime_submission_request_not_persisted cycle_id=%s market_id=%s stage=%s status=%s",
                    cycle_result.cycle_id,
                    evaluation.market_id,
                    evaluation.decision_stage,
                    evaluation.status,
                )
                continue
            logger.info(
                "live_runtime_submission_requested cycle_id=%s market_id=%s order_id=%s stage=%s status=%s",
                cycle_result.cycle_id,
                evaluation.market_id,
                order_handle.order_id,
                evaluation.decision_stage,
                evaluation.status,
            )
            execution_result = self._build_execution_result(
                evaluation=evaluation,
                execution_intent=execution_intent,
                cage_state=cage_state,
            )
            self._execution_memory.record_execution_result(
                handle=order_handle,
                execution_result=execution_result,
            )
            logger.info(
                "live_runtime_execution_result cycle_id=%s market_id=%s order_id=%s result_status=%s accepted=%s",
                cycle_result.cycle_id,
                evaluation.market_id,
                order_handle.order_id,
                execution_result.result_status,
                execution_result.accepted,
            )
            persisted_count += 1
            if execution_result.accepted and execution_result.result_status not in {"BLOCKED_BY_CONFIG", "BLOCKED_BY_RISK", "INVALID_REQUEST", "REJECTED"}:
                selected_market_id = evaluation.market_id

        return LiveTradingRunResult(
            cycle_id=cycle_result.cycle_id,
            evaluated_count=len(plan.evaluations),
            persisted_count=persisted_count,
            selected_market_id=selected_market_id,
        )

    def _build_execution_result(
        self,
        *,
        evaluation: ExecutionCandidateEvaluation,
        execution_intent: ExecutionIntent,
        cage_state: dict[str, object],
    ) -> ExecutionResult:
        runtime_reasons = self._runtime_risk_reasons(
            market_id=evaluation.market_id,
            side=execution_intent.side,
            daily_realized_loss_usd=float(cage_state["daily_realized_loss_usd"]),
            live_positions_count=int(cage_state["open_live_positions"]),
            same_market_positions_count=int(cage_state["same_market_live_positions"]),
            control_kill_active=bool(cage_state["control_kill_active"]),
        )
        if runtime_reasons:
            return ExecutionResult(
                intent_id=execution_intent.intent_id,
                correlation_id=execution_intent.correlation_id,
                accepted=False,
                result_status="BLOCKED_BY_RISK",
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(execution_intent.size),
                external_order_id=None,
                error_code="live_runtime_cage_blocked",
                error_text="; ".join(runtime_reasons),
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "runtime_risk_reasons": runtime_reasons,
                    "live_cage": cage_state,
                },
                processed_at=datetime.now(UTC),
            )
        if evaluation.status != "WOULD_SUBMIT":
            result_status = _blocked_status_from_evaluation(evaluation)
            return ExecutionResult(
                intent_id=execution_intent.intent_id,
                correlation_id=execution_intent.correlation_id,
                accepted=False,
                result_status=result_status,
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(execution_intent.size),
                external_order_id=None,
                error_code=evaluation.reason_code,
                error_text=evaluation.reason_text,
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "decision_stage": evaluation.decision_stage,
                    "policy_reasons": list(evaluation.policy_decision.reasons) if evaluation.policy_decision else [],
                    "guard_reasons": list(evaluation.guard_decision.reasons) if evaluation.guard_decision else [],
                    "live_cage": cage_state,
                },
                processed_at=datetime.now(UTC),
            )
        return self._execution_adapter.submit_intent(execution_intent)

    def _runtime_risk_reasons(
        self,
        *,
        market_id: str,
        side: str,
        daily_realized_loss_usd: float,
        live_positions_count: int,
        same_market_positions_count: int,
        control_kill_active: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if control_kill_active:
            reasons.append("operator KILL control is active")
        if daily_realized_loss_usd >= self._stage4_settings.live_max_daily_loss_usd:
            reasons.append(
                f"daily realized loss ${daily_realized_loss_usd:.4f} meets/exceeds MAX_DAILY_LOSS ${self._stage4_settings.live_max_daily_loss_usd:.4f}"
            )
        if live_positions_count >= self._stage4_settings.live_max_open_positions:
            reasons.append(
                f"open live positions {live_positions_count} meet/exceed MAX_CONCURRENT_POSITIONS {self._stage4_settings.live_max_open_positions}"
            )
        if not self._stage4_settings.live_allow_scaling and same_market_positions_count > 0:
            reasons.append(f"ALLOW_SCALING is false and live exposure already exists for market {market_id}")
        return reasons

    def _load_cage_state(self, *, market_id: str | None) -> dict[str, object]:
        control_kill_active = False
        control_override: dict[str, object] | None = None
        daily_realized_loss_usd = 0.0
        open_live_positions = 0
        same_market_live_positions = 0
        if self._factory.enabled:
            with self._factory.connect() as conn:
                control_row = conn.execute(
                    """
                    SELECT action_class, status_class, created_at, metadata_json
                    FROM operator_control_actions
                    WHERE action_class IN ('KILL', 'RESUME')
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if control_row is not None:
                    control_override = _json_safe(dict(control_row))
                    control_kill_active = str(control_row["action_class"]) == "KILL" and str(control_row["status_class"]) == "ACTIVE_GUARD"
                daily_realized_loss_usd = float(
                    conn.execute(
                        """
                        SELECT COALESCE(ABS(SUM(LEAST(realized, 0))), 0) AS loss
                        FROM positions
                        WHERE updated_at >= date_trunc('day', now())
                        """
                    ).fetchone()["loss"]
                )
                open_live_positions = int(
                    conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM positions
                        WHERE closed_at IS NULL
                          AND current_status = ANY(%s)
                        """,
                        (list(OPEN_LIVE_POSITION_STATUSES),),
                    ).fetchone()["count"]
                )
                if market_id:
                    same_market_live_positions = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) AS count
                            FROM positions
                            WHERE market_id = %s
                              AND closed_at IS NULL
                              AND current_status = ANY(%s)
                            """,
                            (market_id, list(OPEN_LIVE_POSITION_STATUSES)),
                        ).fetchone()["count"]
                    )
        return {
            "live_trading_enabled": self._stage4_settings.live_trading_enabled,
            "live_kill_switch": self._stage4_settings.live_kill_switch,
            "live_market_whitelist": list(self._stage4_settings.live_market_whitelist),
            "live_max_order_usd": self._stage4_settings.live_max_order_usd,
            "live_max_daily_loss_usd": self._stage4_settings.live_max_daily_loss_usd,
            "live_max_open_positions": self._stage4_settings.live_max_open_positions,
            "live_max_same_market_exposure": self._stage4_settings.live_max_same_market_exposure,
            "live_allow_scaling": self._stage4_settings.live_allow_scaling,
            "daily_realized_loss_usd": round(daily_realized_loss_usd, 6),
            "open_live_positions": open_live_positions,
            "same_market_live_positions": same_market_live_positions,
            "control_kill_active": control_kill_active,
            "control_override": control_override,
        }

    @staticmethod
    def _build_execution_intent(
        *,
        cycle_id: str | None,
        evaluation: ExecutionCandidateEvaluation,
    ) -> ExecutionIntent:
        intent = evaluation.intent
        assert intent is not None
        return ExecutionIntent(
            intent_id=str(uuid4()),
            correlation_id=cycle_id or str(uuid4()),
            market_id=intent.market_id,
            side=intent.side,
            order_type="LIMIT",
            size=float(intent.size),
            price_limit=float(intent.price),
            reason_code=evaluation.reason_code,
            reason_text=evaluation.reason_text,
            risk_metadata={
                "bucket": intent.bucket,
                "notional_usd": float(intent.notional_usd),
                "tick_size": intent.tick_size,
                "neg_risk": bool(intent.neg_risk),
                "min_order_size": float(evaluation.min_order_size or intent.min_order_size or 0.0),
                "balance_info": evaluation.balance_info,
            },
            source_context={
                "token_id": intent.token_id,
                "question": intent.question,
                "action": intent.action,
                "decision_stage": evaluation.decision_stage,
                "market_id": evaluation.market_id,
            },
            execution_mode="live",
            backend_target="live",
            created_at=datetime.now(UTC),
        )


def _blocked_status_from_evaluation(evaluation: ExecutionCandidateEvaluation) -> str:
    if evaluation.decision_stage == "policy_guard":
        reasons = [
            *(list(evaluation.policy_decision.reasons) if evaluation.policy_decision else []),
            *(list(evaluation.guard_decision.reasons) if evaluation.guard_decision else []),
        ]
        if any(reason.startswith("LIVE_") or "whitelist" in reason.lower() for reason in reasons):
            return "BLOCKED_BY_CONFIG"
        return "BLOCKED_BY_RISK"
    return "INVALID_REQUEST"


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
