from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


ThesisStatus = Literal["DRAFT", "ACTIVE", "NEEDS_REVIEW", "INVALIDATED", "EXPIRED", "ARCHIVED"]
ThesisSide = Literal["YES", "NO", "UNKNOWN"]

ALLOWED_THESIS_STATUSES = {"DRAFT", "ACTIVE", "NEEDS_REVIEW", "INVALIDATED", "EXPIRED", "ARCHIVED"}
ALLOWED_THESIS_SIDES = {"YES", "NO", "UNKNOWN"}
EXECUTABLE_THESIS_TERMS = {
    "BUY",
    "SELL",
    "PLACE_ORDER",
    "CANCEL_ORDER",
    "EXECUTE",
    "LIVE_APPROVED",
    "ENTER_TRADE",
    "EXIT_TRADE",
    "OPEN_POSITION",
    "CLOSE_POSITION",
    "ORDER_CREATION",
}

PAPER_REQUIRED_FIELDS = [
    "position_id",
    "market_id",
    "entry_thesis",
    "profit_drivers",
    "invalidation_drivers",
    "danger_signals",
    "profit_or_partial_exit_rule",
    "emergency_exit_rules",
]

LIVE_REQUIRED_FIELDS = [
    "side_yes_or_no",
    "watch_entities",
    "take_profit_rules",
    "partial_exit_rules",
    "emergency_exit_rules",
    "reviewed_by",
    "reviewed_at",
]


