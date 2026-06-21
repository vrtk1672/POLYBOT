from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.downstream_evidence_recompute import DownstreamEvidenceRecomputeService


class _Power:
    def __init__(self, on: bool) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


class _Governor:
    def can_execute(self, action) -> bool:
        return True


class _Layer:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls


class _Thesis(_Layer):
    def build_profiles(self, **kwargs) -> dict[str, object]:
        self.calls.append(self.name)
        return {"status": "OK", "coordinator_decisions_checked": 2, "thesis_profiles_created": 0, "thesis_profiles_updated": 2}


class _Risk(_Layer):
    def evaluate_risk(self, **kwargs) -> dict[str, object]:
        self.calls.append(self.name)
        return {"status": "OK", "thesis_profiles_checked": 2, "risk_decisions_created": 0, "risk_decisions_updated": 2}


class _Exit(_Layer):
    def build_exit_plans(self, **kwargs) -> dict[str, object]:
        self.calls.append(self.name)
        return {"status": "OK", "risk_decisions_checked": 2, "exit_plans_created": 0, "exit_plans_updated": 2}


class _Eligibility(_Layer):
    def evaluate_candidates(self, **kwargs) -> dict[str, object]:
        self.calls.append(self.name)
        return {"status": "OK", "exit_plans_checked": 2, "candidates_created": 0, "candidates_updated": 2}


class _NoTrade(_Layer):
    def build_intents(self, **kwargs) -> dict[str, object]:
        self.calls.append(self.name)
        assert kwargs["write_intents"] is False
        assert kwargs["write_no_trade"] is True
        return {"status": "OK", "candidates_checked": 2, "no_trade_records_created": 0, "no_trade_records_updated": 2}


def test_system_off_prevents_downstream_recompute(postgres_test_schema) -> None:
    run_migrations()
    calls: list[str] = []
    service = DownstreamEvidenceRecomputeService(
        system_power=_Power(False),
        governor=_Governor(),
        thesis_service=_Thesis("thesis", calls),
        risk_service=_Risk("risk", calls),
        exit_service=_Exit("exit", calls),
        eligibility_service=_Eligibility("eligibility", calls),
        no_trade_service=_NoTrade("no_trade", calls),
    )

    result = service.run_recompute(cycle_id="recompute-off")

    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "SYSTEM_POWER_OFF"
    assert calls == []
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT COUNT(*) AS count FROM downstream_evidence_recompute_runs").fetchone()["count"]
    assert rows == 0


def test_system_on_recomputes_downstream_layers_in_order_and_records_summary(postgres_test_schema) -> None:
    run_migrations()
    calls: list[str] = []
    service = DownstreamEvidenceRecomputeService(
        system_power=_Power(True),
        governor=_Governor(),
        thesis_service=_Thesis("thesis", calls),
        risk_service=_Risk("risk", calls),
        exit_service=_Exit("exit", calls),
        eligibility_service=_Eligibility("eligibility", calls),
        no_trade_service=_NoTrade("no_trade", calls),
    )

    result = service.run_recompute(cycle_id="recompute-on", limit=25)

    assert result["status"] == "OK"
    assert calls == ["thesis", "risk", "exit", "eligibility", "no_trade"]
    assert result["risk_checked"] == 2
    assert result["risk_updated"] == 2
    assert result["exit_updated"] == 2
    assert result["eligibility_updated"] == 2
    assert result["no_trade_updated"] == 2
    assert result["orders_delta"] == 0
    assert result["fills_delta"] == 0
    assert result["positions_delta"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM downstream_evidence_recompute_runs WHERE cycle_id='recompute-on'").fetchone()
    assert row is not None
    assert row["status"] == "OK"


def test_recompute_is_idempotent_per_cycle(postgres_test_schema) -> None:
    run_migrations()
    calls: list[str] = []
    service = DownstreamEvidenceRecomputeService(
        system_power=_Power(True),
        governor=_Governor(),
        thesis_service=_Thesis("thesis", calls),
        risk_service=_Risk("risk", calls),
        exit_service=_Exit("exit", calls),
        eligibility_service=_Eligibility("eligibility", calls),
        no_trade_service=_NoTrade("no_trade", calls),
    )

    first = service.run_recompute(cycle_id="same-cycle")
    second = service.run_recompute(cycle_id="same-cycle")

    assert first["status"] == "OK"
    assert second["idempotent"] is True
    assert calls == ["thesis", "risk", "exit", "eligibility", "no_trade"]
