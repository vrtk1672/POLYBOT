"""
Configuration for the guarded Stage 4 execution foundation.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Mapping

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.env_runtime import load_env_file_into_process


class Stage4Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    poly_clob_host: str = Field(
        default="https://clob.polymarket.com",
        validation_alias=AliasChoices("POLYMARKET_CLOB_HOST", "POLY_CLOB_HOST"),
    )
    poly_chain_id: int = Field(
        default=137,
        validation_alias=AliasChoices("POLYMARKET_CHAIN_ID", "POLY_CHAIN_ID"),
    )
    poly_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLY_PRIVATE_KEY"),
        repr=False,
    )
    poly_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYMARKET_CLOB_API_KEY", "POLY_API_KEY"),
        repr=False,
    )
    poly_api_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYMARKET_CLOB_SECRET", "POLY_API_SECRET"),
        repr=False,
    )
    poly_api_passphrase: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYMARKET_CLOB_PASSPHRASE", "POLY_API_PASSPHRASE"),
        repr=False,
    )
    poly_funder: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYMARKET_FUNDER_ADDRESS", "POLY_FUNDER"),
    )
    poly_signature_type: int = Field(
        default=2,
        validation_alias=AliasChoices("POLYMARKET_SIGNATURE_TYPE", "POLY_SIGNATURE_TYPE"),
    )
    live_trading_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LIVE_TRADING_ENABLED"),
    )
    live_max_order_usd: float = Field(
        default=2.0,
        ge=0.01,
        validation_alias=AliasChoices("MAX_NOTIONAL_PER_ORDER", "LIVE_MAX_ORDER_USD"),
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
        validation_alias=AliasChoices("MAX_CONCURRENT_POSITIONS", "LIVE_MAX_CONCURRENT_POSITIONS", "LIVE_MAX_OPEN_POSITIONS"),
    )
    paper_safe_max_open_positions: int = Field(
        default=3,
        ge=1,
        validation_alias=AliasChoices("PAPER_SAFE_MAX_CONCURRENT_POSITIONS", "PAPER_MAX_CONCURRENT_POSITIONS"),
    )
    paper_starting_capital_usd: float = Field(
        default=100.0,
        ge=1.0,
        validation_alias=AliasChoices("PAPER_STARTING_CAPITAL_USD"),
    )
    paper_min_cash_reserve_pct: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("PAPER_MIN_CASH_RESERVE_PCT"),
    )
    paper_max_alloc_per_trade_pct: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
        validation_alias=AliasChoices("PAPER_MAX_ALLOC_PER_TRADE_PCT"),
    )
    paper_max_total_deployment_pct: float = Field(
        default=0.75,
        ge=0.01,
        le=1.0,
        validation_alias=AliasChoices("PAPER_MAX_TOTAL_DEPLOYMENT_PCT"),
    )
    live_max_same_market_exposure: int = Field(
        default=1,
        ge=0,
        validation_alias=AliasChoices("MAX_SAME_MARKET_EXPOSURE", "LIVE_MAX_SAME_MARKET_EXPOSURE"),
    )
    live_max_daily_loss_usd: float = Field(
        default=2.0,
        ge=0.0,
        validation_alias=AliasChoices("MAX_DAILY_LOSS", "LIVE_MAX_DAILY_LOSS"),
    )
    live_allow_scaling: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_SCALING", "LIVE_ALLOW_SCALING"),
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
        default=True,
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
    return load_stage4_settings()


def load_stage4_settings() -> Stage4Settings:
    return Stage4Settings()


def load_stage4_settings_from_env(env: Mapping[str, str] | None = None) -> Stage4Settings:
    if env is None:
        return Stage4Settings(_env_file=None)
    return Stage4Settings(_env_file=None, **dict(env))


def load_stage4_settings_from_runtime_env(env_path: str | Path | None = None) -> Stage4Settings:
    load_env_file_into_process(env_path)
    get_stage4_settings.cache_clear()
    return Stage4Settings(_env_file=None, **dict(os.environ))
