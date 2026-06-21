from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.env_runtime import load_env_file_into_process


ENV_FILE_STATUS = load_env_file_into_process()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="POLYBOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "POLYBOT"
    stage_name: str = "Stage 1 - Eyes"
    gamma_api_base_url: str = "https://gamma-api.polymarket.com"
    gamma_events_path: str = "/events"
    refresh_interval_seconds: int = Field(default=60, ge=10, le=3600)
    top_n: int = Field(default=10, ge=1, le=100)
    market_universe_persist_limit: int = Field(default=1000, ge=1, le=10000)
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    request_max_retries: int = Field(default=3, ge=0, le=10)
    gamma_page_limit: int = Field(default=100, ge=1, le=500)
    gamma_max_pages: int = Field(default=25, ge=1, le=500)
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    user_agent: str = "POLYBOT/0.1 (+local-stage1)"
    dashboard_title: str = "POLYBOT Operator Control Room"
    dashboard_refresh_seconds: int = Field(default=30, ge=5, le=3600)
    telegram_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "POLYBOT_TELEGRAM_BOT_TOKEN"),
    )
    telegram_default_chat_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_DEFAULT_CHAT_ID", "POLYBOT_TELEGRAM_DEFAULT_CHAT_ID"),
    )
    telegram_channels: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_CHANNELS", "POLYBOT_TELEGRAM_CHANNELS"),
    )
    telegram_webhook_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_WEBHOOK_SECRET", "POLYBOT_TELEGRAM_WEBHOOK_SECRET"),
    )
    alert_dedupe_window_seconds: int = Field(default=900, ge=0, le=86400)
    runtime_mode: str = Field(default="paper", validation_alias="POLYBOT_RUNTIME_MODE")
    intelligence_refresh_interval_seconds: int = Field(default=900, ge=60, le=86400)
    intelligence_news_enabled: bool = True
    intelligence_news_max_items_per_source: int = Field(default=10, ge=1, le=50)
    intelligence_whale_refresh_interval_seconds: int = Field(default=900, ge=60, le=86400)
    intelligence_ai_enabled: bool = True
    intelligence_ai_max_events: int = Field(default=5, ge=1, le=20)
    intelligence_news_stale_after_seconds: int = Field(default=5400, ge=60, le=172800)
    intelligence_whale_stale_after_seconds: int = Field(default=5400, ge=60, le=172800)
    intelligence_ai_stale_after_seconds: int = Field(default=21600, ge=60, le=604800)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def canonical_runtime_mode(value: str | None) -> str:
    normalized = (value or "paper").strip().lower()
    if normalized in {"listen_only", "scan_only", "off"}:
        return "LISTEN_ONLY"
    if normalized in {"live", "live_caged"}:
        return "LIVE"
    return "PAPER"
