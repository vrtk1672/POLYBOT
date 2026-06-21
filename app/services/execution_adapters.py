from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from app.services.execution_contract import ExecutionAdapter, ExecutionIntent, ExecutionResult
from app.stage4 import Stage4ExecutionClient, Stage4Settings, get_stage4_settings
from app.stage4.order_builder import LiveOrderIntent

PARTIAL_FILL_SPREAD_THRESHOLD = 0.03
OPEN_SPREAD_THRESHOLD = 0.06
EXPIRE_SPREAD_THRESHOLD = 0.10
STALE_WINDOW_SECONDS = 900
EXPIRY_CLOSE_SECONDS = 300


class PaperExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        *,
        settings: Stage4Settings | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._settings)

    def submit_intent(self, intent: ExecutionIntent) -> ExecutionResult:
        risk_metadata = dict(intent.risk_metadata)
        source_context = dict(intent.source_context)
        token_id = source_context.get("token_id")
        min_order_size = _as_float(risk_metadata.get("min_order_size")) or 0.0
        if token_id:
            try:
                order_book = self._execution_client.get_order_book_summary(str(token_id))
                min_order_size = float(getattr(order_book, "min_order_size", str(min_order_size)) or min_order_size)
            except Exception as exc:
                risk_metadata["orderbook_refresh_error"] = str(exc)

        spread = _as_float(risk_metadata.get("spread"))
        time_to_close_seconds = _as_int(risk_metadata.get("time_to_close_seconds"))
        final_status, fill_ratio, reason_code, reason_text, stale_at = _decide_simulated_order_outcome(
            intended_size=intent.size,
            min_order_size=min_order_size,
            spread=spread,
            time_to_close_seconds=time_to_close_seconds,
        )
        filled_size = round(intent.size * fill_ratio, 6)
        remaining_size = round(max(intent.size - filled_size, 0.0), 6)
        avg_fill_price = intent.price_limit if filled_size > 0 else None
        accepted = final_status in {"FILLED", "PARTIALLY_FILLED", "OPEN"}
        return ExecutionResult(
            intent_id=intent.intent_id,
            correlation_id=intent.correlation_id,
            accepted=accepted,
            result_status=final_status,
            filled_size=filled_size,
            avg_fill_price=avg_fill_price,
            remaining_size=remaining_size,
            external_order_id=None,
            error_code=None if accepted else reason_code,
            error_text=None if accepted else reason_text,
            raw_result_json={
                "adapter": "paper",
                "execution_contract_version": "v1",
                "reason_code": reason_code,
                "reason_text": reason_text,
                "fill_ratio": fill_ratio,
                "stale_at": stale_at.isoformat() if stale_at else None,
                "min_order_size": min_order_size,
                "spread": spread,
                "time_to_close_seconds": time_to_close_seconds,
                "risk_metadata": risk_metadata,
            },
            processed_at=datetime.now(UTC),
        )


class LiveExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        *,
        settings: Stage4Settings | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._settings)

    def submit_intent(self, intent: ExecutionIntent) -> ExecutionResult:
        backend = (intent.backend_target or "live").strip().lower()
        live_intent = _build_live_order_intent(intent)
        auth_context = self._execution_client.auth_context()

        if backend == "shadow_live":
            try:
                signed_order = self._execution_client.create_signed_order(live_intent)
            except Exception as exc:
                return ExecutionResult(
                    intent_id=intent.intent_id,
                    correlation_id=intent.correlation_id,
                    accepted=False,
                    result_status="INVALID_REQUEST",
                    filled_size=0.0,
                    avg_fill_price=None,
                    remaining_size=float(intent.size),
                    external_order_id=None,
                    error_code="shadow_request_build_failed",
                    error_text=str(exc),
                    raw_result_json={
                        "adapter": "live",
                        "execution_contract_version": "v1",
                        "shadow_mode": True,
                        "auth_context": auth_context,
                        "order_summary": asdict(live_intent),
                    },
                    processed_at=datetime.now(UTC),
                )
            return ExecutionResult(
                intent_id=intent.intent_id,
                correlation_id=intent.correlation_id,
                accepted=True,
                result_status="WOULD_SUBMIT",
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(intent.size),
                external_order_id=None,
                error_code=None,
                error_text=None,
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "shadow_mode": True,
                    "auth_context": auth_context,
                    "order_summary": asdict(live_intent),
                    "live_request_payload": _serialize_shadow_payload(signed_order),
                },
                processed_at=datetime.now(UTC),
            )

        config_errors = _validate_live_adapter_config(intent=intent, settings=self._settings)
        if config_errors:
            return ExecutionResult(
                intent_id=intent.intent_id,
                correlation_id=intent.correlation_id,
                accepted=False,
                result_status="BLOCKED_BY_CONFIG",
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(intent.size),
                external_order_id=None,
                error_code="live_cage_blocked",
                error_text="; ".join(config_errors),
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "auth_context": auth_context,
                    "order_summary": asdict(live_intent),
                    "config_errors": config_errors,
                    "live_trading_enabled": self._settings.live_trading_enabled,
                    "live_kill_switch": self._settings.live_kill_switch,
                    "live_market_whitelist": list(self._settings.live_market_whitelist),
                },
                processed_at=datetime.now(UTC),
            )

        try:
            signed_order = self._execution_client.create_signed_order(live_intent)
        except Exception as exc:
            return ExecutionResult(
                intent_id=intent.intent_id,
                correlation_id=intent.correlation_id,
                accepted=False,
                result_status="INVALID_REQUEST",
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(intent.size),
                external_order_id=None,
                error_code="live_request_build_failed",
                error_text=str(exc),
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "auth_context": auth_context,
                    "order_summary": asdict(live_intent),
                },
                processed_at=datetime.now(UTC),
            )

        try:
            response = self._execution_client.submit_order(live_intent)
        except Exception as exc:
            details = getattr(exc, "details", None)
            return ExecutionResult(
                intent_id=intent.intent_id,
                correlation_id=intent.correlation_id,
                accepted=False,
                result_status="REJECTED",
                filled_size=0.0,
                avg_fill_price=None,
                remaining_size=float(intent.size),
                external_order_id=None,
                error_code="live_submit_failed",
                error_text=str(exc),
                raw_result_json={
                    "adapter": "live",
                    "execution_contract_version": "v1",
                    "auth_context": auth_context,
                    "order_summary": asdict(live_intent),
                    "live_request_payload": _serialize_shadow_payload(signed_order),
                    "live_response_error": details if isinstance(details, dict) else {"error": str(exc)},
                },
                processed_at=datetime.now(UTC),
            )

        response_payload = response.get("response", {}) if isinstance(response, dict) else {}
        result_status = _normalize_live_result_status(response_payload)
        return ExecutionResult(
            intent_id=intent.intent_id,
            correlation_id=intent.correlation_id,
            accepted=result_status not in {"REJECTED", "ERROR"},
            result_status=result_status,
            filled_size=float(intent.size) if result_status == "FILLED" else 0.0,
            avg_fill_price=float(intent.price_limit) if result_status == "FILLED" else None,
            remaining_size=0.0 if result_status == "FILLED" else float(intent.size),
            external_order_id=_extract_external_order_id(response_payload),
            error_code=None if result_status not in {"REJECTED", "ERROR"} else "live_submit_failed",
            error_text=None if result_status not in {"REJECTED", "ERROR"} else str(response_payload),
            raw_result_json={
                "adapter": "live",
                "execution_contract_version": "v1",
                "auth_context": auth_context,
                "order_summary": asdict(live_intent),
                "live_request_payload": _serialize_shadow_payload(signed_order),
                "live_response": response,
            },
            processed_at=datetime.now(UTC),
        )


def build_execution_adapter(
    *,
    backend_target: str | None = None,
    settings: Stage4Settings | None = None,
    execution_client: Stage4ExecutionClient | None = None,
) -> ExecutionAdapter:
    selected_backend = (
        backend_target
        or os.getenv("POLYBOT_EXECUTION_BACKEND")
        or os.getenv("EXECUTION_BACKEND")
        or "paper"
    ).strip().lower()
    if selected_backend == "live":
        return LiveExecutionAdapter(settings=settings, execution_client=execution_client)
    if selected_backend == "shadow_live":
        return LiveExecutionAdapter(settings=settings, execution_client=execution_client)
    return PaperExecutionAdapter(settings=settings, execution_client=execution_client)