class ThesisValidationResult(BaseModel):
    validation_status: str
    completeness_score: float = Field(ge=0, le=1)
    paper_ready: bool
    live_ready: bool
    missing_fields: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PositionThesisProfile(BaseModel):
    thesis_id: str = Field(default_factory=lambda: f"thesis_{uuid4().hex}")
    position_id: str
    market_id: str
    side: ThesisSide | str | None = "UNKNOWN"
    entry_thesis: str
    profit_drivers: list[str] = Field(default_factory=list)
    invalidation_drivers: list[str] = Field(default_factory=list)
    watch_entities: list[str] = Field(default_factory=list)
    danger_signals: list[str] = Field(default_factory=list)
    take_profit_rules: list[str] = Field(default_factory=list)
    partial_exit_rules: list[str] = Field(default_factory=list)
    emergency_exit_rules: list[str] = Field(default_factory=list)
    status: ThesisStatus | str = "DRAFT"
    completeness_score: float | None = Field(default=None, ge=0, le=1)
    paper_ready: bool = False
    live_ready: bool = False
    coordinator_decision_id: str | None = None
    brain_output_id: str | None = None
    source_signal_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    thesis_version: int = Field(default=1, ge=1)
    created_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("position_id", "market_id", "entry_thesis", "thesis_id")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("thesis_id, position_id, market_id, and entry_thesis are required")
        return normalized

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in ALLOWED_THESIS_STATUSES:
            raise ValueError(f"status must be one of {sorted(ALLOWED_THESIS_STATUSES)}")
        return normalized

    @field_validator("side")
    @classmethod
    def normalize_side(cls, value: str | None) -> str:
        normalized = (value or "UNKNOWN").strip().upper()
        if normalized not in ALLOWED_THESIS_SIDES:
            raise ValueError(f"side must be one of {sorted(ALLOWED_THESIS_SIDES)}")
        return normalized

    @field_validator(
        "profit_drivers",
        "invalidation_drivers",
        "watch_entities",
        "danger_signals",
        "take_profit_rules",
        "partial_exit_rules",
        "emergency_exit_rules",
        "source_signal_ids",
        "risk_flags",
    )
    @classmethod
    def normalize_string_list(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in (value or []) if str(item).strip()]

    @model_validator(mode="after")
    def validate_non_executing_contract(self) -> "PositionThesisProfile":
        executable_hits = _find_executable_terms(
            {
                "entry_thesis": self.entry_thesis,
                "profit_drivers": self.profit_drivers,
                "invalidation_drivers": self.invalidation_drivers,
                "watch_entities": self.watch_entities,
                "danger_signals": self.danger_signals,
                "take_profit_rules": self.take_profit_rules,
                "partial_exit_rules": self.partial_exit_rules,
                "emergency_exit_rules": self.emergency_exit_rules,
                "metadata": self.metadata,
            }
        )
        if executable_hits:
            raise ValueError(f"thesis profile must not contain executable order language: {sorted(executable_hits)}")
        if self.live_ready and not self.paper_ready:
            raise ValueError("live_ready requires paper_ready")
        return self

    def with_validation(self) -> "PositionThesisProfile":
        validation = calculate_thesis_validation(self)
        data = self.model_dump()
        data["completeness_score"] = validation.completeness_score
        data["paper_ready"] = validation.paper_ready
        data["live_ready"] = validation.live_ready
        return PositionThesisProfile(**data)

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def calculate_thesis_validation(profile: PositionThesisProfile) -> ThesisValidationResult:
    missing: list[str] = []
    errors: list[str] = []

    paper_checks = {
        "position_id": bool(profile.position_id),
        "market_id": bool(profile.market_id),
        "entry_thesis": bool(profile.entry_thesis.strip()),
        "profit_drivers": bool(profile.profit_drivers),
        "invalidation_drivers": bool(profile.invalidation_drivers),
        "danger_signals": bool(profile.danger_signals),
        "profit_or_partial_exit_rule": bool(profile.take_profit_rules or profile.partial_exit_rules),
        "emergency_exit_rules": bool(profile.emergency_exit_rules),
    }
    live_checks = {
        "side_yes_or_no": profile.side in {"YES", "NO"},
        "watch_entities": bool(profile.watch_entities),
        "take_profit_rules": bool(profile.take_profit_rules),
        "partial_exit_rules": bool(profile.partial_exit_rules),
        "emergency_exit_rules": bool(profile.emergency_exit_rules),
        "reviewed_by": bool((profile.reviewed_by or "").strip()),
        "reviewed_at": profile.reviewed_at is not None,
    }

    missing.extend(key for key, ok in paper_checks.items() if not ok)
    live_missing = [key for key, ok in live_checks.items() if not ok]

    score_checks = {
        "position_id": paper_checks["position_id"],
        "market_id": paper_checks["market_id"],
        "side_yes_or_no": live_checks["side_yes_or_no"],
        "entry_thesis": paper_checks["entry_thesis"],
        "profit_drivers": paper_checks["profit_drivers"],
        "invalidation_drivers": paper_checks["invalidation_drivers"],
        "watch_entities": live_checks["watch_entities"],
        "danger_signals": paper_checks["danger_signals"],
        "take_profit_rules": live_checks["take_profit_rules"],
        "partial_exit_rules": live_checks["partial_exit_rules"],
        "emergency_exit_rules": live_checks["emergency_exit_rules"],
        "reviewed": live_checks["reviewed_by"] and live_checks["reviewed_at"],
    }
    completeness_score = round(sum(1 for ok in score_checks.values() if ok) / len(score_checks), 6)

    inactive_status = profile.status in {"DRAFT", "NEEDS_REVIEW", "INVALIDATED", "EXPIRED", "ARCHIVED"}
    if inactive_status:
        errors.append(f"status_{profile.status.lower()}_is_not_ready")

    executable_hits = _find_executable_terms(
        {
            "entry_thesis": profile.entry_thesis,
            "profit_drivers": profile.profit_drivers,
            "invalidation_drivers": profile.invalidation_drivers,
            "watch_entities": profile.watch_entities,
            "danger_signals": profile.danger_signals,
            "take_profit_rules": profile.take_profit_rules,
            "partial_exit_rules": profile.partial_exit_rules,
            "emergency_exit_rules": profile.emergency_exit_rules,
            "metadata": profile.metadata,
        }
    )
    if executable_hits:
        errors.append("executable_rule_language_present")

    paper_ready = profile.status == "ACTIVE" and not errors and all(paper_checks.values())
    live_ready = (
        paper_ready
        and all(live_checks.values())
        and completeness_score >= 0.85
    )
    if not live_ready:
        missing.extend(field for field in live_missing if field not in missing)
    validation_status = "READY" if live_ready else "PAPER_READY" if paper_ready else "INCOMPLETE"
    if errors:
        validation_status = "ERROR"

    return ThesisValidationResult(
        validation_status=validation_status,
        completeness_score=completeness_score,
        paper_ready=paper_ready,
        live_ready=live_ready,
        missing_fields=missing,
        validation_errors=errors,
    )


def position_thesis_profile_from_row(row: dict[str, Any]) -> PositionThesisProfile:
    data = dict(row)
    data["profit_drivers"] = data.pop("profit_drivers_json", []) or []
    data["invalidation_drivers"] = data.pop("invalidation_drivers_json", []) or []
    data["watch_entities"] = data.pop("watch_entities_json", []) or []
    data["danger_signals"] = data.pop("danger_signals_json", []) or []
    data["take_profit_rules"] = data.pop("take_profit_rules_json", []) or []
    data["partial_exit_rules"] = data.pop("partial_exit_rules_json", []) or []
    data["emergency_exit_rules"] = data.pop("emergency_exit_rules_json", []) or []
    data["source_signal_ids"] = data.pop("source_signal_ids_json", []) or []
    data["risk_flags"] = data.pop("risk_flags_json", []) or []
    data["metadata"] = data.pop("metadata_json", {}) or {}
    return PositionThesisProfile(**data)


def _find_executable_terms(value: Any) -> set[str]:
    hits: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            hits.update(_find_executable_terms(item))
    elif isinstance(value, list):
        for item in value:
            hits.update(_find_executable_terms(item))
    elif isinstance(value, str):
        tokens = set(re.findall(r"[A-Z_]+", value.upper()))
        hits.update(tokens & EXECUTABLE_THESIS_TERMS)
    return hits
