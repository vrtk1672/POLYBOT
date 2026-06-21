from __future__ import annotations

import os

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.runtime.service_registry import ServiceRegistry
from app.runtime.state_governor import StateGovernor


class SafeStartupPolicy:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = StateGovernor(connection_factory=self._factory)
        self._registry = ServiceRegistry(connection_factory=self._factory)

    def initialize(self) -> dict[str, object]:
        if not self._factory.enabled:
            return {"status": "ERROR", "current_mode": None, "warnings": ["database unavailable; runtime fail-safe active"]}
        warnings: list[str] = []
        env_mode = (os.getenv("POLYBOT_RUNTIME_MODE") or "").strip().lower()
        try:
            state = self._governor.ensure_initial_state()
            self._registry.register_defaults()
            self._registry.heartbeat("fastapi", status="RUNNING")
            self._registry.heartbeat("postgres", status="HEALTHY")
            if env_mode in {"live", "live_caged", "small_live", "attack_mode"} and state.current_mode.value == "DATA_ONLY":
                warnings.append("env requested elevated mode but persisted state is DATA_ONLY; live was not enabled")
                self._record_incident(
                    severity="MEDIUM",
                    incident_type="SAFE_STARTUP_DOWNGRADE",
                    message="Safe startup kept runtime in DATA_ONLY despite elevated env mode.",
                    details={"env_mode": env_mode},
                )
            return {"status": "OK", "current_mode": state.current_mode.value, "warnings": warnings}
        except Exception as exc:
            return {"status": "ERROR", "current_mode": None, "warnings": [f"safe startup failed: {exc}"]}

    def _record_incident(self, *, severity: str, incident_type: str, message: str, details: dict[str, object]) -> None:
        with self._factory.connect() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO runtime_incidents (severity, source_service, incident_type, message, details_json)
                VALUES (%s, 'safe_startup', %s, %s, %s)
                """,
                (severity, incident_type, message, Jsonb(details)),
            )
