from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


LinkabilityStatus = Literal["LINKED", "LINKABLE", "NOT_LINKABLE", "NEEDS_MORE_EVIDENCE", "STALE", "DRY_RUN_ONLY", "ERROR"]
SuggestedLinkAction = Literal[
    "NONE",
    "REVIEW_ONLY",
    "SAFE_TO_LINK_EXISTING_MARKET_ID",
    "BLOCKED_WEAK_EVIDENCE",
    "BLOCKED_DRY_RUN_ONLY",
    "BLOCKED_STALE",
    "BLOCKED_MISSING_MARKET",
    "BLOCKED_MISSING_ENTITY",
    "BLOCKED_MISSING_SOURCE",
    "BLOCKED_NO_MATCHER",
]
AnalysisStatus = Literal["OK", "PARTIAL", "ERROR"]
SuggestionStatus = Literal["REVIEW_ONLY", "SAFE_CANDIDATE", "REJECTED_WEAK_EVIDENCE", "REJECTED_DRY_RUN_ONLY", "REJECTED_STALE", "APPLIED", "ERROR"]


class SignalLinkCoverageAnalysis(BaseModel):
    signal_id: str
    is_linked_to_market: bool = False
    is_linked_to_position: bool = False
    is_unlinked: bool = True
    linkability_status: LinkabilityStatus | str
    primary_unlinked_reason: str
    unlinked_reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    has_market_id: bool = False
    has_entity: bool = False
    has_source: bool = False
    has_rules_context: bool = False
    has_producer: bool = False
    has_matcher_evidence: bool = False
    has_raw_payload_ref: bool = False
    is_dry_run_generated: bool = False
    is_runtime_generated: bool = False
    is_stale: bool = False
    suggested_market_id: str | None = None
    suggested_market_confidence: float | None = Field(default=None, ge=0, le=1)
    suggested_market_reason: str | None = None
    suggested_link_action: SuggestedLinkAction | str
    can_auto_link: bool = False
    can_feed_brain_after_link: bool = False
    can_feed_paper_after_link: bool = False
    analysis_status: AnalysisStatus | str = "OK"
    analyzed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id")
    @classmethod
    def require_signal_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("signal_id is required")
        return normalized

    @field_validator("linkability_status", "primary_unlinked_reason", "suggested_link_action", "analysis_status")
    @classmethod
    def normalize_upper_text(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("link coverage status/reason/action fields are required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["blocked_by"] = data.get("unlinked_reasons", [])
        return data


class SuggestedMarketLink(BaseModel):
    signal_id: str
    suggested_market_id: str
    confidence: float = Field(ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str
    suggestion_status: SuggestionStatus | str
    created_by: str | None = None
    is_applied: bool = False
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("signal_id", "suggested_market_id", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("suggested link signal, market, and reason are required")
        return normalized

    @field_validator("suggestion_status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if not normalized:
            raise ValueError("suggestion_status is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def link_coverage_from_row(row: dict[str, Any]) -> SignalLinkCoverageAnalysis:
    data = dict(row)
    data["unlinked_reasons"] = data.pop("unlinked_reasons_json", []) or []
    data["missing_fields"] = data.pop("missing_fields_json", []) or []
    return SignalLinkCoverageAnalysis(**data)


def suggested_market_link_from_row(row: dict[str, Any]) -> SuggestedMarketLink:
    data = dict(row)
    data["evidence"] = data.pop("evidence_json", {}) or {}
    return SuggestedMarketLink(**data)
