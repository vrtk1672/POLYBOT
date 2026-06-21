from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.advisory_resolution import AdvisoryResolutionService
from app.services.alerts import AlertEventService
from app.services.command_intent_staging import CommandIntentStagingService
from app.services.exit_advisory import ExitAdvisoryService
from app.services.operator_control import OperatorControlService
from app.services.ranking_policy import RankingPolicyService
from app.services.telegram_bot import TelegramCommandService
from test_phase3e_cognition_summary import _seed_market_snapshots
from test_phase7b_ranking_policy import _insert_ranking_candidate
from test_phase8b_exit_advisory import (
    _seed_invalidation_policy_record,
    _seed_live_order,
    _seed_live_position,
    _seed_paper_order,
    _seed_paper_position,
    _seed_shadow_order,
    _seed_shadow_position,
)


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def _seed_phase9_operator_context(market_id: str) -> None:
    _seed_market_snapshots()
    ranking_run_id, _ = _insert_ranking_candidate(
        market_id=market_id,
        total_rank_score=81.0,
        rank_position=1,
        rank_tier_class="TOP",
    )
    ranking_policy = RankingPolicyService().apply_policy_to_ranking_run(ranking_run_id)
    assert ranking_policy is not None
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=market_id)
    _seed_live_order(market_id=market_id, status="LIVE")
    _seed_paper_position(market_id=market_id)
    _seed_paper_order(market_id=market_id, status="OPEN")
    _seed_shadow_position(market_id=market_id)
    _seed_shadow_order(market_id=market_id, status="WOULD_SUBMIT")

    advisory = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase9_test")
    assert advisory is not None
    resolution = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase9_test")
    assert resolution is not None
    intents = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase9_test")
    assert intents is not None


