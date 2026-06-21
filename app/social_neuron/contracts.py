from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.social_neuron.redaction import redact_dict


class SocialSourceType(StrEnum):
    RSS_MIRROR = "RSS_MIRROR"
    PUBLIC_TREND_API = "PUBLIC_TREND_API"
    MANUAL = "MANUAL"
    X_TWITTER = "X_TWITTER"
    REDDIT = "REDDIT"
    TELEGRAM = "TELEGRAM"
    DISCORD = "DISCORD"
    NEWS_SOCIAL_MIRROR = "NEWS_SOCIAL_MIRROR"


class SocialPlatform(StrEnum):
    X_TWITTER = "x_twitter"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    RSS_MIRROR = "rss_mirror"
    MANUAL = "manual"
    PUBLIC_TRENDS = "public_trends"


class SocialDirection(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    BOTH = "BOTH"
    NONE = "NONE"


class SocialSentiment(StrEnum):
    YES = "YES"
    NO = "NO"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class LeadLagStatus(StrEnum):
    SOCIAL_LEADS_PRICE = "SOCIAL_LEADS_PRICE"
    SOCIAL_LAGS_PRICE = "SOCIAL_LAGS_PRICE"
    SIMULTANEOUS = "SIMULTANEOUS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def bounded(value: float | int | None, default: float = 0.0) -> float:
    try:
        number = float(default if value is None else value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def stable_hash(value: Any) -> str:
    payload = json.dumps(redact_dict(value if isinstance(value, dict) else {"value": value}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SocialSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    name: str
    source_type: SocialSourceType
    platform: SocialPlatform
    category: str | None = None
    url: str | None = None
    feed_url: str | None = None
    enabled: bool = True
    reliability_score: float = 0.50
    noise_baseline: float = 0.50
    bot_risk_baseline: float = 0.50
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_id", "name")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("field is required")
        return str(value).strip()

    @field_validator("reliability_score", "noise_baseline", "bot_risk_baseline")
    @classmethod
    def scores(cls, value: float) -> float:
        return bounded(value, 0.5)

    @model_validator(mode="after")
    def redact_metadata(self) -> "SocialSource":
        self.metadata = redact_dict(self.metadata)
        return self


class RawSocialEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_social_event_id: str = Field(default_factory=lambda: f"social_raw_{uuid4().hex}")
    source_id: str
    platform: SocialPlatform = SocialPlatform.MANUAL
    external_id: str | None = None
    url: str | None = None
    author_id: str | None = None
    author_handle: str | None = None
    text: str
    raw_text: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    language: str | None = None
    engagement: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_hash(self) -> "RawSocialEvent":
        if not self.text.strip():
            raise ValueError("text is required")
        self.raw_payload = redact_dict(self.raw_payload)
        if not self.content_hash:
            self.content_hash = stable_hash({"source_id": self.source_id, "text": self.text, "url": self.url})
        return self


class NormalizedSocialEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    social_event_id: str = Field(default_factory=lambda: f"social_evt_{uuid4().hex}")
    raw_social_event_id: str | None = None
    source_id: str
    platform: SocialPlatform = SocialPlatform.MANUAL
    dedup_group_id: str | None = None
    text: str
    normalized_text: str
    author_handle: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    category: str | None = None
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    cashtags: list[str] = Field(default_factory=list)
    language: str | None = None
    engagement_score: float = 0.0
    influence_score: float = 0.0
    spam_score: float = 0.0
    bot_risk: float = 0.0
    novelty_score: float = 0.0
    status: str = "NORMALIZED"

    @field_validator("engagement_score", "influence_score", "spam_score", "bot_risk", "novelty_score")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class SocialMarketLink(BaseModel):
    social_link_id: str = Field(default_factory=lambda: f"social_link_{uuid4().hex}")
    social_event_id: str
    market_id: str
    link_score: float = 0.0
    sentiment_direction: SocialDirection = SocialDirection.UNKNOWN
    confidence: float = 0.0
    link_reason: str | None = None
    matched_entities: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    method: str = "rule_based"

    @field_validator("link_score", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class SocialSentimentScore(BaseModel):
    sentiment_id: str = Field(default_factory=lambda: f"social_sentiment_{uuid4().hex}")
    social_event_id: str
    market_id: str | None = None
    sentiment: SocialSentiment = SocialSentiment.UNKNOWN
    sentiment_score: float = 0.0
    confidence: float = 0.0
    target: str | None = None
    reason: str | None = None

    @field_validator("sentiment_score", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)


class SocialSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: str = "social"
    market_id: str
    hype_pressure: float = 0.0
    sentiment: SocialSentiment = SocialSentiment.UNKNOWN
    mentions_velocity: float = 0.0
    bot_risk: float = 0.0
    confidence: float = 0.0

    @field_validator("hype_pressure", "bot_risk", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)

    @field_validator("mentions_velocity")
    @classmethod
    def velocity_non_negative(cls, value: float) -> float:
        return max(0.0, float(value))


class SocialHypeScore(BaseModel):
    hype_id: str = Field(default_factory=lambda: f"social_hype_{uuid4().hex}")
    market_id: str
    window_seconds: int = 900
    mention_count: int = 0
    unique_author_count: int = 0
    mentions_velocity: float = 0.0
    velocity_zscore: float | None = None
    hype_pressure: float = 0.0
    sentiment: SocialSentiment = SocialSentiment.UNKNOWN
    sentiment_confidence: float = 0.0
    bot_risk: float = 0.0
    spam_ratio: float = 0.0
    narrative_strength: float = 0.0
    confidence: float = 0.0
    signal: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def build_signal(self) -> "SocialHypeScore":
        self.hype_pressure = bounded(self.hype_pressure)
        self.sentiment_confidence = bounded(self.sentiment_confidence)
        self.bot_risk = bounded(self.bot_risk)
        self.spam_ratio = bounded(self.spam_ratio)
        self.narrative_strength = bounded(self.narrative_strength)
        self.confidence = bounded(self.confidence)
        self.mentions_velocity = max(0.0, float(self.mentions_velocity))
        self.signal = SocialSignal(
            market_id=self.market_id,
            hype_pressure=self.hype_pressure,
            sentiment=self.sentiment,
            mentions_velocity=self.mentions_velocity,
            bot_risk=self.bot_risk,
            confidence=self.confidence,
        ).model_dump(mode="json")
        return self


class SocialNoiseScore(BaseModel):
    noise_id: str = Field(default_factory=lambda: f"social_noise_{uuid4().hex}")
    social_event_id: str | None = None
    market_id: str | None = None
    platform: SocialPlatform | None = None
    spam_score: float = 0.0
    bot_risk: float = 0.0
    duplicate_risk: float = 0.0
    coordinated_activity_risk: float = 0.0
    noise_score: float = 0.0
    reason: str | None = None

    @model_validator(mode="after")
    def bound_scores(self) -> "SocialNoiseScore":
        self.spam_score = bounded(self.spam_score)
        self.bot_risk = bounded(self.bot_risk)
        self.duplicate_risk = bounded(self.duplicate_risk)
        self.coordinated_activity_risk = bounded(self.coordinated_activity_risk)
        self.noise_score = bounded(max(self.spam_score, self.bot_risk, self.duplicate_risk, self.coordinated_activity_risk))
        return self


class SocialNarrative(BaseModel):
    narrative_id: str = Field(default_factory=lambda: f"social_narrative_{uuid4().hex}")
    narrative_key: str
    title: str
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    market_ids: list[str] = Field(default_factory=list)
    event_count: int = 0
    narrative_strength: float = 0.0
    confidence: float = 0.0
    status: str = "ACTIVE"

    @field_validator("narrative_strength", "confidence")
    @classmethod
    def bounded_scores(cls, value: float) -> float:
        return bounded(value)
