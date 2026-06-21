from __future__ import annotations

from app.domain.contracts.resolution_analysis_run import (
    ResolutionAnalysisRunCloseContract,
    ResolutionAnalysisRunOpenContract,
)
from app.repositories.resolution_analysis_runs_repository import ResolutionAnalysisRunsRepository


class ResolutionAnalysisRunRecorder:
    def __init__(self, repository: ResolutionAnalysisRunsRepository | None = None) -> None:
        self._repository = repository or ResolutionAnalysisRunsRepository()

    def open_run(self, conn, run: ResolutionAnalysisRunOpenContract) -> None:
        self._repository.open_run(conn, run)

    def close_run(self, conn, run: ResolutionAnalysisRunCloseContract) -> None:
        self._repository.close_run(conn, run)
