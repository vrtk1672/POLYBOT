from __future__ import annotations

from app.config import Settings
from app.db.migrate import run_migrations
from app.ingestion.market_service import MarketService


class _Gamma:
    async def fetch_active_events(self) -> list[dict]:
        return []


class _Intelligence:
    def refresh(self, **kwargs) -> None:
        return None


class _Activation:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run_activation(self, **kwargs) -> dict[str, object]:
        self.calls.append("activation")
        return {"status": "OK"}


class _EvidenceRefresh:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run_refresh(self, **kwargs) -> dict[str, object]:
        self.calls.append("evidence")
        return {"status": "OK"}


class _Downstream:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.kwargs = None

    def run_recompute(self, **kwargs) -> dict[str, object]:
        self.calls.append("downstream")
        self.kwargs = kwargs
        return {"status": "OK"}


class _EligibilityRecovery:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.kwargs = None

    def run_recovery(self, **kwargs) -> dict[str, object]:
        self.calls.append("eligibility_recovery")
        self.kwargs = kwargs
        return {"status": "OK"}


async def test_market_service_runs_downstream_recompute_after_evidence_refresh(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    calls: list[str] = []
    downstream = _Downstream(calls)
    eligibility_recovery = _EligibilityRecovery(calls)
    service = MarketService(
        settings=Settings(),
        gamma_client=_Gamma(),
        runtime_intelligence=_Intelligence(),
        brain_mesh_activation=_Activation(calls),
        evidence_refresh=_EvidenceRefresh(calls),
        downstream_recompute=downstream,
        eligibility_recovery=eligibility_recovery,
    )
    monkeypatch.setattr(service, "_persist_runtime_snapshot", lambda **kwargs: "phase1-cycle")

    await service.refresh()

    assert calls == ["activation", "evidence", "downstream", "eligibility_recovery"]
    assert downstream.kwargs["cycle_id"].startswith("v2-")
    assert downstream.kwargs["limit"] >= service._settings.top_n
    assert eligibility_recovery.kwargs["cycle_id"].startswith("v2-")
    assert eligibility_recovery.kwargs["limit"] >= service._settings.top_n
