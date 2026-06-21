from __future__ import annotations

from app.config import Settings
from app.db.migrate import run_migrations
from app.ingestion.market_service import MarketService


class _Gamma:
    async def fetch_active_events(self) -> list[dict]:
        return []


class _Intelligence:
    def __init__(self) -> None:
        self.called = False

    def refresh(self, **kwargs) -> None:
        self.called = True


class _Activation:
    def __init__(self) -> None:
        self.called = False
        self.kwargs = None

    def run_activation(self, **kwargs) -> dict[str, object]:
        self.called = True
        self.kwargs = kwargs
        return {"status": "OK"}


async def test_market_service_refresh_runs_brain_mesh_activation_under_system_on(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    intelligence = _Intelligence()
    activation = _Activation()
    service = MarketService(
        settings=Settings(),
        gamma_client=_Gamma(),
        runtime_intelligence=intelligence,
        brain_mesh_activation=activation,
    )
    monkeypatch.setattr(service, "_persist_runtime_snapshot", lambda **kwargs: "phase1-cycle")

    await service.refresh()

    assert intelligence.called is True
    assert activation.called is True
    assert activation.kwargs["phase1_cycle_id"] == "phase1-cycle"
