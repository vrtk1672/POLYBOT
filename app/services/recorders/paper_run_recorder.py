from __future__ import annotations

from app.domain.contracts.paper_run import PaperRunCloseContract, PaperRunOpenContract
from app.repositories.paper_runs_repository import PaperRunsRepository


class PaperRunRecorder:
    def __init__(self, repository: PaperRunsRepository | None = None) -> None:
        self._repository = repository or PaperRunsRepository()

    def open_run(self, conn, paper_run: PaperRunOpenContract) -> None:
        self._repository.open_run(conn, paper_run)

    def close_run(self, conn, paper_run: PaperRunCloseContract) -> None:
        self._repository.close_run(conn, paper_run)
