from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.candidate_producer_freshness import CandidateProducerFreshnessService
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.runtime_supervisor import RuntimeSupervisorService, RuntimeSupervisorStartRequest, RuntimeSupervisorStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


def test_system_on_supervisor_triggers_candidate_producer_path(postgres_test_schema, monkeypatch) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-before", now - timedelta(minutes=5))
    producer = _UpdatingCandidateProducer("candidate-before")
    store = RuntimeSupervisorStore()

    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=store,
        paper_simulation=_PaperControl(),
        candidate_producer=producer,
        run_in_background=False,
        sleep_between_cycles=False,
    )
    result = supervisor.start(RuntimeSupervisorStartRequest(actor="pytest", reason="candidate producer test", interval_seconds=30))

    assert result.supervisor_status in {"RUNNING", "DEGRADED"}
    assert result.cycles_completed == 1
    assert producer.calls == 1
    payload = CandidateProducerFreshnessService(
        connection_factory=DatabaseConnectionFactory(),
        supervisor_life_path=_FakeSupervisorLife("ALIVE"),
        runtime_readiness=_FakeRuntimeReadiness("ALIVE"),
        paper_readiness=_FakePaperReadiness(),
    ).get_freshness()
    assert payload["candidate_update_result"] == "CANDIDATES_UPDATED"
    assert payload["candidate_producer_state"] == "RUNNING"
    assert payload["updated_after_system_on"]["candidates"] is True
    assert _artifact_counts()["paper_orders"] == 0
    assert _artifact_counts()["paper_fills"] == 0
    assert _artifact_counts()["paper_positions"] == 0


