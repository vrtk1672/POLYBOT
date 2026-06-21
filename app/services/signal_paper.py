from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.paper_run import PaperRunCloseContract, PaperRunOpenContract
from app.domain.contracts.paper_signal import PaperSignalContract
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.services.recorders.phase1_cycle_persistence import (
    build_selection_view,
    normalize_rejection_reason_code,
)
from app.services.capital_allocator import CapitalAllocator, PaperCapitalSource
from app.services.recorders.paper_run_recorder import PaperRunRecorder
from app.services.recorders.paper_signal_recorder import PaperSignalRecorder
from app.services.execution_contract import ExecutionIntent
from app.stage4 import (
    LiveGuard,
    Stage4ExecutionClient,
    build_allowed_universe,
    build_live_order_intent,
    evaluate_execution_policy,
    get_stage4_settings,
    rank_candidates,
)
from app.stage4.order_builder import LiveOrderValidationError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SignalPaperRunResult:
    paper_run_id: str
    signals_emitted_count: int
    candidates_selected_count: int
    selected_market_id: str | None


class SignalPaperService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._paper_runs = PaperRunRecorder()
        self._paper_signals = PaperSignalRecorder()
        self._decisions = DecisionLedgerRepository()
        self._stage4_settings = get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)
        self._guard = LiveGuard(self._stage4_settings)
        self._capital_source = PaperCapitalSource(
            settings=self._settings,
            connection_factory=self._factory,
            stage4_settings=self._stage4_settings,
        )
        self._capital_allocator = CapitalAllocator(self._stage4_settings)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def record_cycle(
        self,
        cycle_result,
        *,
        mode: str = "SIGNAL_PAPER",
    ) -> SignalPaperRunResult | None:
        if not self.enabled:
            return None

        paper_run_id = str(uuid4())
        started_at = datetime.now(UTC)
        selection_view = build_selection_view(cycle_result.top_scored, cycle_result.recommendations)
        try:
            with self._factory.connect() as conn, conn.transaction():
                self._paper_runs.open_run(
                    conn,
                    PaperRunOpenContract(
                        id=paper_run_id,
                        cycle_id=cycle_result.cycle_id,
                        mode=mode,
                        started_at=started_at,
                        status="OPEN",
                        metadata_json={"cycle_id": cycle_result.cycle_id},
                    ),
                )

                decision_rows = {
                    str(row["market_id"]): row
                    for row in self._decisions.list_for_cycle(conn, cycle_result.cycle_id)
                } if cycle_result.cycle_id else {}
                signals = self._build_paper_signals(
                    cycle_result=cycle_result,
                    paper_run_id=paper_run_id,
                    selection_view=selection_view,
                    decision_rows=decision_rows,
                )
                self._paper_signals.record_many(conn, signals)
                selected_count = sum(1 for signal in signals if signal.signal_type == "WOULD_ENTER")
                self._paper_runs.close_run(
                    conn,
                    PaperRunCloseContract(
                        id=paper_run_id,
                        ended_at=datetime.now(UTC),
                        status="COMPLETED",
                        markets_seen_count=len(cycle_result.top_scored),
                        markets_ranked_count=len(selection_view.ranked_entries),
                        candidates_selected_count=selected_count,
                        signals_emitted_count=len(signals),
                        metadata_json={
                            "mode": mode,
                            "selected_market_id": next(
                                (signal.market_id for signal in signals if signal.signal_type == "WOULD_ENTER"),
                                None,
                            ),
                            "cycle_id": cycle_result.cycle_id,
                        },
                    ),
                )
            return SignalPaperRunResult(
                paper_run_id=paper_run_id,
                signals_emitted_count=len(signals),
                candidates_selected_count=selected_count,
                selected_market_id=next(
                    (signal.market_id for signal in signals if signal.signal_type == "WOULD_ENTER"),
                    None,
                ),
            )
        except Exception:
            logger.exception("signal_paper_record_cycle_failed cycle_id=%s", cycle_result.cycle_id)
            try:
                with self._factory.connect() as conn, conn.transaction():
                    self._paper_runs.close_run(
                        conn,
                        PaperRunCloseContract(
                            id=paper_run_id,
                            ended_at=datetime.now(UTC),
                            status="FAILED",
                            markets_seen_count=len(cycle_result.top_scored),
                            markets_ranked_count=len(selection_view.ranked_entries),
                            candidates_selected_count=0,
                            signals_emitted_count=0,
                            metadata_json={"error": "signal_paper_record_cycle_failed"},
                        ),
                    )
            except Exception:
                logger.exception("signal_paper_close_failed paper_run_id=%s", paper_run_id)
            return None

    def _build_paper_signals(
        self,
        *,
        cycle_result,
        paper_run_id: str,
        selection_view,
        decision_rows: dict[str, dict[str, object]],
    ) -> list[PaperSignalContract]:
        source_limit = (
            self._stage4_settings.live_allowed_universe_top_n
            if self._stage4_settings.live_use_adaptive_selector
            else 1
        )
        source_markets = cycle_result.top_scored[:source_limit]
        allowed_universe, skipped = build_allowed_universe(
            source_markets,
            cycle_result.recommendations,
            self._stage4_settings,
        )
        ranked_candidates = rank_candidates(allowed_universe)

        try:
            open_orders = self._execution_client.get_open_orders()
            open_orders_error = None
        except Exception as exc:
            open_orders = []
            open_orders_error = str(exc)

        signals: list[PaperSignalContract] = []
        signaled_market_ids: set[str] = set()
        effective_open_orders = [dict(order) for order in open_orders]
        capital_snapshot = self._capital_source.snapshot()

        for ranked in ranked_candidates:
            candidate = ranked.candidate
            market_id = candidate.market.market_id
            decision_row = decision_rows.get(market_id)

            evaluation = self._evaluate_ranked_candidate(
                ranked,
                effective_open_orders,
                open_orders_error,
                capital_snapshot=capital_snapshot,
            )
            signals.append(
                self._build_signal(
                    paper_run_id=paper_run_id,
                    cycle_id=cycle_result.cycle_id,
                    market_id=market_id,
                    decision_id=decision_row,
                    signal_type=evaluation["signal_type"],
                    intended_outcome=_intended_outcome(candidate.recommendation.action),
                    bucket_type=candidate.bucket,
                    confidence=float(candidate.recommendation.confidence),
                    expected_edge_proxy=_float_or_none(candidate.edge_cents),
                    intended_price=evaluation["intended_price"],
                    intended_size=evaluation["intended_size"],
                    guard_result=evaluation["guard_result"],
                    reason_code=evaluation["reason_code"],
                    reason_text=evaluation["reason_text"],
                    payload_json=evaluation["payload_json"],
                )
            )
            signaled_market_ids.add(market_id)
            if evaluation["signal_type"] == "WOULD_ENTER":
                effective_open_orders.append(
                    {
                        "market_id": market_id,
                        "exposure_type": "ORDER",
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                approved_notional = float(
                    ((evaluation["payload_json"].get("capital_allocation") or {}).get("approved_notional_usd")) or 0.0
                )
                capital_snapshot = self._capital_allocator.reserve_pending_allocation(
                    capital_snapshot,
                    approved_notional_usd=approved_notional,
                )

        for decision in selection_view.decisions:
            if decision.market_id in signaled_market_ids:
                continue
            decision_row = decision_rows.get(decision.market_id)
            signal_type = _map_decision_to_signal(decision.decision_type)
            guard_result = "BLOCKED" if signal_type == "WOULD_BLOCK" else "NOT_EVALUATED"
            signals.append(
                self._build_signal(
                    paper_run_id=paper_run_id,
                    cycle_id=cycle_result.cycle_id,
                    market_id=decision.market_id,
                    decision_id=decision_row,
                    signal_type=signal_type,
                    intended_outcome=None,
                    bucket_type=decision.bucket_type,
                    confidence=decision.confidence,
                    expected_edge_proxy=decision.expected_edge_proxy,
                    intended_price=None,
                    intended_size=None,
                    guard_result=guard_result,
                    reason_code=normalize_rejection_reason_code(decision.reason),
                    reason_text=decision.reason,
                    payload_json={
                        "decision_type": decision.decision_type,
                        "metadata": decision.metadata,
                    },
                )
            )

        signals.sort(key=lambda signal: (signal.signal_type != "WOULD_ENTER", signal.market_id))
        return signals

    def _evaluate_ranked_candidate(
        self,
        ranked,
        open_orders: list[dict[str, object]],
        open_orders_error: str | None,
        *,
        capital_snapshot,
    ) -> dict[str, object]:
        candidate = ranked.candidate
        token_id = candidate.token_ids[1] if candidate.recommendation.action == "BUY_NO" else candidate.token_ids[0]
        try:
            order_book = self._execution_client.get_order_book_summary(token_id)
            tick_size = getattr(order_book, "tick_size", None) or "0.01"
            neg_risk = bool(getattr(order_book, "neg_risk", False))
            min_order_size = float(getattr(order_book, "min_order_size", "0") or 0.0)
        except Exception as exc:
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": "orderbook_lookup_failed",
                "reason_text": str(exc),
                "intended_price": None,
                "intended_size": None,
                "payload_json": {"error": str(exc), "stage": "orderbook_lookup"},
            }

        if self._stage4_settings.live_require_orderbook and min_order_size <= 0:
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": "unusable_orderbook",
                "reason_text": f"min_order_size={min_order_size}",
                "intended_price": None,
                "intended_size": None,
                "payload_json": {"min_order_size": min_order_size, "stage": "orderbook_check"},
            }

        allocation_decision = self._capital_allocator.plan_entry(
            snapshot=capital_snapshot,
            market_id=candidate.item.market.market_id,
            total_rank=float(ranked.total_rank),
            confidence=float(candidate.recommendation.confidence),
        )
        capital_payload = {
            "capital_snapshot": capital_snapshot.to_payload(),
            "capital_allocation": allocation_decision.to_payload(),
        }
        if allocation_decision.action != "ENTER":
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": allocation_decision.reason_code,
                "reason_text": allocation_decision.reason_text,
                "intended_price": None,
                "intended_size": None,
                "payload_json": {
                    "stage": "capital_allocator",
                    **capital_payload,
                },
            }

        balance_info = {
            "collateral": {
                "balance": f"{capital_snapshot.available_cash_usd:.6f}",
                "balance_usd": round(capital_snapshot.available_cash_usd, 6),
            },
            "capital_source_mode": capital_snapshot.source_mode,
            "capital_source_status": capital_snapshot.source_status,
        }

        try:
            intent = build_live_order_intent(
                candidate.item,
                candidate.recommendation,
                bucket=candidate.bucket,
                tick_size=tick_size,
                neg_risk=neg_risk,
                min_order_size=min_order_size,
                max_order_usd=allocation_decision.approved_notional_usd,
                balance_hint=capital_snapshot.available_cash_usd,
            )
        except LiveOrderValidationError as exc:
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": exc.code,
                "reason_text": str(exc),
                "intended_price": None,
                "intended_size": None,
                "payload_json": {
                    "stage": "intent_build",
                    **capital_payload,
                },
            }
        except Exception as exc:
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": "intent_build_failed",
                "reason_text": str(exc),
                "intended_price": None,
                "intended_size": None,
                "payload_json": {
                    "stage": "intent_build",
                    **capital_payload,
                },
            }

        policy_decision = evaluate_execution_policy(
            ranked,
            open_orders=open_orders,
            settings=self._stage4_settings,
            open_orders_error=open_orders_error,
            capacity_mode="paper_safe",
        )
        guard_decision = self._guard.evaluate_order(
            market_id=intent.market_id,
            notional_usd=intent.notional_usd,
            live=False,
            armed=False,
            enforce_notional_cap=False,
        )
        combined_reasons = [*policy_decision.reasons, *guard_decision.reasons]
        if combined_reasons:
            return {
                "signal_type": "WOULD_BLOCK",
                "guard_result": "BLOCKED",
                "reason_code": normalize_rejection_reason_code(combined_reasons[0]),
                "reason_text": "; ".join(combined_reasons),
                "intended_price": float(intent.price),
                "intended_size": float(intent.size),
                "payload_json": {
                    "stage": "policy_guard",
                    "balance_info": balance_info,
                    "recommendation_action": candidate.recommendation.action,
                    **capital_payload,
                    "execution_intent": _build_execution_intent_payload(
                        ranked=ranked,
                        reason_code=normalize_rejection_reason_code(combined_reasons[0]),
                        reason_text="; ".join(combined_reasons),
                        intent=intent,
                        balance_info=balance_info,
                    ),
                    "policy_reasons": policy_decision.reasons,
                    "guard_reasons": guard_decision.reasons,
                    "intent": {
                        "market_id": intent.market_id,
                        "token_id": intent.token_id,
                        "price": intent.price,
                        "size": intent.size,
                        "notional": intent.notional_usd,
                        "min_order_size": min_order_size,
                        "tick_size": tick_size,
                        "neg_risk": neg_risk,
                    },
                },
            }

        return {
            "signal_type": "WOULD_ENTER",
            "guard_result": "ALLOWED",
            "reason_code": "would_enter",
            "reason_text": "candidate passed current guards and would have been attempted",
            "intended_price": float(intent.price),
            "intended_size": float(intent.size),
                "payload_json": {
                    "stage": "would_enter",
                    "balance_info": balance_info,
                    "recommendation_action": candidate.recommendation.action,
                    **capital_payload,
                    "execution_intent": _build_execution_intent_payload(
                        ranked=ranked,
                        reason_code="would_enter",
                        reason_text="candidate passed current guards and would have been attempted",
                        intent=intent,
                        balance_info=balance_info,
                    ),
                    "rank_total": ranked.total_rank,
                    "rank_reason": ranked.reason,
                    "intent": {
                        "market_id": intent.market_id,
                        "token_id": intent.token_id,
                        "price": intent.price,
                        "size": intent.size,
                        "notional": intent.notional_usd,
                        "min_order_size": min_order_size,
                        "tick_size": tick_size,
                        "neg_risk": neg_risk,
                    },
                    "market_price": _float_or_none(_market_price_for_outcome(candidate.item, _intended_outcome(candidate.recommendation.action))),
                    "market_spread": _float_or_none(candidate.item.market.spread),
                    "time_to_close_seconds": _time_to_close_seconds(candidate.item.market),
                },
            }

    def _build_signal(
        self,
        *,
        paper_run_id: str,
        cycle_id: str | None,
        market_id: str,
        decision_id: dict[str, object] | None,
        signal_type: str,
        intended_outcome: str | None,
        bucket_type: str | None,
        confidence: float | None,
        expected_edge_proxy: float | None,
        intended_price: float | None,
        intended_size: float | None,
        guard_result: str,
        reason_code: str,
        reason_text: str,
        payload_json: dict[str, object],
    ) -> PaperSignalContract:
        return PaperSignalContract(
            id=str(uuid4()),
            paper_run_id=paper_run_id,
            cycle_id=cycle_id,
            market_id=market_id,
            decision_id=str(decision_id["id"]) if decision_id else None,
            signal_type=signal_type,
            intended_outcome=intended_outcome,
            trade_type=None,
            bucket_type=bucket_type,
            confidence=confidence,
            expected_edge_proxy=expected_edge_proxy,
            intended_price=intended_price,
            intended_size=intended_size,
            guard_result=guard_result,
            reason_code=reason_code,
            reason_text=reason_text,
            payload_json=payload_json,
        )


