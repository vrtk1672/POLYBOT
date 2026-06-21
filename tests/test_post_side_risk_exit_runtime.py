from __future__ import annotations

import asyncio

from app.config import Settings
from app.ingestion.market_service import MarketService
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket


class _Gamma:
    async def fetch_active_events(self):
        return []


class _Layer:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls

    def run_activation(self, **kwargs):
        self.calls.append(self.name)

    def run_refresh(self, **kwargs):
        self.calls.append(self.name)

    def run_recovery(self, **kwargs):
        self.calls.append(self.name)

    def run_recompute(self, **kwargs):
        self.calls.append(self.name)

    def build_intents(self, **kwargs):
        self.calls.append(self.name)

    def run_execution(self, **kwargs):
        self.calls.append(self.name)

    def run_exit_loop(self, **kwargs):
        self.calls.append(self.name)


class _RuntimeIntelligence:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def refresh(self, **kwargs):
        self.calls.append("intelligence")


def test_market_service_runs_post_side_before_eligibility(monkeypatch) -> None:
    calls: list[str] = []
    service = MarketService(
        Settings(),
        _Gamma(),
        runtime_intelligence=_RuntimeIntelligence(calls),
        brain_mesh_activation=_Layer("brain", calls),
        evidence_refresh=_Layer("evidence", calls),
        side_evidence=_Layer("side", calls),
        downstream_recompute=_Layer("downstream", calls),
        post_side_readiness=_Layer("post_side", calls),
        eligibility_recovery=_Layer("eligibility", calls),
        paper_intent_gate=_Layer("intent", calls),
        paper_execution=_Layer("execution", calls),
        paper_exit_loop=_Layer("exit_loop", calls),
    )

    monkeypatch.setattr(service._runtime_cycle_orchestrator, "start_cycle", lambda metadata=None: "cycle-test")
    monkeypatch.setattr(service._runtime_cycle_orchestrator, "run_stage_guard", lambda *args, **kwargs: None)
    monkeypatch.setattr(service._runtime_cycle_orchestrator, "mark_stage_started", lambda *args, **kwargs: None)
    monkeypatch.setattr(service._runtime_cycle_orchestrator, "mark_stage_finished", lambda *args, **kwargs: None)
    monkeypatch.setattr(service._runtime_cycle_orchestrator, "finish_cycle", lambda *args, **kwargs: None)
    monkeypatch.setattr(service._runtime_cycle_orchestrator, "should_run_stage", lambda stage: stage == "intelligence")
    monkeypatch.setattr(service, "_persist_runtime_snapshot", lambda **kwargs: "phase1-cycle")
    monkeypatch.setattr(service._data_foundation, "process_markets", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_rank_markets", lambda markets: [])
    monkeypatch.setattr(service, "_publish_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.ingestion.market_service.render_top_markets_table", lambda rows: None)

    asyncio.run(service.refresh())

    assert calls[:6] == ["intelligence", "brain", "evidence", "side", "downstream", "post_side"]
    assert calls.index("post_side") < calls.index("eligibility")