def test_candidate_freshness_fresh_when_rows_update_after_system_on(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-after", now)

    payload = _service(supervisor_life="ALIVE").get_freshness()

    assert payload["candidate_producer_state"] == "RUNNING"
    assert payload["candidate_freshness_state"] == "FRESH"
    assert payload["candidate_update_result"] == "CANDIDATES_UPDATED"
    assert payload["supervisor_candidate_path_result"] == "PASSED"


def test_candidate_freshness_stale_with_explicit_reason_when_no_update(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-stale", now - timedelta(hours=2))

    payload = _service(supervisor_life="ALIVE").get_freshness()

    assert payload["candidate_producer_state"] in {"BLOCKED", "STALE"}
    assert payload["candidate_update_result"] in {"CANDIDATES_BLOCKED_BY_SOURCE", "CANDIDATES_NOT_UPDATED_WITH_REASON"}
    assert "CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON" in payload["blockers"] or "CANDIDATE_LEDGER_STALE" in payload["blockers"]
    assert payload["updated_after_system_on"]["candidates"] is False


def test_candidate_producer_endpoint_shape_and_read_only(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="OFF", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-read-only", now - timedelta(minutes=5))
    before = _artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/candidate-producer-freshness")

    assert response.status_code == 200
    payload = response.json()
    for field in (
        "candidate_producer_state",
        "candidate_freshness_state",
        "candidate_update_result",
        "supervisor_candidate_path_result",
        "system_power_state",
        "runtime_life_state",
        "supervisor_life_state",
        "last_candidate_updated_at",
        "updated_after_system_on",
        "blockers",
        "warnings",
        "errors",
        "source",
        "last_updated",
    ):
        assert field in payload
    assert _artifact_counts() == before


def test_paper_readiness_remains_blocked_when_paper_simulation_off(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-paper-off", now)

    payload = _service(supervisor_life="ALIVE").get_freshness()

    assert payload["paper_readiness"]["paper_readiness_state"] == "BLOCKED"
    assert payload["paper_readiness"]["paper_simulation_state"] == "OFF"


def test_runtime_readiness_exposes_candidate_update_warning(postgres_test_schema) -> None:
    now = datetime.now(UTC)
    _prepare_tables(system_power="ON", transition_at=now - timedelta(minutes=1))
    _insert_candidate("candidate-old-runtime-warning", now - timedelta(hours=2))

    payload = RuntimeReadinessService(connection_factory=DatabaseConnectionFactory(), runtime_supervisor_store=RuntimeSupervisorStore()).get_readiness()

    assert payload["candidate_producer_state"] != "RUNNING"
    assert payload["candidate_update_warning"] == "CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON"
    assert "CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON" in payload["warnings"]


def _service(*, supervisor_life: str) -> CandidateProducerFreshnessService:
    return CandidateProducerFreshnessService(
        connection_factory=DatabaseConnectionFactory(),
        supervisor_life_path=_FakeSupervisorLife(supervisor_life),
        runtime_readiness=_FakeRuntimeReadiness("ALIVE" if supervisor_life == "ALIVE" else "STOPPED"),
        paper_readiness=_FakePaperReadiness(),
    )


class _UpdatingCandidateProducer:
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id
        self.calls = 0

    def evaluate_candidates(self, *, limit: int, include_blocked: bool, write_candidates: bool) -> dict[str, Any]:
        self.calls += 1
        with DatabaseConnectionFactory().connect() as conn, conn.transaction():
            conn.execute(
                "UPDATE paper_eligibility_candidates SET updated_at = now() WHERE eligibility_id = %s",
                (self.candidate_id,),
            )
        return {
            "status": "OK",
            "exit_plans_checked": 1,
            "candidates_created": 0,
            "candidates_updated": 1,
            "eligible_count": 1,
            "blocked_count": 0,
            "orders_created": 0,
            "fills_created": 0,
            "positions_created": 0,
            "live_actions_created": 0,
            "errors": [],
        }


class _FakeSupervisorLife:
    def __init__(self, state: str) -> None:
        self.state = state

    def get_life_path(self) -> dict[str, Any]:
        return {
            "supervisor_life_state": self.state,
            "runtime_life_state": "ALIVE" if self.state == "ALIVE" else "STOPPED",
            "system_power_state": "ON" if self.state == "ALIVE" else "OFF",
            "supervisor_last_heartbeat": datetime.now(UTC).isoformat(),
            "last_cycle_completed_at": datetime.now(UTC).isoformat(),
        }


class _FakeRuntimeReadiness:
    def __init__(self, state: str) -> None:
        self.state = state

    def get_readiness(self) -> dict[str, Any]:
        return {
            "runtime_life_state": self.state,
            "readiness_state": "READY" if self.state == "ALIVE" else "NOT_READY",
            "system_power_state": "ON" if self.state == "ALIVE" else "OFF",
            "blockers": [],
        }


class _FakePaperReadiness:
    def get_readiness(self) -> dict[str, Any]:
        return {
            "paper_readiness_state": "BLOCKED",
            "paper_simulation_state": "OFF",
            "readiness_state": "BLOCKED",
            "blockers": ["PAPER_SIMULATION_OFF"],
            "last_updated": datetime.now(UTC).isoformat(),
        }


class _Governor:
    def __init__(self) -> None:
        self.state = RuntimeState(
            current_mode=RuntimeMode.DATA_ONLY,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=SystemPower.ON,
        )

    def get_current_state(self) -> RuntimeState:
        return self.state

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value}

    def get_permissions(self) -> RuntimePermissions:
        return RuntimePermissions(can_collect_data=True, can_run_intelligence=True)


class _PaperControl:
    def status_record(self, include_paper_truth: bool = False):
        class _Record:
            enabled = False
            status = "DISABLED"
            warnings: list[str] = []
            errors: list[str] = []

        return _Record()


class _QueryService:
    def overview(self):
        return _envelope("runtime_state", {"source_counts": {"event_log": 1}})

    def live_flow(self):
        return _envelope("event_log", {"events": [{"id": "event"}], "count": 1})

    def organs(self):
        return _envelope("service_health", {"services": [], "count": 0})

    def closest_actionable(self):
        return _envelope("risk_evidence", {"candidates": [], "count": 0})

    def risk_evidence(self):
        return _envelope("risk_evidence", {})

    def positions(self):
        return _envelope("paper_positions", {"positions": []})

    def lifecycle_governance(self):
        return _envelope("lifecycle_governance", {})

    def pnl_ledger(self):
        return _envelope("paper_daily_pnl", {})

    def no_trade(self):
        return _envelope("no_trade_log", {"records": []})

    def ai(self):
        return _envelope("ai_context_router", {})

    def logs(self):
        return _envelope("event_log", {"events": []})

    def truth_state(self):
        return _envelope("truth_state_registry", {})


def _envelope(source: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"status": "REAL", "source": source, "last_updated": datetime.now(UTC).isoformat(), "truth_state": "ACTIVE_FRESH", "data": data, "warnings": [], "errors": []}


def _prepare_tables(*, system_power: str, transition_at: datetime) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_eligibility_candidates",
            "paper_eligibility_runs",
            "runtime_cycles_v2",
            "event_log",
            "system_state",
            "system_state_history",
            "system_power_transitions",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO system_state (
                current_mode, state_status, kill_switch_active, cooldown_active,
                attack_mode_active, reason, actor, system_power, system_power_transition_at, metadata_json
            )
            VALUES ('DATA_ONLY', 'ACTIVE', false, false, false, 'candidate producer test', 'pytest', %s, %s, '{}'::jsonb)
            """,
            (system_power, transition_at),
        )


def _insert_candidate(candidate_id: str, updated_at: datetime) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence, lineage_trusted,
                risk_approved, exit_ready, generated_by, producer_name, updated_at
            )
            VALUES (%s, 'market-candidate-producer', 'YES', 'ELIGIBLE', 0.9,
                    '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, true, true, true,
                    'pytest', 'pytest', %s)
            """,
            (candidate_id, updated_at),
        )


def _artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count(conn, table)
            for table in ("paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "live_orders", "orders_v2", "fills_v2", "positions")
        }


def _count(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}
