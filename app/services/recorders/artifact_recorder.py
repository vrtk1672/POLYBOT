from __future__ import annotations

from app.domain.contracts.artifact import RunArtifactContract
from app.repositories.run_artifacts_repository import RunArtifactsRepository


class ArtifactRecorder:
    def __init__(self, repository: RunArtifactsRepository | None = None) -> None:
        self._repository = repository or RunArtifactsRepository()

    def record(self, conn, artifact: RunArtifactContract) -> None:
        self._repository.upsert(conn, artifact)
