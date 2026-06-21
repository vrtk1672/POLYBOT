from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.news_neuron.redaction import redact_dict


class NewsDirection(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    BOTH = "BOTH"
    NONE = "NONE"


class NewsSourceType(StrEnum):
    RSS = "RSS"
    API = "API"
    WEB = "WEB"
    MANUAL = "MANUAL"
    POLYMARKET = "POLYMARKET"
    COURT = "COURT"
    WEATHER = "WEATHER"
    SPORTS = "SPORTS"
    CRYPTO = "CRYPTO"
    MACRO = "MACRO"
    SECURITY = "SECURITY"
    GEO_POLITICS = "GEO_POLITICS"


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def stable_hash(value: Any) -> str:
    payload = json.dumps(redact_dict(value if isinstance(value, dict) else {"value": value}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class NewsSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    name: str
    source_type: NewsSourceType
    category: str | None = None
    url: str | None = None
    feed_url: str | None = None
    enabled: bool = True
    reliability_score: float = 0.50
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "name")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("field is required")
        return str(value).strip()

    @field_validator("reliability_score")
    @classmethod
    def score(cls, value: float) -> float:
        return bounded(value, 0.5)


class RawNewsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_event_id: str = Field(default_factory=lambda: f"news_raw_{uuid4().hex}")
    source_id: str
    external_id: str | None = None
    url: str | None = None
    title: str
    summary: str | None = None
    body_text: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    language: str | None = None
    content_hash: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_hash(self) -> "RawNewsEvent":
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.content_hash:
            self.content_hash = stable_hash({"title": self.title, "summary": self.summary, "url": self.url})
        self.raw_payload = redact_dict(self.raw_payload)
        return self


class NormalizedNewsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    news_event_id: str = Field(default_factory=lambda: f"news_evt_{uuid4().hex}")
    raw_event_id: str | None = None
    source_id: str
    dedup_group_id: str | None = None
    title: str
    normalized_title: str
    summary: str | None = None
    normalized_text: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    event_time: datetime | None = None
    category: str | None = None
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    language: str | None = None
    importance_score: float = 0.0
    urgency_score: float = 0.0
    novelty_score: float = 0.0
    source_reliability: float = 0.50
    status: str = "NORMALIZED"

    @field_validator("importance_score", "urgency_score", "novelty_score", "source_reliability")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class DedupGroup(BaseModel):
    dedup_group_id: str = Field(default_factory=lambda: f"news_dedup_{uuid4().hex}")
    canonical_news_event_id: str | None = None
    group_hash: str
    topic_signature: str | None = None
    event_count: int = 0
    sources: list[str] = Field(default_factory=list)


class NewsMarketLink(BaseModel):
    link_id: str = Field(default_factory=lambda: f"news_link_{uuid4().hex}")
    news_event_id: str
    market_id: str
    link_score: float = 0.0
    direction: NewsDirection = NewsDirection.UNKNOWN
    confidence: float = 0.0
    link_reason: str | None = None
    matched_entities: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    method: str = "rule_based"

    @field_validator("link_score", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class NewsSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: str = "news"
    market_id: str
    direction: NewsDirection = NewsDirection.UNKNOWN
    strength: float = 0.0
    confidence: float = 0.0
    urgency: float = 0.0
    already_priced_in: float = 0.0
    ttl_seconds: int = 0
    source_reliability: float = 0.5
    reason: str = ""

    @field_validator("strength", "confidence", "urgency", "already_priced_in", "source_reliability")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)

    @field_validator("ttl_seconds")
    @classmethod
    def ttl_non_negative(cls, value: int) -> int:
        return max(0, int(value))


class NewsImpactScore(BaseModel):
    impact_id: str = Field(default_factory=lambda: f"news_impact_{uuid4().hex}")
    news_event_id: str
    market_id: str
    direction: NewsDirection = NewsDirection.UNKNOWN
    strength: float = 0.0
    confidence: float = 0.0
    urgency: float = 0.0
    already_priced_in: float = 0.0
    ttl_seconds: int = 0
    source_reliability: float = 0.50
    reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    signal: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def build_signal(self) -> "NewsImpactScore":
        self.strength = bounded(self.strength)
        self.confidence = bounded(self.confidence)
        self.urgency = bounded(self.urgency)
        self.already_priced_in = bounded(self.already_priced_in)
        self.source_reliability = bounded(self.source_reliability, 0.5)
        self.ttl_seconds = max(0, int(self.ttl_seconds))
        self.signal = NewsSignal(
            market_id=self.market_id,
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            urgency=self.urgency,
            already_priced_in=self.already_priced_in,
            ttl_seconds=self.ttl_seconds,
            source_reliability=self.source_reliability,
            reason=self.reason or "news impact scored",
        ).model_dump(mode="json")
        return self
