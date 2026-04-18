from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    request_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    request_max_retries: int = Field(default=3, ge=0, le=10)
    gamma_page_limit: int = Field(default=100, ge=1, le=500)
    gamma_max_pages: int = Field(default=25, ge=1, le=500)
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    user_agent: str = "POLYBOT/0.1 (+local-stage1)"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

