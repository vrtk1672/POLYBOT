from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.truth_contract import (
    ControlCenterStatus,
    ControlCenterTruthState,
    TruthContractError,
    not_implemented_envelope,
    require_candidate_truth_state,
    require_decision_source,
    require_health_source,
    require_pnl_source,
    truth_envelope,
)


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_valid_real_envelope_requires_source_and_known_truth_state() -> None:
    envelope = truth_envelope(
        status=ControlCenterStatus.REAL,
        source="paper_ledger",
        truth_state=ControlCenterTruthState.ACTIVE_FRESH,
        data={"value": 1},
        last_updated="2026-06-07T00:00:00+00:00",
        stale_after_seconds=60,
    )

    payload = envelope.to_dict()
    assert payload["status"] == "REAL"
    assert payload["source"] == "paper_ledger"
    assert payload["truth_state"] == "ACTIVE_FRESH"
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert isinstance(payload["data"], dict)


def test_real_without_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="REAL requires source"):
        truth_envelope(
            status=ControlCenterStatus.REAL,
            source=None,
            truth_state=ControlCenterTruthState.ACTIVE_FRESH,
        )


def test_real_with_unknown_truth_state_is_rejected() -> None:
    with pytest.raises(ValueError, match="REAL cannot use truth_state UNKNOWN"):
        truth_envelope(
            status=ControlCenterStatus.REAL,
            source="runtime_state",
            truth_state=ControlCenterTruthState.UNKNOWN,
        )


def test_error_without_errors_is_rejected() -> None:
    with pytest.raises(ValueError, match="ERROR requires at least one error"):
        truth_envelope(
            status=ControlCenterStatus.ERROR,
            source="dashboard_service",
            truth_state=ControlCenterTruthState.UNKNOWN,
        )


def test_not_implemented_response_does_not_claim_live_data() -> None:
    payload = not_implemented_envelope(source="control_center_truth_contract").to_dict()

    assert payload["status"] == "NOT_IMPLEMENTED"
    assert payload["truth_state"] == "UNKNOWN"
    assert payload["data"] == {}
    serialized = str(payload).lower()
    assert "healthy" not in serialized
    assert "green" not in serialized
    assert "pnl" in serialized
    assert "live data" in serialized


def test_arrays_and_data_object_are_enforced() -> None:
    payload = truth_envelope(
        status=ControlCenterStatus.MISSING,
        source=None,
        truth_state=ControlCenterTruthState.UNKNOWN,
        data=None,
        warnings=["missing source"],
        errors=None,
    ).to_dict()
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["errors"], list)
    assert isinstance(payload["data"], dict)

    with pytest.raises(ValueError, match="data must be an object"):
        truth_envelope(
            status=ControlCenterStatus.PARTIAL,
            source="runtime_state",
            truth_state=ControlCenterTruthState.LAST_KNOWN,
            data=["not", "a", "dict"],  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="warnings and errors"):
        truth_envelope(
            status=ControlCenterStatus.MISSING,
            source=None,
            truth_state=ControlCenterTruthState.UNKNOWN,
            warnings="missing",  # type: ignore[arg-type]
        )


def test_domain_guards_reject_missing_required_sources() -> None:
    with pytest.raises(TruthContractError, match="PnL requires source"):
        require_pnl_source(None)
    with pytest.raises(TruthContractError, match="Health requires source"):
        require_health_source("")
    with pytest.raises(TruthContractError, match="Decision requires source"):
        require_decision_source(None)
    with pytest.raises(TruthContractError, match="Candidate requires truth_state"):
        require_candidate_truth_state(None)

    require_pnl_source("paper_pnl_ledger")
    require_health_source("service_health_heartbeat")
    require_decision_source("risk_evidence_source")
    require_candidate_truth_state(ControlCenterTruthState.REFRESH_REQUIRED)


def test_truth_contract_demo_endpoint_returns_required_envelope() -> None:
    with _client() as client:
        response = client.get("/dashboard/api/v2/control/truth-contract")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "status",
        "source",
        "last_updated",
        "stale_after_seconds",
        "truth_state",
        "data",
        "warnings",
        "errors",
    } <= set(payload)
    assert payload["status"] == "NOT_IMPLEMENTED"
    assert payload["source"] == "control_center_truth_contract"
    assert payload["truth_state"] == "UNKNOWN"
    assert payload["data"] == {}
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["errors"], list)


def test_existing_dashboard_and_control_center_routes_still_load() -> None:
    with _client() as client:
        dashboard = client.get("/dashboard")
        control_center = client.get("/control-center")

    assert dashboard.status_code == 200
    assert control_center.status_code == 200
    assert "POLYBOT Operator Control Room" in dashboard.text
    assert '<div id="root"></div>' in control_center.text
