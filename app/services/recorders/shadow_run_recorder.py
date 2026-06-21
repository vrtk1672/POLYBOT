from __future__ import annotations

from app.domain.contracts.shadow_run import ShadowRunCloseContract, ShadowRunOpenContract
from app.repositories.shadow_runs_repository import ShadowRunsRepository


class ShadowRunRecorder:
    def __init__(self, repository: ShadowRunsRepository | None = None) -> None:
        self._repository = repository or ShadowRunsRepository()

    def open_run(self, conn, shadow_run: ShadowRunOpenContract) -> None:
        self._repository.open_run(conn, shadow_run)

    def close_run(self, conn, shadow_run: ShadowRunCloseContract) -> None:
        self._repository.close_run(conn, shadow_run)
