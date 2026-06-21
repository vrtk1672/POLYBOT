from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYBOT_DATABASE_URL", "DATABASE_URL"),
    )
    database_schema: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POLYBOT_DATABASE_SCHEMA", "DATABASE_SCHEMA"),
    )
    phase1_persistence_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "POLYBOT_PHASE1_PERSISTENCE_ENABLED",
            "PHASE1_PERSISTENCE_ENABLED",
        ),
    )
    phase1_auto_migrate: bool = Field(
        default=False,
        validation_alias=AliasChoices("POLYBOT_PHASE1_AUTO_MIGRATE", "PHASE1_AUTO_MIGRATE"),
    )
    artifacts_root: str = Field(
        default="artifacts/phase1",
        validation_alias=AliasChoices("POLYBOT_ARTIFACTS_ROOT", "ARTIFACTS_ROOT"),
    )

    @property
    def enabled(self) -> bool:
        return self.phase1_persistence_enabled and bool(self.database_url)


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
