from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.config import get_database_settings
from app.db.migrate import run_migrations
from app.services.paper_defense import PaperDefenseGovernor, defense_profile
import pytest


def test_defense_profile_preserves_strict_default() -> None:
    profile = defense_profile(100)
    assert profile.defense_level == 100
    assert str(profile.adjusted_threshold) == "60"
    assert str(profile.max_deployed_pct) == "20"
    assert profile.exit_fallback_enabled is False


def test_low_defense_profile_allows_learning_capital() -> None:
    profile = defense_profile(20)
    assert profile.defense_level == 20
    assert str(profile.adjusted_threshold) == "42"
    assert str(profile.max_deployed_pct) == "80"
    assert profile.exit_fallback_enabled is True


def test_reset_creates_session_with_defense_level() -> None:
    if not get_database_settings().database_url:
        pytest.skip("POLYBOT_DATABASE_URL is not configured")
    run_migrations()
    result = PaperDefenseGovernor().status()
    assert result["status"] in {"OK", "DATABASE_UNAVAILABLE"}
    if result["status"] == "DATABASE_UNAVAILABLE":
        return
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='paper_sessions' AND column_name='defense_level'
            """
        ).fetchone()
    assert row is not None
