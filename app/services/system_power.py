from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_state_repository import RuntimeStateRepository, SystemPowerRepository
from app.runtime.modes import RuntimeMode, get_permissions_for_mode
from app.runtime.system_power import SystemPower, parse_system_power
from app.stage4 import get_stage4_settings


class SystemPowerService:
    """Canonical operator-facing ON/OFF control for POLYBOT runtime life."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SystemPowerRepository | None = None,
        state_repository: RuntimeStateRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SystemPowerRepository()
        self._state_repository = state_repository or RuntimeStateRepository()

    def get_power_state(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _unavailable_state()
        with self._factory.connect() as conn:
            state = self._state_repository.initialize_if_missing(conn)
            row = self._repository.get_current_power_row(conn)
        return self._state_payload(dict(row or {}), current_mode=state.current_mode.value)

    def turn_on(self, *, actor: str, reason: str, correlation_id: str | None = None) -> dict[str, Any]:
        return self._transition(SystemPower.ON, actor=actor, reason=reason, correlation_id=correlation_id)

    def turn_off(self, *, actor: str, reason: str, correlation_id: str | None = None) -> dict[str, Any]:
        return self._transition(SystemPower.OFF, actor=actor, reason=reason, correlation_id=correlation_id)

    def is_runtime_work_allowed(self) -> bool:
        try:
            return self.get_power_state()["runtime_work_allowed"] is True
        except Exception:
            return False

    def get_dashboard_summary(self) -> dict[str, Any]:
        payload = self.get_power_state()
        return {
            "mock_data": False,
            "status": "OK" if payload.get("power") in {"ON", "OFF"} else "ERROR",
            "system_power": payload.get("power"),
            "power": payload.get("power"),
            "last_transition_at": payload.get("last_transition_at"),
            "actor": payload.get("actor"),
            "reason": payload.get("reason"),
            "correlation_id": payload.get("correlation_id"),
            "runtime_work_allowed": payload.get("runtime_work_allowed"),
            "scheduler_allowed": payload.get("scheduler_allowed"),
            "market_service_allowed": payload.get("market_service_allowed"),
            "data_intake_allowed": payload.get("data_intake_allowed"),
            "neurons_allowed": payload.get("neurons_allowed"),
            "brains_allowed": payload.get("brains_allowed"),
            "dialogue_allowed": payload.get("dialogue_allowed"),
            "paper_allowed": payload.get("paper_allowed"),
            "paper_simulation_allowed": payload.get("paper_simulation_allowed"),
            "paper_execution_allowed": payload.get("paper_execution_allowed"),
            "shadow_allowed": payload.get("shadow_allowed"),
            "live_allowed": payload.get("live_allowed"),
            "components": payload.get("components", {}),
            "safety": payload.get("safety", {}),
            "safety_warning": "live trading disabled as expected" if not payload.get("live_allowed") else "live trading unexpectedly allowed",
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def _transition(self, target: SystemPower, *, actor: str, reason: str, correlation_id: str | None) -> dict[str, Any]:
        actor = (actor or "").strip()
        reason = (reason or "").strip()
        if not actor:
            raise ValueError("actor is required")
        if not reason:
            raise ValueError("reason is required")
        correlation_id = (correlation_id or f"system_power_{uuid4().hex}").strip()
        transition_id = f"system_power_transition_{uuid4().hex}"
        with self._factory.connect() as conn, conn.transaction():
            state = self._state_repository.initialize_if_missing(conn)
            old_power = parse_system_power(state.system_power)
            row = self._repository.update_power(
                conn,
                old_power=old_power,
                new_power=target,
                actor=actor,
                reason=reason,
                correlation_id=correlation_id,
                transition_id=transition_id,
                result="IDEMPOTENT" if old_power == target else "OK",
            )
            self._state_repository.insert_history(
                conn,
                from_mode=state.current_mode,
                to_mode=state.current_mode,
                action=f"SYSTEM_{target.value}",
                reason=reason,
                actor=actor,
                allowed=True,
                correlation_id=correlation_id,
                metadata={
                    "system_power_transition_id": transition_id,
                    "old_power": old_power.value,
                    "new_power": target.value,
                    "power_only_transition": True,
                },
            )
        payload = self._state_payload(dict(row), current_mode=state.current_mode.value)
        payload["transition_id"] = transition_id
        return payload

    def _state_payload(self, row: dict[str, Any], *, current_mode: str | None = None) -> dict[str, Any]:
        power = parse_system_power(row.get("system_power") or SystemPower.ON)
        runtime_allowed = power == SystemPower.ON
        permissions = get_permissions_for_mode(current_mode or RuntimeMode.DATA_ONLY)
        stage4 = get_stage4_settings()
        live_allowed = False
        shadow_allowed = False
        paper_allowed = bool(runtime_allowed and permissions.can_run_paper_engine)
        paper_simulation_allowed = bool(runtime_allowed and permissions.can_run_paper_simulation)
        return _json_safe(
            {
                "power": power.value,
                "system_power": power.value,
                "runtime_work_allowed": runtime_allowed,
                "last_transition_at": row.get("system_power_transition_at"),
                "actor": row.get("system_power_actor"),
                "reason": row.get("system_power_reason"),
                "correlation_id": row.get("system_power_correlation_id"),
                "current_mode": current_mode,
                "scheduler_allowed": runtime_allowed,
                "market_service_allowed": runtime_allowed,
                "data_intake_allowed": runtime_allowed,
                "neurons_allowed": runtime_allowed,
                "brains_allowed": runtime_allowed,
                "dialogue_allowed": runtime_allowed,
                "paper_allowed": paper_allowed,
                "paper_simulation_allowed": paper_simulation_allowed,
                "paper_execution_allowed": paper_simulation_allowed,
                "shadow_allowed": shadow_allowed,
                "live_allowed": live_allowed,
                "components": {
                    "scheduler": {"allowed": runtime_allowed, "active": runtime_allowed, "wired": True},
                    "market_service": {"allowed": runtime_allowed, "active": runtime_allowed, "wired": True},
                    "data_foundation": {"allowed": runtime_allowed, "active": runtime_allowed, "wired": True},
                    "orderbook_refresh": {"allowed": runtime_allowed, "active": False, "wired": False},
                    "neuron_producers": {"allowed": runtime_allowed, "active": False, "wired": False},
                    "brain_producer": {"allowed": runtime_allowed, "active": False, "wired": False},
                    "coordinator": {"allowed": runtime_allowed, "active": False, "wired": False},
                    "thesis_builder": {"allowed": runtime_allowed, "active": False, "wired": False},
                    "risk": {"allowed": runtime_allowed, "active": False, "wired": True},
                    "exit": {"allowed": runtime_allowed, "active": False, "wired": True},
                    "eligibility": {"allowed": runtime_allowed, "active": False, "wired": True},
                    "no_trade": {"allowed": runtime_allowed, "active": False, "wired": True},
                    "dashboard_truth": {"allowed": True, "active": True, "wired": True},
                    "brain_dialogue_feed": {"allowed": runtime_allowed, "active": False, "wired": True},
                    "paper_simulation": {"allowed": paper_simulation_allowed, "active": False, "wired": True},
                    "paper": {"allowed": paper_allowed, "active": False, "wired": True},
                    "shadow": {"allowed": False, "active": False, "wired": False},
                    "live": {"allowed": False, "active": False, "wired": False},
                },
                "safety": {
                    "live_trading_enabled": bool(stage4.live_trading_enabled),
                    "execution_allowed": False,
                    "orders_allowed": False,
                    "paper_allowed": paper_allowed,
                    "paper_simulation_allowed": paper_simulation_allowed,
                    "shadow_allowed": False,
                    "live_allowed": False,
                    "real_orders_allowed": False,
                    "live_disabled_expected": not bool(stage4.live_trading_enabled),
                },
            }
        )


def _unavailable_state() -> dict[str, Any]:
    return {
        "power": "OFF",
        "system_power": "OFF",
        "runtime_work_allowed": False,
        "last_transition_at": None,
        "actor": None,
        "reason": "database unavailable",
        "correlation_id": None,
        "safety": {"live_trading_enabled": False, "execution_allowed": False, "orders_allowed": False},
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
