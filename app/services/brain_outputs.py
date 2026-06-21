from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.brain_outputs import (
    BrainOutput,
    BrainOutputConflict,
    BrainOutputDependency,
    brain_output_from_row,
    conflict_from_row,
    dependency_from_row,
)
from app.repositories.brain_output_repository import BrainOutputRepository


class BrainOutputService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: BrainOutputRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or BrainOutputRepository()

    def create_brain_output(self, output: BrainOutput | dict[str, Any]) -> dict[str, Any]:
        item = output if isinstance(output, BrainOutput) else BrainOutput(**output)
        if not self._factory.enabled:
            return item.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_brain_output(conn, item)
        return brain_output_from_row(row).to_api_dict()

    def create_brain_output_with_dependencies(
        self,
        output: BrainOutput | dict[str, Any],
        *,
        dependencies: list[BrainOutputDependency | dict[str, Any]] | None = None,
        conflicts: list[BrainOutputConflict | dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        item = output if isinstance(output, BrainOutput) else BrainOutput(**output)
        dependency_items = [_dependency_for_output(item.brain_output_id, dep) for dep in dependencies or []]
        conflict_items = [_conflict_for_output(item.brain_output_id, conflict) for conflict in conflicts or []]
        if not self._factory.enabled:
            return {
                **item.to_api_dict(),
                "dependencies": [dep.model_dump(mode="json") for dep in dependency_items],
                "conflicts": [conflict.model_dump(mode="json") for conflict in conflict_items],
            }
        with self._factory.connect() as conn, conn.transaction():
            self._validate_references(conn, dependency_items, conflict_items)
            row = self._repository.create_brain_output(conn, item)
            created = brain_output_from_row(row)
            for dependency in dependency_items:
                self._repository.add_dependency(conn, dependency)
            for conflict in conflict_items:
                self._repository.add_conflict(conn, conflict)
        return self._serialize_output(created, dependencies=dependency_items, conflicts=conflict_items)

    def add_dependency(self, brain_output_id: str, dependency: BrainOutputDependency | dict[str, Any]) -> dict[str, Any]:
        item = _dependency_for_output(brain_output_id, dependency)
        if not self._factory.enabled:
            return item.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            self._validate_references(conn, [item], [])
            row = self._repository.add_dependency(conn, item)
        return dependency_from_row(row).model_dump(mode="json")

    def add_conflict(self, brain_output_id: str, conflict: BrainOutputConflict | dict[str, Any]) -> dict[str, Any]:
        item = _conflict_for_output(brain_output_id, conflict)
        if not self._factory.enabled:
            return item.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            self._validate_references(conn, [], [item])
            row = self._repository.add_conflict(conn, item)
        return conflict_from_row(row).model_dump(mode="json")

    def get_brain_output(self, brain_output_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_brain_output(conn, brain_output_id)
            if not row:
                return None
            dependencies = self._repository.list_dependencies(conn, brain_output_id)
            conflicts = self._repository.list_conflicts_for_output(conn, brain_output_id)
        return self._serialize_output(
            brain_output_from_row(row),
            dependencies=[dependency_from_row(dict(row)) for row in dependencies],
            conflicts=[conflict_from_row(dict(row)) for row in conflicts],
        )

    def list_recent_brain_outputs(
        self,
        *,
        limit: int = 50,
        brain: str | None = None,
        market_id: str | None = None,
        position_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_recent_brain_outputs(
                conn,
                limit=limit,
                brain=brain,
                market_id=market_id,
                position_id=position_id,
                status=status,
            )
        return [brain_output_from_row(dict(row)).to_api_dict() for row in rows]

    def list_outputs_by_market(self, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_outputs_by_market(conn, market_id, limit=limit)
        return [brain_output_from_row(dict(row)).to_api_dict() for row in rows]

    def list_outputs_by_brain(self, brain: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_outputs_by_brain(conn, brain, limit=limit)
        return [brain_output_from_row(dict(row)).to_api_dict() for row in rows]

    def list_outputs_by_signal_dependency(self, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_outputs_by_signal_dependency(conn, signal_id, limit=limit)
        return [brain_output_from_row(dict(row)).to_api_dict() for row in rows]

    def list_conflicts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_conflicts(conn, limit=limit)
        return [conflict_from_row(dict(row)).model_dump(mode="json") for row in rows]

    def get_brain_output_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": datetime.now().astimezone().isoformat(),
            "total_outputs_24h": summary["total_outputs_24h"],
            "active_outputs": summary["active_outputs"],
            "expired_outputs": summary["expired_outputs"],
            "outputs_by_brain": [_json_safe(dict(row)) for row in summary["outputs_by_brain"]],
            "outputs_by_status": [_json_safe(dict(row)) for row in summary["outputs_by_status"]],
            "latest_outputs": [_json_safe(brain_output_from_row(dict(row)).to_api_dict()) for row in summary["latest_outputs"]],
            "recent_conflicts": [_json_safe(conflict_from_row(dict(row)).model_dump(mode="json")) for row in summary["recent_conflicts"]],
            "outputs_without_dependencies": summary["outputs_without_dependencies"],
            "signals_with_outputs": summary["signals_with_outputs"],
        }

    def _validate_references(
        self,
        conn,
        dependencies: list[BrainOutputDependency],
        conflicts: list[BrainOutputConflict],
    ) -> None:
        for dependency in dependencies:
            if dependency.dependency_type == "signal" and not self._repository.signal_exists(conn, dependency.dependency_id):
                raise ValueError(f"signal dependency does not exist: {dependency.dependency_id}")
            if dependency.dependency_type == "brain_output" and not self._repository.brain_output_exists(conn, dependency.dependency_id):
                raise ValueError(f"brain output dependency does not exist: {dependency.dependency_id}")
        for conflict in conflicts:
            if conflict.conflicts_with_type == "signal" and not self._repository.signal_exists(conn, conflict.conflicts_with_id):
                raise ValueError(f"signal conflict target does not exist: {conflict.conflicts_with_id}")
            if conflict.conflicts_with_type == "brain_output" and not self._repository.brain_output_exists(conn, conflict.conflicts_with_id):
                raise ValueError(f"brain output conflict target does not exist: {conflict.conflicts_with_id}")

    def _serialize_output(
        self,
        output: BrainOutput,
        *,
        dependencies: list[BrainOutputDependency],
        conflicts: list[BrainOutputConflict],
    ) -> dict[str, Any]:
        return {
            **output.to_api_dict(),
            "dependencies": [dependency.model_dump(mode="json") for dependency in dependencies],
            "conflicts": [conflict.model_dump(mode="json") for conflict in conflicts],
        }


def _dependency_for_output(brain_output_id: str, dependency: BrainOutputDependency | dict[str, Any]) -> BrainOutputDependency:
    data = dependency.model_dump() if isinstance(dependency, BrainOutputDependency) else dict(dependency)
    data["brain_output_id"] = brain_output_id
    return BrainOutputDependency(**data)


def _conflict_for_output(brain_output_id: str, conflict: BrainOutputConflict | dict[str, Any]) -> BrainOutputConflict:
    data = conflict.model_dump() if isinstance(conflict, BrainOutputConflict) else dict(conflict)
    data["brain_output_id"] = brain_output_id
    return BrainOutputConflict(**data)


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "total_outputs_24h": 0,
        "active_outputs": 0,
        "expired_outputs": 0,
        "outputs_by_brain": [],
        "outputs_by_status": [],
        "latest_outputs": [],
        "recent_conflicts": [],
        "outputs_without_dependencies": 0,
        "signals_with_outputs": 0,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
