from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.brain_mesh_activation import BrainMeshActivationService


class _Power:
    def __init__(self, *, on: bool) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


class _Governor:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed

    def can_execute(self, action) -> bool:
        return self.allowed


class _Evidence:
    def __init__(self) -> None:
        self.called = False

    def run_runtime_evidence_loop(self, **kwargs) -> dict[str, object]:
        self.called = True
        return {"run_id": "evidence-run", "signals_created": 2}


class _Brain:
    def __init__(self, *, fail: bool = False) -> None:
        self.called = False
        self.fail = fail

    def run_runtime_brain(self, **kwargs) -> dict[str, object]:
        self.called = True
        if self.fail:
            raise RuntimeError("brain failed")
        return {"run_id": "brain-run", "brain_outputs_created": 3}


class _Coordinator:
    def __init__(self) -> None:
        self.called = False

    def run_runtime_coordinator(self, **kwargs) -> dict[str, object]:
        self.called = True
        return {"run_id": "coordinator-run", "coordinator_decisions_created": 4}


class _Thesis:
    def __init__(self) -> None:
        self.called = False

    def build_profiles(self, **kwargs) -> dict[str, object]:
        self.called = True
        return {"run_id": "thesis-run", "thesis_profiles_created": 5, "thesis_profiles_updated": 1}


def _service(*, on: bool = True, brain_fail: bool = False):
    evidence = _Evidence()
    brain = _Brain(fail=brain_fail)
    coordinator = _Coordinator()
    thesis = _Thesis()
    service = BrainMeshActivationService(
        system_power=_Power(on=on),
        governor=_Governor(),
        evidence_service=evidence,
        brain_service=brain,
        coordinator_service=coordinator,
        thesis_service=thesis,
    )
    return service, evidence, brain, coordinator, thesis


def test_system_off_prevents_brain_mesh_activation(postgres_test_schema) -> None:
    run_migrations()
    service, evidence, brain, coordinator, thesis = _service(on=False)

    result = service.run_activation(cycle_id="off-cycle")

    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "SYSTEM_POWER_OFF"
    assert evidence.called is False
    assert brain.called is False
    assert coordinator.called is False
    assert thesis.called is False
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM brain_mesh_activation_runs").fetchone()["count"]
    assert count == 0


def test_system_on_calls_all_brain_mesh_components_and_records_run(postgres_test_schema) -> None:
    run_migrations()
    service, evidence, brain, coordinator, thesis = _service(on=True)

    result = service.run_activation(cycle_id="on-cycle", phase1_cycle_id="phase1", limit=10)

    assert result["status"] == "OK"
    assert result["evidence_created"] == 2
    assert result["brain_outputs_created"] == 3
    assert result["coordinator_decisions_created"] == 4
    assert result["thesis_profiles_created"] == 5
    assert evidence.called and brain.called and coordinator.called and thesis.called
    assert result["orders_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM brain_mesh_activation_runs WHERE cycle_id = 'on-cycle'").fetchone()
    assert row is not None
    assert row["status"] == "OK"


def test_activation_handles_partial_failure_safely(postgres_test_schema) -> None:
    run_migrations()
    service, evidence, brain, coordinator, thesis = _service(on=True, brain_fail=True)

    result = service.run_activation(cycle_id="degraded-cycle")

    assert result["status"] == "DEGRADED"
    assert "runtime_brain_adapter:RuntimeError:brain failed" in result["error_message"]
    assert evidence.called and brain.called and coordinator.called and thesis.called
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