def _decide_simulated_order_outcome(
    *,
    intended_size: float,
    min_order_size: float,
    spread: float | None,
    time_to_close_seconds: int | None,
) -> tuple[str, float, str, str, datetime | None]:
    now = datetime.now(UTC)
    if intended_size <= 0:
        return ("BLOCKED_MIN_SIZE", 0.0, "non_positive_size", "intended size must be positive", None)
    if min_order_size > 0 and intended_size < min_order_size:
        return (
            "BLOCKED_MIN_SIZE",
            0.0,
            "below_minimum_size",
            f"intended size {intended_size:.3f} is below min_order_size {min_order_size:.3f}",
            None,
        )
    if time_to_close_seconds is not None and time_to_close_seconds <= EXPIRY_CLOSE_SECONDS:
        return ("EXPIRED", 0.0, "too_close_to_market_close", "order expired because market close is too near", now)
    if spread is not None and spread >= EXPIRE_SPREAD_THRESHOLD:
        return ("EXPIRED", 0.0, "stale_spread_too_wide", f"spread {spread:.4f} is too wide for paper execution", now)
    if spread is not None and spread >= OPEN_SPREAD_THRESHOLD:
        return (
            "OPEN",
            0.0,
            "pending_wide_spread",
            f"spread {spread:.4f} leaves the order pending",
            now + timedelta(seconds=STALE_WINDOW_SECONDS),
        )
    if spread is not None and spread >= PARTIAL_FILL_SPREAD_THRESHOLD:
        return (
            "PARTIALLY_FILLED",
            0.5,
            "partial_fill_on_moderate_spread",
            f"spread {spread:.4f} supports only a partial paper fill",
            now + timedelta(seconds=STALE_WINDOW_SECONDS),
        )
    return ("FILLED", 1.0, "filled_at_current_mark", "order would fill at the current cycle mark", None)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _build_live_order_intent(intent: ExecutionIntent) -> LiveOrderIntent:
    source_context = dict(intent.source_context)
    risk_metadata = dict(intent.risk_metadata)
    return LiveOrderIntent(
        market_id=intent.market_id,
        token_id=str(source_context.get("token_id") or ""),
        question=str(source_context.get("question") or intent.market_id),
        action=str(source_context.get("action") or "BUY_YES"),
        side=intent.side,
        bucket=str(risk_metadata.get("bucket") or "high"),
        price=float(intent.price_limit or 0.0),
        size=float(intent.size),
        notional_usd=float(risk_metadata.get("notional_usd") or 0.0),
        tick_size=str(risk_metadata.get("tick_size") or "0.01"),
        neg_risk=bool(risk_metadata.get("neg_risk") or False),
        min_order_size=float(risk_metadata.get("min_order_size") or 0.0),
    )


def _serialize_shadow_payload(payload: object) -> object:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if hasattr(payload, "dict"):
        return payload.dict()
    if hasattr(payload, "__dict__"):
        return dict(payload.__dict__)
    return {"repr": repr(payload)}


def _validate_live_adapter_config(
    *,
    intent: ExecutionIntent,
    settings: Stage4Settings,
) -> list[str]:
    errors: list[str] = []
    if not settings.live_trading_enabled:
        errors.append("LIVE_TRADING_ENABLED is false")
    if settings.live_kill_switch:
        errors.append("LIVE_KILL_SWITCH is enabled")
    if not settings.live_market_whitelist:
        errors.append("LIVE_MARKET_WHITELIST must be non-empty in live mode")
    elif intent.market_id not in settings.live_market_whitelist:
        errors.append(f"market {intent.market_id} is not in LIVE_MARKET_WHITELIST")
    if (intent.backend_target or "").strip().lower() != "live":
        errors.append("backend_target must be live for real live execution")
    return errors


def _extract_external_order_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("orderID") or payload.get("order_id") or payload.get("id")
    return str(value) if value else None


def _normalize_live_result_status(payload: object) -> str:
    if not isinstance(payload, dict):
        return "UNKNOWN"
    status = str(payload.get("status") or payload.get("state") or payload.get("orderStatus") or "").upper()
    if status in {"FILLED", "MATCHED"}:
        return "FILLED"
    if status in {"LIVE", "OPEN", "ACTIVE"}:
        return "LIVE"
    if status in {"PARTIALLY_FILLED", "PARTIAL"}:
        return "PARTIALLY_FILLED"
    if status in {"REJECTED", "CANCELED", "CANCELLED"}:
        return status
    if payload.get("success") is True:
        return "SUBMITTED"
    if payload.get("success") is False:
        return "ERROR"
    return status or "UNKNOWN"
