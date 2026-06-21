from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.sql import SQL, Identifier

from app.db.config import get_database_settings


STAGE4_LIVE_ENV_KEYS = (
    "POLY_PRIVATE_KEY",
    "POLY_FUNDER",
    "POLY_API_KEY",
    "POLY_API_SECRET",
    "POLY_API_PASSPHRASE",
    "POLYMARKET_CLOB_API_KEY",
    "POLYMARKET_CLOB_SECRET",
    "POLYMARKET_CLOB_PASSPHRASE",
    "POLYMARKET_CLOB_HOST",
    "POLYMARKET_CHAIN_ID",
    "POLYMARKET_SIGNATURE_TYPE",
    "POLYMARKET_FUNDER_ADDRESS",
    "POLY_CLOB_HOST",
    "POLY_CHAIN_ID",
    "POLY_SIGNATURE_TYPE",
    "LIVE_TRADING_ENABLED",
    "LIVE_KILL_SWITCH",
    "LIVE_MAX_ORDER_USD",
    "LIVE_MAX_DAILY_LOSS",
    "LIVE_MARKET_WHITELIST",
    "LIVE_USE_ADAPTIVE_SELECTOR",
    "LIVE_ALLOWED_UNIVERSE_TOP_N",
    "LIVE_MIN_TOTAL_RANK",
    "LIVE_MIN_CONFIDENCE",
    "LIVE_MAX_CONCURRENT_POSITIONS",
    "LIVE_MAX_OPEN_POSITIONS",
    "LIVE_MAX_SAME_MARKET_EXPOSURE",
    "LIVE_COOLDOWN_SECONDS",
    "LIVE_REQUIRE_ORDERBOOK",
    "LIVE_REQUIRE_TRADABLE_MARKET",
    "LIVE_OPTIONAL_WHITELIST_MODE",
    "MAX_NOTIONAL_PER_ORDER",
    "MAX_CONCURRENT_POSITIONS",
    "MAX_SAME_MARKET_EXPOSURE",
    "MAX_DAILY_LOSS",
    "ALLOW_SCALING",
    "EXECUTION_BACKEND",
    "LIVE_EXECUTION_ENABLED",
)


def _database_url() -> str | None:
    return os.environ.get("POLYBOT_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(autouse=True)
def isolate_stage4_live_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    path = Path(str(request.fspath))
    if not path.name.startswith("test_stage4"):
        yield
        return
    for key in STAGE4_LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    try:
        from app.stage4.config import get_stage4_settings

        get_stage4_settings.cache_clear()
    except Exception:
        pass
    yield
    try:
        from app.stage4.config import get_stage4_settings

        get_stage4_settings.cache_clear()
    except Exception:
        pass


@pytest.fixture
def postgres_test_schema(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    database_url = _database_url()
    if not database_url:
        pytest.skip("POLYBOT_DATABASE_URL is not configured")

    schema_name = f"polybot_test_{uuid4().hex[:12]}"
    with connect(database_url, autocommit=True) as conn:
        conn.execute(SQL("CREATE SCHEMA {}").format(Identifier(schema_name)))

    monkeypatch.setenv("POLYBOT_DATABASE_URL", database_url)
    monkeypatch.setenv("POLYBOT_DATABASE_SCHEMA", schema_name)
    monkeypatch.setenv("PHASE1_PERSISTENCE_ENABLED", "true")
    get_database_settings.cache_clear()

    try:
        yield {"database_url": database_url, "schema": schema_name}
    finally:
        get_database_settings.cache_clear()
        with connect(database_url, autocommit=True) as conn:
            conn.execute(SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(Identifier(schema_name)))
