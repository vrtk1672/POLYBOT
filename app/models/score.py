from datetime import datetime

from pydantic import BaseModel, Field

from app.models.market import NormalizedMarket


class ScoreBreakdown(BaseModel):
    price_attractiveness: float = Field(ge=0.0, le=35.0)
    time_to_close: float = Field(ge=0.0, le=25.0)
    liquidity_volume: float = Field(ge=0.0, le=20.0)
    market_activity: float = Field(ge=0.0, le=20.0)


class ScoredMarket(BaseModel):
    market: NormalizedMarket
    score: float = Field(ge=0.0, le=100.0)
    breakdown: ScoreBreakdown
    reason: str
    computed_at: datetime