def test_phase9_migrations_create_dashboard_and_telegram_tables(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    table_names = {row["table_name"] for row in tables}
    assert {"operator_control_actions", "alert_events"} <= table_names


def test_dashboard_endpoints_return_coherent_data(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"phase9-dashboard-{uuid4().hex[:8]}"
    _seed_phase9_operator_context(market_id)
    AlertEventService().emit_alert(
        event_class="INVALIDATION_WARNING",
        severity_class="WARNING",
        title="Invalidation warning",
        body_text="Critical invalidation policy record was persisted.",
        dedupe_key=f"phase9-warning-{market_id}",
        source_ref=market_id,
    )
    OperatorControlService().request_placeholder_action(
        action_class="PAUSE",
        requested_via="API",
        requested_by="phase9-test",
        command_text="/pause",
    )

    with _build_test_client() as client:
        html = client.get("/dashboard")
        overview = client.get("/dashboard/api/overview?limit=4")
        kpi_quality = client.get("/dashboard/api/kpi-quality?recent_cycles=4&top_reasons_limit=3")
        ranking = client.get("/dashboard/api/ranking?limit=4")
        positions = client.get("/dashboard/api/positions-orders?limit=4")
        invalidation = client.get("/dashboard/api/invalidation?limit=4")
        audit = client.get("/dashboard/api/audit?limit=4")
        alerts = client.get("/dashboard/api/alerts?limit=4")

    assert html.status_code == 200
    assert "POLYBOT Operator Control Room" in html.text
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["system_health"]["db_connected"] is True
    assert overview_payload["system_health"]["execution_mode"] in {"PAPER", "LIVE", "LISTEN_ONLY"}
    assert "env_runtime" in overview_payload["system_health"]
    assert "live_cage" in overview_payload["system_health"]
    assert "paper_safe_policy" in overview_payload["system_health"]
    assert "paper_capital" in overview_payload["system_health"]
    assert "paper_capital_policy" in overview_payload["system_health"]
    assert "live_capital_source" in overview_payload["system_health"]
    assert "intelligence_runtime" in overview_payload["system_health"]
    assert overview_payload["system_health"]["paper_capital"]["source_mode"] == "paper"
    assert "kpi_quality" in overview_payload
    assert overview_payload["positions_orders"]["pnl"]["live"]["unrealized"] == 0.0
    assert kpi_quality.status_code == 200
    kpi_payload = kpi_quality.json()
    assert "kpis" in kpi_payload
    assert "quality" in kpi_payload
    assert "shadow_activity" in kpi_payload["kpis"]
    assert "shadow_status_distribution" in kpi_payload["quality"]
    assert ranking.json()["selected_candidate_count"] >= 0
    assert len(positions.json()["live_positions"]) == 1
    invalidation_payload = invalidation.json()
    assert len(invalidation_payload["invalidation_policy_records"]) == 1
    assert len(invalidation_payload["exit_advisory_records"]) >= 1
    assert len(invalidation_payload["advisory_resolution_records"]) == 1
    assert len(invalidation_payload["command_intent_records"]) >= 1
    assert len(audit.json()["operator_control_actions"]) == 1
    assert "live_order_status_history" in audit.json()
    assert "live_position_events" in audit.json()
    assert "shadow_order_events" in audit.json()
    assert len(alerts.json()["items"]) == 1


def test_dashboard_handles_missing_or_empty_upstream_data_honestly(postgres_test_schema) -> None:
    run_migrations()
    with _build_test_client() as client:
        overview = client.get("/dashboard/api/overview")
        intelligence = client.get("/dashboard/api/intelligence")

    assert overview.status_code == 200
    payload = overview.json()
    assert payload["system_health"]["warnings"]
    assert payload["kpi_quality"]["window"]["recent_cycle_count"] == 0
    assert payload["ranking"]["top_ranked"] == []
    assert payload["positions_orders"]["live_positions"] == []
    assert payload["invalidation_exit"]["command_intent_records"] == []
    assert intelligence.status_code == 200
    intelligence_payload = intelligence.json()
    assert intelligence_payload["whales"] == []
    assert intelligence_payload["news"] == []
    assert intelligence_payload["cognition"] == []
    assert "news_state" in intelligence_payload
    assert "whale_state" in intelligence_payload
    assert "ai_state" in intelligence_payload
    assert intelligence_payload["news_state"]["freshness_status"] == "ABSENT"
    assert intelligence_payload["whale_state"]["freshness_status"] == "ABSENT"
    assert intelligence_payload["ai_state"]["freshness_status"] == "ABSENT"
    assert "env_runtime" in payload["system_health"]


def test_telegram_command_handlers_return_coherent_responses(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"phase9-telegram-{uuid4().hex[:8]}"
    _seed_phase9_operator_context(market_id)

    service = TelegramCommandService()
    status = service.handle_command("/status", requested_by="tester")
    top = service.handle_command("/top", requested_by="tester")
    positions = service.handle_command("/positions", requested_by="tester")
    orders = service.handle_command("/orders", requested_by="tester")
    pnl = service.handle_command("/pnl", requested_by="tester")
    whales = service.handle_command("/whales", requested_by="tester")
    news = service.handle_command("/news", requested_by="tester")

    assert status.supported is True
    assert "Pending eligible intents" in status.response_text
    assert top.supported is True
    assert "Top ranked opportunities" in top.response_text
    assert positions.supported is True
    assert "Open positions" in positions.response_text
    assert orders.supported is True
    assert "Orders" in orders.response_text
    assert pnl.supported is True
    assert "PnL snapshot" in pnl.response_text
    assert whales.supported is True
    assert whales.response_text == "No persisted whale intelligence is available yet."
    assert news.supported is True
    assert news.response_text == "No persisted external news is available yet."


def test_alert_generation_behaves_correctly_for_supported_events(postgres_test_schema) -> None:
    run_migrations()
    service = AlertEventService()
    first = service.emit_alert(
        event_class="FEED_FAILURE",
        severity_class="CRITICAL",
        title="Feed failure",
        body_text="External feed failed health checks.",
        dedupe_key="phase9-feed-failure",
        source_ref="feed-a",
    )
    second = service.emit_alert(
        event_class="FEED_FAILURE",
        severity_class="CRITICAL",
        title="Feed failure",
        body_text="External feed failed health checks.",
        dedupe_key="phase9-feed-failure",
        source_ref="feed-a",
    )

    assert first.emitted is True
    assert first.delivery_status_class == "PENDING"
    assert second.emitted is False
    assert second.delivery_status_class == "SKIPPED"

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT delivery_status_class FROM alert_events ORDER BY created_at ASC, id ASC"
        ).fetchall()
    assert [row["delivery_status_class"] for row in rows] == ["PENDING", "SKIPPED"]


@pytest.mark.parametrize(
    ("command", "expected_status", "expected_text"),
    [
        ("/pause", "PLACEHOLDER", "recorded for audit only"),
        ("/resume", "RELEASED_GUARD", "cleared the live cage kill override"),
        ("/kill", "ACTIVE_GUARD", "Future live submissions will be blocked immediately"),
    ],
)
def test_safe_control_commands_are_audited_and_constrained(
    postgres_test_schema,
    command: str,
    expected_status: str,
    expected_text: str,
) -> None:
    run_migrations()
    with _build_test_client() as client:
        response = client.post(
            "/telegram/command",
            json={"command": command, "requested_by": "telegram-phase9"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is True
    assert payload["control_action_id"] is not None
    assert expected_text in payload["response_text"]

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            """
            SELECT action_class, requested_via, status_class, reason_text
            FROM operator_control_actions
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    assert row["action_class"] == command.replace("/", "").upper()
    assert row["requested_via"] == "TELEGRAM"
    assert row["status_class"] == expected_status


def test_unsupported_commands_respond_honestly(postgres_test_schema) -> None:
    run_migrations()
    response = TelegramCommandService().handle_command("/unsupported", requested_by="tester")
    assert response.supported is False
    assert response.response_text == "Command not supported yet by the current Telegram foundation."


def test_no_direct_execution_mutation_occurs(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"phase9-safe-{uuid4().hex[:8]}"
    _seed_phase9_operator_context(market_id)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_positions": conn.execute("SELECT COUNT(*) AS count FROM shadow_positions").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
        }

    with _build_test_client() as client:
        assert client.get("/dashboard/api/overview").status_code == 200
        assert client.post("/telegram/command", json={"command": "/pause", "requested_by": "phase9-safe"}).status_code == 200

    with factory.connect() as conn:
        after = {
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_positions": conn.execute("SELECT COUNT(*) AS count FROM shadow_positions").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
        }

    assert before == after
