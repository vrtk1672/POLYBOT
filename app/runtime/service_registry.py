from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.service_health_repository import ServiceHealthRepository


DEFAULT_SERVICES = {
    "fastapi": "api",
    "scheduler": "runtime",
    "market_service": "runtime",
    "postgres": "persistence",
    "intelligence_runtime": "runtime",
    "paper_runtime": "runtime",
    "dashboard": "api",
    "telegram": "control",
    "stage4_guard": "safety",
    "event_bus": "event_mesh",
    "event_store": "event_mesh",
    "event_dispatcher": "event_mesh",
    "data_foundation": "data",
    "ai_brain": "intelligence",
}


class ServiceRegistry:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: ServiceHealthRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or ServiceHealthRepository()

    def register_defaults(self) -> None:
        for service_name, service_type in DEFAULT_SERVICES.items():
            self.register_service(service_name, service_type)

    def register_service(self, service_name: str, service_type: str, status: str = "STOPPED") -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.upsert_service_health(
                conn,
                service_name=service_name,
                service_type=service_type,
                status=status,
            )

    def heartbeat(self, service_name: str, status: str = "RUNNING") -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_heartbeat(conn, service_name, status=status)

    def mark_success(self, service_name: str, details: dict[str, object] | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_success(conn, service_name, details)

    def mark_error(self, service_name: str, details: dict[str, object] | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_error(conn, service_name, details)

    def list_services(self) -> list[dict[str, object]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return [dict(row) for row in self._repository.list_services(conn)]
