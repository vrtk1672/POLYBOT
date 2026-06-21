from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


BlockerSeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
BlockerCategory = Literal[
    "DATA",
    "SIGNALS",
    "LINKAGE",
    "LINEAGE",
    "PROVENANCE",
    "BRAIN",
    "COORDINATOR",
    "RISK",
    "EXIT",
    "RUNTIME",
    "EXECUTION",
    "DASHBOARD",
]
BlockerOverallStatus = Literal["READY", "BLOCKED", "DEGRADED", "UNKNOWN"]


class MeshBlocker(BaseModel):
    code: str
    active: bool = True
    severity: BlockerSeverity | str
    category: BlockerCategory | str
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    source: str
    recommended_next_step: str
    blocks_paper: bool = True

    @field_validator("code", "severity", "category")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("code, severity, and category are required")
        return normalized

    @field_validator("reason", "source", "recommended_next_step")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("reason, source, and recommended_next_step are required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class MeshBlockerReport(BaseModel):
    mock_data: bool = False
    paper_ready: bool = False
    overall_status: BlockerOverallStatus | str
    blocked_by: list[str] = Field(default_factory=list)
    blockers: list[MeshBlocker] = Field(default_factory=list)
    info: list[MeshBlocker] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    last_updated: datetime
    analysis_status: str = "OK"

    @field_validator("overall_status", "analysis_status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("status is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
