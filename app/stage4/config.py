"""
Configuration for the guarded Stage 4 execution foundation.
"""

from __future__ import annotations

from functools import lru_cache

from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Stage4Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    poly_clob_host: str = Field(
        default="https://clob.polymarket.com",
        validation_alias=AliasChoices("POLY_CLOB_HOST"),
    )
    poly_chain_id: int = Field(
        default=137,
        validation_alias=AliasChoices("POLY_CHAIN_ID"),
    )
    poly_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_PRIVATE_KEY"),
    )
    poly_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_API_KEY"),
    )
    poly_api_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_API_SECRET"),
    )
    poly_api_passphrase: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_API_PASSPHRASE"),
    )
    poly_funder: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_FUNDER"),
    )
    poly_signature_type: int = Field(
        default=2,
        validation_alias=AliasChoices("POLY_SIGNATURE_TYPE"),
    )
    live_trading_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LIVE_TRADING_ENABLED"),
    )
    live_max_order_usd: float = Field(
        default=2.0,
        ge=0.01,
        validation_alias=AliasChoices("LIVE_MAX_ORDER_USD"),
    )
    live_market_whitelist: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("LIVE_MARKET_WHITELIST"),
    )
    live_use_adaptive_selector: bool = Field(
        default=True,
        validation_alias=AliasChoices("LIVE_USE_ADAPTIVE_SELECTOR"),
    )
    live_allowed_universe_top_n: int = Field(
        default=20,
        ge=1,
        validation_alias=AliasChoices("LIVE_ALLOWED_UNIVERSE_TOP_N"),
    )
    live_min_total_rank: float = Field(
        default=55.0,
        ge=0.0,
        validation_alias=AliasChoices("LIVE_MIN_TOTAL_RANK"),
    )
    live_min_confidence: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("LIVE_MIN_CONFIDENCE"),
    )
    live_max_open_positions: int = Field(
        default=1,
        ge=0,
        validation_alias=AliasChoices("LIVE_MAX_OPEN_POSITIONS"),
    )
    live_max_same_market_exposure: int = Field(
        default=1,
        ge=0,
        validation_alias=AliasChoices("LIVE_MAX_SAME_MARKET_EXPOSURE"),
    )
    live_cooldown_seconds: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("LIVE_COOLDOWN_SECONDS"),
    )
    live_require_orderbook: bool = Field(
        default=True,
        validation_alias=AliasChoices("LIVE_REQUIRE_ORDERBOOK"),
    )
    live_require_tradable_market: bool = Field(
        default=True,
        validation_alias=AliasChoices("LIVE_REQUIRE_TRADABLE_MARKET"),
    )
    live_optional_whitelist_mode: str = Field(
        default="subset",
        validation_alias=AliasChoices("LIVE_OPTIONAL_WHITELIST_MODE"),
    )
    live_kill_switch: bool = Field(
        default=False,
        validation_alias=AliasChoices("LIVE_KILL_SWITCH"),
    )

    @field_validator("live_market_whitelist", mode="before")
    @classmethod
    def _parse_live_whitelist(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, (int, float)):
            return [str(value).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @field_validator("live_optional_whitelist_mode", mode="before")
    @classmethod
    def _parse_whitelist_mode(cls, value: object) -> str:
        if value is None:
            return "subset"
        normalized = str(value).strip().lower()
        if normalized in {"subset", "disabled"}:
            return normalized
        return "subset"

    @property
    def has_l1_credentials(self) -> bool:
        return bool(self.poly_private_key and self.poly_funder)

    @property
    def has_l2_credentials(self) -> bool:
        return bool(self.poly_api_key and self.poly_api_secret and self.poly_api_passphrase)


@lru_cache(maxsize=1)
def get_stage4_settings() -> Stage4Settings:
    return Stage4Settings()
