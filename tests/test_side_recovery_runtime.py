from __future__ import annotations

import asyncio

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


class _SideEvidence:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.kwargs = None

    def run_recovery(self, **kwargs) -> dict[str, object]:
        self.calls.append("side")
        self.kwargs = kwargs
        return {"status": "OK"}


class _Downstream:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run_recompute(self, **kwargs) -> dict[str, object]:
        self.calls.append("downstream")
        return {"status": "OK"}


class _TrustedOrderbook:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def resolve(self, **kwargs) -> dict[str, object]:
        self.calls.append("trusted_orderbook")
        return {"status": "OK"}


class _EligibilityRecovery:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def run_recovery(self, **kwargs) -> dict[str, object]:
        self.calls.append("eligibility")
        return {"status": "OK"}


def test_market_service_runs_side_recovery_after_evidence_before_downstream(postgres_test_schema, monkeypatch) -> None:
    run_migrations()
    calls: list[str] = []
    side = _SideEvidence(calls)
    service = MarketService(
        settings=Settings(),
        gamma_client=_Gamma(),
        runtime_intelligence=_Intelligence(),
        brain_mesh_activation=_Activation(calls),
        evidence_refresh=_EvidenceRefresh(calls),
        side_evidence=side,
        trusted_orderbook=_TrustedOrderbook(calls),
        downstream_recompute=_Downstream(calls),
        eligibility_recovery=_EligibilityRecovery(calls),
    )
    monkeypatch.setattr(service, "_persist_runtime_snapshot", lambda **kwargs: "phase1-cycle")

    asyncio.run(service.refresh())

    assert calls == ["activation", "evidence", "side", "trusted_orderbook", "downstream", "eligibility"]
    assert side.kwargs["cycle_id"].startswith("v2-")
    assert side.kwargs["limit"] >= service._settings.top_n
