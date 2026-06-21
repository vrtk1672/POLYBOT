from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.services.position_thesis import PositionThesisService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM position_thesis_validation_events")
        conn.execute("DELETE FROM position_thesis_profiles")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM entity_market_links")
        conn.execute("DELETE FROM event_entities")


def _valid_payload(**overrides) -> dict[str, object]:
    data: dict[str, object] = {
        "position_id": f"position-{uuid4().hex}",
        "market_id": "market-thesis-repo",
        "side": "YES",
        "entry_thesis": "Position exists because the market may reprice after verified information.",
        "profit_drivers": ["verified resolution path"],
        "invalidation_drivers": ["resolution wording becomes ambiguous"],
        "watch_entities": ["resolution source"],
        "danger_signals": ["rules_degraded"],
        "take_profit_rules": ["review profit if edge closes"],
        "partial_exit_rules": ["review partial de-risk if confidence drops"],
        "emergency_exit_rules": ["review emergency exit if source is invalidated"],
        "status": "ACTIVE",
        "reviewed_by": "operator",
        "reviewed_at": datetime.now(UTC),
        "created_by": "test",
        "metadata": {"phase": "3B"},
    }
    data.update(overrides)
    return data


def test_repository_creates_and_reads_thesis_profile(postgres_test_schema) -> None:
    _clear()
    service = PositionThesisService()
    profile = service.create_position_thesis_profile(_valid_payload(position_id="position-read"))

    by_id = service.get_thesis_by_id(profile["thesis_id"])
    by_position = service.get_thesis_by_position("position-read")

    assert by_id is not None
    assert by_position is not None
    assert by_id["paper_ready"] is True
    assert by_id["live_ready"] is True
    assert by_position["thesis_id"] == profile["thesis_id"]


def test_repository_updates_and_validates_profile(postgres_test_schema) -> None:
    _clear()
    service = PositionThesisService()
    profile = service.create_position_thesis_profile(_valid_payload(position_id="position-update"))
    updated = service.update_position_thesis_profile(
        profile["thesis_id"],
        {"status": "ACTIVE", "invalidation_drivers": []},
    )
    validation = service.validate_thesis_profile(profile["thesis_id"])

    assert updated["paper_ready"] is False
    assert validation["paper_ready"] is False
    assert "invalidation_drivers" in validation["missing_fields"]


def test_mark_needs_review_and_invalidated(postgres_test_schema) -> None:
    _clear()
    service = PositionThesisService()
    profile = service.create_position_thesis_profile(_valid_payload(position_id="position-status"))

    needs_review = service.mark_thesis_needs_review(profile["thesis_id"])
    invalidated = service.mark_thesis_invalidated(profile["thesis_id"])

    assert needs_review["status"] == "NEEDS_REVIEW"
    assert needs_review["paper_ready"] is False
    assert invalidated["status"] == "INVALIDATED"
    assert invalidated["live_ready"] is False


def test_thesis_summary_and_required_helper(postgres_test_schema) -> None:
    _clear()
    service = PositionThesisService()
    profile = service.create_position_thesis_profile(_valid_payload(position_id="position-summary"))

    summary = service.get_thesis_summary()
    check = service.check_thesis_required_for_position("position-summary")
    missing = service.check_thesis_required_for_position("position-missing")

    assert summary["mock_data"] is False
    assert summary["total_thesis_profiles"] == 1
    assert summary["paper_ready"] == 1
    assert check["thesis_present"] is True
    assert check["thesis_id"] == profile["thesis_id"]
    assert missing["thesis_present"] is False
    assert missing["status"] == "MISSING"


def test_thesis_store_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    PositionThesisService().create_position_thesis_profile(_valid_payload(position_id="position-safe"))

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
