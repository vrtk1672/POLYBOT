from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.position_thesis import (
    PositionThesisProfile,
    calculate_thesis_validation,
    position_thesis_profile_from_row,
)
from app.repositories.position_thesis_repository import PositionThesisRepository


class PositionThesisService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: PositionThesisRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or PositionThesisRepository()

    def create_position_thesis_profile(self, profile: PositionThesisProfile | dict[str, Any]) -> dict[str, Any]:
        item = profile if isinstance(profile, PositionThesisProfile) else PositionThesisProfile(**profile)
        item = item.with_validation()
        validation = calculate_thesis_validation(item)
        if not self._factory.enabled:
            return {**item.to_api_dict(), "validation": validation.to_api_dict()}
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_profile(conn, item)
            self._repository.record_validation_event(conn, thesis_id=item.thesis_id, validation=validation)
        created = position_thesis_profile_from_row(row)
        return {**created.to_api_dict(), "validation": validation.to_api_dict()}

    def update_position_thesis_profile(self, thesis_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_thesis_by_id(thesis_id)
        if current is None:
            raise ValueError(f"thesis profile not found: {thesis_id}")
        merged = {**current, **updates, "thesis_id": thesis_id}
        item = PositionThesisProfile(**merged).with_validation()
        validation = calculate_thesis_validation(item)
        if not self._factory.enabled:
            return {**item.to_api_dict(), "validation": validation.to_api_dict()}
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.update_profile(conn, item)
            self._repository.record_validation_event(conn, thesis_id=thesis_id, validation=validation)
        updated = position_thesis_profile_from_row(row)
        return {**updated.to_api_dict(), "validation": validation.to_api_dict()}

    def get_thesis_by_id(self, thesis_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_by_id(conn, thesis_id)
        return position_thesis_profile_from_row(row).to_api_dict() if row else None

    def get_thesis_by_position(self, position_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_by_position(conn, position_id)
        return position_thesis_profile_from_row(row).to_api_dict() if row else None

    def list_thesis_profiles(
        self,
        *,
        status: str | None = None,
        market_id: str | None = None,
        position_id: str | None = None,
        paper_ready: bool | None = None,
        live_ready: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_profiles(
                conn,
                status=status,
                market_id=market_id,
                position_id=position_id,
                paper_ready=paper_ready,
                live_ready=live_ready,
                limit=limit,
            )
        return [position_thesis_profile_from_row(dict(row)).to_api_dict() for row in rows]

    def validate_thesis_profile(self, thesis_id: str) -> dict[str, Any]:
        current = self.get_thesis_by_id(thesis_id)
        if current is None:
            raise ValueError(f"thesis profile not found: {thesis_id}")
        item = PositionThesisProfile(**current).with_validation()
        validation = calculate_thesis_validation(item)
        if not self._factory.enabled:
            return validation.to_api_dict()
        with self._factory.connect() as conn, conn.transaction():
            self._repository.update_profile(conn, item)
            self._repository.record_validation_event(conn, thesis_id=thesis_id, validation=validation)
        return validation.to_api_dict()

    def mark_thesis_needs_review(self, thesis_id: str) -> dict[str, Any]:
        return self.update_position_thesis_profile(thesis_id, {"status": "NEEDS_REVIEW"})

    def mark_thesis_invalidated(self, thesis_id: str) -> dict[str, Any]:
        return self.update_position_thesis_profile(thesis_id, {"status": "INVALIDATED"})

    def get_thesis_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": datetime.now().astimezone().isoformat(),
            "total_thesis_profiles": int(summary["total_thesis_profiles"] or 0),
            "active_thesis_profiles": int(summary["active_thesis_profiles"] or 0),
            "draft_thesis_profiles": int(summary["draft_thesis_profiles"] or 0),
            "needs_review": int(summary["needs_review"] or 0),
            "invalidated": int(summary["invalidated"] or 0),
            "paper_ready": int(summary["paper_ready"] or 0),
            "live_ready": int(summary["live_ready"] or 0),
            "avg_completeness_score": float(summary["avg_completeness_score"] or 0),
            "positions_without_thesis": int(summary["positions_without_thesis"] or 0),
            "latest_thesis_profiles": [
                _json_safe(position_thesis_profile_from_row(dict(row)).to_api_dict())
                for row in summary["latest_thesis_profiles"]
            ],
            "missing_required_fields_summary": [_json_safe(dict(row)) for row in summary["missing_required_fields_summary"]],
        }

    def get_positions_without_thesis(self) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            return self._repository.positions_without_thesis_count(conn)

    def check_thesis_required_for_position(self, position_id: str) -> dict[str, Any]:
        thesis = self.get_thesis_by_position(position_id)
        if thesis is None:
            return {
                "position_id": position_id,
                "thesis_required": True,
                "thesis_present": False,
                "paper_ready": False,
                "live_ready": False,
                "status": "MISSING",
                "reason": "No canonical position thesis profile found.",
            }
        validation = calculate_thesis_validation(PositionThesisProfile(**thesis))
        return {
            "position_id": position_id,
            "thesis_required": True,
            "thesis_present": True,
            "thesis_id": thesis["thesis_id"],
            "paper_ready": validation.paper_ready,
            "live_ready": validation.live_ready,
            "status": thesis["status"],
            "reason": "Thesis profile is complete enough for paper." if validation.paper_ready else "Thesis profile is incomplete or needs review.",
            "validation": validation.to_api_dict(),
        }


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "total_thesis_profiles": 0,
        "active_thesis_profiles": 0,
        "draft_thesis_profiles": 0,
        "needs_review": 0,
        "invalidated": 0,
        "paper_ready": 0,
        "live_ready": 0,
        "avg_completeness_score": 0.0,
        "positions_without_thesis": 0,
        "latest_thesis_profiles": [],
        "missing_required_fields_summary": [],
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
