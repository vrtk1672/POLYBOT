from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.health_truth import HealthTruthService, _stale_services
from app.runtime.state_governor import StateGovernor


def test_healthy_required_service_is_not_stale() -> None:
    rows = [
        {
            "service_name": "fastapi",
            "status": "RUNNING",
            "last_heartbeat_at": datetime.now(UTC),
        }
    ]

    assert _stale_services(rows) == []


def test_genuinely_stale_required_service_is_stale() -> None:
    rows = [
        {
            "service_name": "worker_runtime",
            "status": "RUNNING",
            "last_heartbeat_at": datetime.now(UTC) - timedelta(minutes=11),
        }
    ]

    assert [row["service_name"] for row in _stale_services(rows)] == ["worker_runtime"]


def test_stopped_optional_service_is_not_stale() -> None:
    rows = [
        {
            "service_name": "telegram",
            "status": "STOPPED",
            "last_heartbeat_at": None,
        }
    ]

    assert _stale_services(rows) == []


def test_internal_module_without_heartbeat_is_not_stale() -> None:
    rows = [
        {
            "service_name": "strategy_router",
            "status": "RUNNING",
            "last_heartbeat_at": None,
        }
    ]

    assert _stale_services(rows) == []


def test_runtime_health_refreshes_postgres_and_redis_dependency_health(
    postgres_test_schema,
    monkeypatch,
) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    StateGovernor(connection_factory=factory).ensure_initial_state()
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    import app.runtime.health_truth as health_truth

    monkeypatch.setattr(
        health_truth,
        "_check_redis_health",
        lambda redis_url: {"ok": True, "host": "redis", "port": 6379, "error": None},
    )

    result = HealthTruthService(connection_factory=factory).get_health_truth()
    services = {row["service_name"]: row for row in result["services"]}

    assert result["overall_status"] == "HEALTHY"
    assert result["stale_services"] == []
    assert services["fastapi"]["last_heartbeat_at"] is not None
    assert services["postgres"]["status"] == "HEALTHY"
    assert services["postgres"]["last_heartbeat_at"] is not None
    assert services["redis"]["status"] == "HEALTHY"
    assert services["redis"]["last_heartbeat_at"] is not None


def test_runtime_health_degrades_for_real_stale_service(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    StateGovernor(connection_factory=factory).ensure_initial_state()
    monkeypatch.delenv("REDIS_URL", raising=False)
    old_heartbeat = datetime.now(UTC) - timedelta(minutes=11)

    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, last_heartbeat_at)
            VALUES ('worker_runtime', 'runtime', 'RUNNING', %s)
            """,
            (old_heartbeat,),
        )

    result = HealthTruthService(connection_factory=factory).get_health_truth()

    assert result["overall_status"] == "DEGRADED"
    assert [row["service_name"] for row in result["stale_services"]] == ["worker_runtime"]


def test_runtime_health_does_not_report_ttl_expired_cycle_as_current(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    StateGovernor(connection_factory=factory).ensure_initial_state()
    monkeypatch.delenv("REDIS_URL", raising=False)
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM runtime_cycles_v2")
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, metadata_json)
            VALUES ('expired-running-health-cycle', 'PAPER', 'RUNNING', %s, '{}'::jsonb)
            """,
            (datetime.now(UTC) - timedelta(hours=2),),
        )

    result = HealthTruthService(connection_factory=factory).get_health_truth()

    assert result["active_cycle"] is None
    assert result["active_cycle_truth"]["freshness_state"] == "MISSING"
    with factory.connect() as conn:
        status = conn.execute(
            "SELECT status FROM runtime_cycles_v2 WHERE cycle_id='expired-running-health-cycle'"
        ).fetchone()["status"]
    assert status == "STALE_ABANDONED"
