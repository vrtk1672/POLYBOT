from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.shadow_order import ShadowOrderContract
from app.domain.contracts.shadow_order_event import ShadowOrderEventContract
from app.domain.contracts.shadow_position import ShadowPositionContract
from app.domain.contracts.shadow_position_event import ShadowPositionEventContract
from app.domain.contracts.shadow_run import ShadowRunCloseContract, ShadowRunOpenContract
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.shadow_order_events_repository import ShadowOrderEventsRepository
from app.repositories.shadow_orders_repository import ShadowOrdersRepository
from app.repositories.shadow_position_events_repository import ShadowPositionEventsRepository
from app.repositories.shadow_positions_repository import ShadowPositionsRepository
from app.repositories.shadow_runs_repository import ShadowRunsRepository
from app.services.execution_adapters import build_execution_adapter
from app.services.execution_contract import ExecutionAdapter, ExecutionIntent
from app.services.live_execution_plan import ExecutionCandidateEvaluation, build_live_execution_plan
from app.services.recorders.shadow_order_event_recorder import ShadowOrderEventRecorder
from app.services.recorders.shadow_order_recorder import ShadowOrderRecorder
from app.services.recorders.shadow_position_event_recorder import ShadowPositionEventRecorder
from app.services.recorders.shadow_position_recorder import ShadowPositionRecorder
from app.services.recorders.shadow_run_recorder import ShadowRunRecorder
from app.stage4 import Stage4ExecutionClient, get_stage4_settings
from app.stage4.live_guard import LiveGuard

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ShadowLiveRunResult:
    shadow_run_id: str
    shadow_orders_count: int
    candidates_selected_count: int
    selected_market_id: str | None


