from __future__ import annotations

from app.domain.contracts.resolution_analysis import ResolutionAnalysisContract
from app.repositories.resolution_analyses_repository import ResolutionAnalysesRepository


class ResolutionAnalysisRecorder:
    def __init__(self, repository: ResolutionAnalysesRepository | None = None) -> None:
        self._repository = repository or ResolutionAnalysesRepository()

    def record(self, conn, analysis: ResolutionAnalysisContract) -> None:
        self._repository.insert(conn, analysis)
