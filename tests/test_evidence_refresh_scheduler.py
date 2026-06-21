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
    def run_activation(self, **kwargs) -> dict[str, object]:
        return {"status": "OK"}


class _EvidenceRefresh:
    def __init__(self) -> None:
        self.called = False
        self.kwargs = None

    def run_refresh(self, **kwargs) -> dict[str, object]:
        self.called = True
        self.kwargs = kwargs
        return {"status": "OK"}


async def test_market_service_refresh_runs_evidence_refresh_after_brain_activation(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    evidence = _EvidenceRefresh()
    service = MarketService(
        settings=Settings(),
        gamma_client=_Gamma(),
        runtime_intelligence=_Intelligence(),
        brain_mesh_activation=_Activation(),
        evidence_refresh=evidence,
    )
    monkeypatch.setattr(service, "_persist_runtime_snapshot", lambda **kwargs: "phase1-cycle")

    await service.refresh()

    assert evidence.called is True
    assert evidence.kwargs["limit"] == service._settings.top_n
    assert evidence.kwargs["cycle_id"].startswith("v2-")