class ShadowLiveService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
        guard: LiveGuard | None = None,
        execution_adapter: ExecutionAdapter | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)
        self._guard = guard
        self._execution_adapter = execution_adapter or build_execution_adapter(
            backend_target="shadow_live",
            settings=self._stage4_settings,
            execution_client=self._execution_client,
        )
        self._shadow_runs = ShadowRunRecorder(ShadowRunsRepository())
        self._shadow_orders = ShadowOrderRecorder(ShadowOrdersRepository())
        self._shadow_order_events = ShadowOrderEventRecorder(ShadowOrderEventsRepository())
        self._shadow_positions = ShadowPositionRecorder(ShadowPositionsRepository())
        self._shadow_position_events = ShadowPositionEventRecorder(ShadowPositionEventsRepository())
        self._decisions = DecisionLedgerRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def record_cycle(self, cycle_result) -> ShadowLiveRunResult | None:
        if not self.enabled:
            return None

        shadow_run_id = str(uuid4())
        started_at = datetime.now(UTC)
        try:
            plan = build_live_execution_plan(
                cycle_result,
                settings=self._stage4_settings,
                execution_client=self._execution_client,
                guard=self._guard,
                live=False,
                armed=False,
            )
            with self._factory.connect() as conn, conn.transaction():
                self._shadow_runs.open_run(
                    conn,
                    ShadowRunOpenContract(
                        id=shadow_run_id,
                        cycle_id=cycle_result.cycle_id,
                        mode="SHADOW_LIVE",
                        started_at=started_at,
                        status="OPEN",
                        metadata_json={"cycle_id": cycle_result.cycle_id},
                    ),
                )
                decision_rows = {
                    str(row["market_id"]): row
                    for row in self._decisions.list_for_cycle(conn, cycle_result.cycle_id)
                } if cycle_result.cycle_id else {}

                selected_market_id = None
                for evaluation in plan.evaluations:
                    execution_result = None
                    execution_intent = None
                    if evaluation.intent is not None:
                        execution_intent = self._build_execution_intent(
                            shadow_run_id=shadow_run_id,
                            evaluation=evaluation,
                        )
                        if evaluation.status == "WOULD_SUBMIT":
                            execution_result = self._execution_adapter.submit_intent(execution_intent)
                    shadow_order = self._build_shadow_order(
                        shadow_run_id=shadow_run_id,
                        cycle_id=cycle_result.cycle_id,
                        evaluation=evaluation,
                        decision_rows=decision_rows,
                        execution_intent=execution_intent,
                        execution_result=execution_result,
                    )
                    self._shadow_orders.record(conn, shadow_order)
                    self._append_order_event(
                        conn,
                        shadow_order_id=shadow_order.id,
                        old_status=None,
                        new_status="CREATED",
                        reason_code="shadow_order_created",
                        reason_text="shadow live recorded the evaluated live candidate",
                        payload_json={"market_id": shadow_order.market_id},
                    )
                    self._append_order_event(
                        conn,
                        shadow_order_id=shadow_order.id,
                        old_status="CREATED",
                        new_status=shadow_order.status,
                        reason_code=evaluation.reason_code,
                        reason_text=evaluation.reason_text,
                        payload_json={"decision_stage": evaluation.decision_stage},
                    )
                    if shadow_order.status == "WOULD_SUBMIT":
                        selected_market_id = shadow_order.market_id
                        self._record_pending_submission_position(
                            conn,
                            shadow_run_id=shadow_run_id,
                            shadow_order=shadow_order,
                            evaluation=evaluation,
                            execution_intent=execution_intent,
                            execution_result=execution_result,
                        )

                self._shadow_runs.close_run(
                    conn,
                    ShadowRunCloseContract(
                        id=shadow_run_id,
                        ended_at=datetime.now(UTC),
                        status="COMPLETED",
                        markets_seen_count=len(plan.source_markets),
                        markets_ranked_count=len(plan.ranked_candidates),
                        candidates_selected_count=1 if selected_market_id else 0,
                        shadow_orders_count=len(plan.evaluations),
                        metadata_json={
                            "selected_market_id": selected_market_id,
                            "skipped_count": len(plan.skipped),
                            "open_orders_inspected": len(plan.open_orders),
                            "open_orders_error": plan.open_orders_error,
                        },
                    ),
                )
            return ShadowLiveRunResult(
                shadow_run_id=shadow_run_id,
                shadow_orders_count=len(plan.evaluations),
                candidates_selected_count=1 if selected_market_id else 0,
                selected_market_id=selected_market_id,
            )
        except Exception:
            logger.exception("shadow_live_record_cycle_failed cycle_id=%s", cycle_result.cycle_id)
            try:
                with self._factory.connect() as conn, conn.transaction():
                    self._shadow_runs.close_run(
                        conn,
                        ShadowRunCloseContract(
                            id=shadow_run_id,
                            ended_at=datetime.now(UTC),
                            status="FAILED",
                            markets_seen_count=0,
                            markets_ranked_count=0,
                            candidates_selected_count=0,
                            shadow_orders_count=0,
                            metadata_json={"error": "shadow_live_record_cycle_failed"},
                        ),
                    )
            except Exception:
                logger.exception("shadow_live_close_failed shadow_run_id=%s", shadow_run_id)
            return None

    def _build_shadow_order(
        self,
        *,
        shadow_run_id: str,
        cycle_id: str | None,
        evaluation: ExecutionCandidateEvaluation,
        decision_rows: dict[str, dict[str, object]],
        execution_intent: ExecutionIntent | None,
        execution_result,
    ) -> ShadowOrderContract:
        intent = evaluation.intent
        policy_result = "ALLOWED" if evaluation.policy_decision and evaluation.policy_decision.allowed else "BLOCKED"
        if evaluation.policy_decision is None and evaluation.status == "WOULD_SUBMIT":
            policy_result = "ALLOWED"
        guard_result = "ALLOWED" if evaluation.guard_decision and evaluation.guard_decision.allowed else "BLOCKED"
        if evaluation.guard_decision is None and evaluation.status == "WOULD_SUBMIT":
            guard_result = "ALLOWED"
        status = _shadow_status(evaluation, execution_result)
        return ShadowOrderContract(
            id=str(uuid4()),
            shadow_run_id=shadow_run_id,
            cycle_id=cycle_id,
            decision_id=str(decision_rows[evaluation.market_id]["id"]) if evaluation.market_id in decision_rows else None,
            market_id=evaluation.market_id,
            token_id=evaluation.token_id,
            intended_outcome=_intended_outcome(intent.action) if intent else None,
            action=intent.action if intent else "NO_SUBMIT",
            intended_price=float(intent.price) if intent else None,
            intended_size=float(intent.size) if intent else None,
            notional=float(intent.notional_usd) if intent else None,
            guard_result=guard_result,
            execution_policy_result=policy_result,
            status=status,
            raw_intent_json=_intent_payload(intent, evaluation, execution_intent),
            raw_guard_json={
                "allowed": evaluation.guard_decision.allowed if evaluation.guard_decision else evaluation.status == "WOULD_SUBMIT",
                "reasons": list(evaluation.guard_decision.reasons) if evaluation.guard_decision else [],
            },
            raw_policy_json={
                "allowed": evaluation.policy_decision.allowed if evaluation.policy_decision else evaluation.status == "WOULD_SUBMIT",
                "reasons": list(evaluation.policy_decision.reasons) if evaluation.policy_decision else [],
                "stage": evaluation.decision_stage,
                "execution_result": execution_result.to_payload() if execution_result is not None else {
                    "result_status": status,
                    "accepted": False,
                    "reason_code": evaluation.reason_code,
                    "reason_text": evaluation.reason_text,
                },
            },
        )

    def _record_pending_submission_position(
        self,
        conn,
        *,
        shadow_run_id: str,
        shadow_order: ShadowOrderContract,
        evaluation: ExecutionCandidateEvaluation,
        execution_intent: ExecutionIntent | None,
        execution_result,
    ) -> None:
        now = datetime.now(UTC)
        current_mark = shadow_order.intended_price
        shadow_position = ShadowPositionContract(
            id=str(uuid4()),
            shadow_run_id=shadow_run_id,
            shadow_order_id=shadow_order.id,
            market_id=shadow_order.market_id,
            intended_outcome=shadow_order.intended_outcome,
            size=shadow_order.intended_size or 0.0,
            avg_entry=shadow_order.intended_price,
            current_status="PENDING_SUBMISSION",
            mark_price=current_mark,
            unrealized=None,
            realized=None,
            thesis_state="ACTIVE",
            invalidation_state="NONE",
            opened_at=now,
            updated_at=now,
            closed_at=None,
            payload_json={
                "reason": "shadow_live_stops_before_submit",
                "decision_stage": evaluation.decision_stage,
                "execution_contract": execution_intent.to_payload() if execution_intent is not None else None,
                "execution_result": execution_result.to_payload() if execution_result is not None else None,
            },
        )
        self._shadow_positions.record(conn, shadow_position)
        self._shadow_position_events.record(
            conn,
            ShadowPositionEventContract(
                id=str(uuid4()),
                shadow_position_id=shadow_position.id,
                event_at=now,
                event_type="PENDING_SUBMISSION_CREATED",
                reason_code="would_submit",
                reason_text="shadow live reached the submit boundary without submitting",
                payload_json={
                    "shadow_order_id": shadow_order.id,
                    "execution_result": execution_result.to_payload() if execution_result is not None else None,
                },
            ),
        )

    def _append_order_event(
        self,
        conn,
        *,
        shadow_order_id: str,
        old_status: str | None,
        new_status: str,
        reason_code: str,
        reason_text: str,
        payload_json: dict[str, object],
    ) -> None:
        self._shadow_order_events.record(
            conn,
            ShadowOrderEventContract(
                id=str(uuid4()),
                shadow_order_id=shadow_order_id,
                event_at=datetime.now(UTC),
                old_status=old_status,
                new_status=new_status,
                reason_code=reason_code,
                reason_text=reason_text,
                payload_json=payload_json,
            ),
        )


    def _build_execution_intent(
        self,
        *,
        shadow_run_id: str,
        evaluation: ExecutionCandidateEvaluation,
    ) -> ExecutionIntent:
        intent = evaluation.intent
        assert intent is not None
        return ExecutionIntent(
            intent_id=str(uuid4()),
            correlation_id=shadow_run_id,
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
            execution_mode="shadow_live",
            backend_target="shadow_live",
            created_at=datetime.now(UTC),
        )


