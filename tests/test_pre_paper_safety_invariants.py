from __future__ import annotations

import app.control_center.pre_paper_safety as module
from app.control_center.pre_paper_safety import PrePaperSafetyService


class _FakeRuntime:
    def __init__(self, **kwargs) -> None:
        pass

    def get_readiness(self):
        return {"runtime_life_state": "STOPPED"}


class _FakeSupervisor:
    def __init__(self, **kwargs) -> None:
        pass

    def get_life_path(self):
        return {"supervisor_life_state": "STOPPED"}


class _FakePaper:
    def __init__(self, **kwargs) -> None:
        pass

    def get_readiness(self):
        return {"system_power_state": "OFF"}


class _FakePaperSimulation:
    def __init__(self, **kwargs) -> None:
        pass

    def status(self):
        return {"enabled": False}


class _FakeScopedEvents:
    def __init__(self, **kwargs) -> None:
        pass

    def list_events(self, **kwargs):
        return {"counts": {"candidate_event_scoped": 0}, "blockers": ["NO_CANDIDATE_SCOPED_EVENT"]}


class _FakeActionability:
    def __init__(self, **kwargs) -> None:
        pass

    def list_actionability(self, **kwargs):
        return {"counts": {"actionable_small_paper": 0}, "blockers": ["NO_PAPER_ACTIONABILITY"]}


def test_pre_paper_safety_returns_not_ready_when_paper_simulation_off(monkeypatch) -> None:
    monkeypatch.setattr(module, "RuntimeReadinessService", _FakeRuntime)
    monkeypatch.setattr(module, "SupervisorLifePathService", _FakeSupervisor)
    monkeypatch.setattr(module, "PaperReadinessService", _FakePaper)
    monkeypatch.setattr(module, "PaperSimulationControlService", _FakePaperSimulation)
    monkeypatch.setattr(module, "CandidateScopedEventsService", _FakeScopedEvents)
    monkeypatch.setattr(module, "PaperActionabilityService", _FakeActionability)
    monkeypatch.setattr(PrePaperSafetyService, "_counts", lambda self: {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "open_paper_positions": 0,
        "live_orders": 0,
        "positions": 0,
        "duplicate_active_intent_risk": 0,
    })

    payload = PrePaperSafetyService().get_safety()

    assert payload["readiness_state"] == "PRE_PAPER_NOT_READY"
    assert "PAPER_SIMULATION_OFF" in payload["blockers"]
    assert "NO_CANDIDATE_SCOPED_EVENT" in payload["blockers"]
    assert payload["unified_blockers"][0]["blocker_code"]


def test_pre_paper_safety_reports_duplicate_intent_risk(monkeypatch) -> None:
    test_pre_paper_safety_returns_not_ready_when_paper_simulation_off(monkeypatch)
    monkeypatch.setattr(PrePaperSafetyService, "_counts", lambda self: {
        "paper_intents": 2,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "open_paper_positions": 0,
        "live_orders": 0,
        "positions": 0,
        "duplicate_active_intent_risk": 1,
    })

    payload = PrePaperSafetyService().get_safety()

    assert "DUPLICATE_ACTIVE_INTENT_RISK" in payload["blockers"]