def _map_decision_to_signal(decision_type: str) -> str:
    return {
        "SELECT": "WOULD_ENTER",
        "SKIP": "WOULD_SKIP",
        "BLOCK": "WOULD_BLOCK",
        "NO_ACTION": "NO_ACTION",
    }.get(decision_type, "NO_ACTION")


def _intended_outcome(action: str | None) -> str | None:
    if action == "BUY_YES":
        return "YES"
    if action == "BUY_NO":
        return "NO"
    return None


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None else None


def _market_price_for_outcome(item, intended_outcome: str | None) -> float | None:
    if intended_outcome == "YES":
        return _float_or_none(item.market.yes_price)
    if intended_outcome == "NO":
        return _float_or_none(item.market.no_price)
    return None


def _time_to_close_seconds(market) -> int | None:
    from gamma_crawler import hours_remaining

    remaining_hours = hours_remaining(market)
    if remaining_hours is None:
        return None
    return round(remaining_hours * 3600)


def _build_execution_intent_payload(
    *,
    ranked,
    reason_code: str,
    reason_text: str,
    intent,
    balance_info: dict[str, object],
) -> dict[str, object]:
    candidate = ranked.candidate
    execution_intent = ExecutionIntent(
        intent_id=candidate.item.market.market_id,
        correlation_id=candidate.item.market.market_id,
        market_id=intent.market_id,
        side=intent.side,
        order_type="LIMIT",
        size=float(intent.size),
        price_limit=float(intent.price),
        reason_code=reason_code,
        reason_text=reason_text,
        risk_metadata={
            "bucket": intent.bucket,
            "notional_usd": float(intent.notional_usd),
            "tick_size": intent.tick_size,
            "neg_risk": bool(intent.neg_risk),
            "min_order_size": float(intent.min_order_size),
            "balance_info": balance_info,
            "spread": _float_or_none(candidate.item.market.spread),
            "time_to_close_seconds": _time_to_close_seconds(candidate.item.market),
        },
        source_context={
            "token_id": intent.token_id,
            "question": intent.question,
            "action": intent.action,
            "intended_outcome": _intended_outcome(intent.action),
            "recommendation_action": candidate.recommendation.action,
            "market_price": _market_price_for_outcome(candidate.item, _intended_outcome(candidate.recommendation.action)),
            "rank_total": ranked.total_rank,
            "rank_reason": ranked.reason,
        },
        execution_mode="paper",
        backend_target="paper",
        created_at=datetime.now(UTC),
    )
    return execution_intent.to_payload()