def _intent_payload(intent, evaluation: ExecutionCandidateEvaluation, execution_intent: ExecutionIntent | None) -> dict[str, object]:
    if intent is None:
        return {
            "decision_stage": evaluation.decision_stage,
            "min_order_size": evaluation.min_order_size,
            "tick_size": evaluation.tick_size,
            "neg_risk": evaluation.neg_risk,
            "balance_info": evaluation.balance_info,
        }
    payload = {
        "market_id": intent.market_id,
        "token_id": intent.token_id,
        "question": intent.question,
        "action": intent.action,
        "side": intent.side,
        "bucket": intent.bucket,
        "price": intent.price,
        "size": intent.size,
        "notional_usd": intent.notional_usd,
        "tick_size": intent.tick_size,
        "neg_risk": intent.neg_risk,
        "min_order_size": evaluation.min_order_size,
        "balance_info": evaluation.balance_info,
    }
    if execution_intent is not None:
        payload["execution_contract"] = execution_intent.to_payload()
    return payload


def _intended_outcome(action: str | None) -> str | None:
    if action == "BUY_YES":
        return "YES"
    if action == "BUY_NO":
        return "NO"
    return None


def _shadow_status(evaluation: ExecutionCandidateEvaluation, execution_result) -> str:
    if execution_result is not None:
        return str(execution_result.result_status)
    if evaluation.decision_stage == "policy_guard":
        guard_reasons = list(evaluation.guard_decision.reasons) if evaluation.guard_decision else []
        if any(reason.startswith("LIVE_") for reason in guard_reasons):
            return "BLOCKED_BY_CONFIG"
        return "BLOCKED_BY_RISK"
    if evaluation.decision_stage in {"orderbook_lookup", "orderbook_check", "intent_build"}:
        return "INVALID_REQUEST"
    if evaluation.status == "WOULD_SUBMIT":
        return "WOULD_SUBMIT"
    return "WOULD_REJECT"
