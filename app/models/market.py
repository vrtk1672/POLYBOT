from datetime import datetime

from pydantic import BaseModel, Field


class NormalizedMarket(BaseModel):
    market_id: str
    event_id: str
    event_title: str
    question: str
    slug: str | None = None
    end_time: datetime | None = None
    yes_price: float | None = Field(default=None, ge=0.0, le=1.0)
    no_price: float | None = Field(default=None, ge=0.0, le=1.0)
    last_trade_price: float | None = Field(default=None, ge=0.0, le=1.0)
    best_bid: float | None = Field(default=None, ge=0.0, le=1.0)
    best_ask: float | None = Field(default=None, ge=0.0, le=1.0)
    spread: float | None = Field(default=None, ge=0.0)
    liquidity: float | None = Field(default=None, ge=0.0)
    volume: float | None = Field(default=None, ge=0.0)
    volume_24h: float | None = Field(default=None, ge=0.0)
    open_interest: float | None = Field(default=None, ge=0.0)
    comment_count: int | None = Field(default=None, ge=0)
    competitive: float | None = Field(default=None, ge=0.0)
    accepting_orders: bool = False
    updated_at: datetime | None = None
    raw_market: dict = Field(default_factory=dict)

