from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.source_refresh_orchestrator import SourceRefreshOrchestrator


class SourceRefreshStatusService:
    """Read-only Control Center surface for continuous source refresh truth."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_status(self) -> dict[str, object]:
        return SourceRefreshOrchestrator(connection_factory=self._factory).status()
