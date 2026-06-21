from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.coordinator_routes import create_coordinator_router
from app.db.connection import DatabaseConnectionFactory
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_coordinator_router())
    return TestClient(app)


def _brain_output(brain: str, output_type: str, recommendation: str, **extra) -> dict[str, object]:
    return BrainOutputService().create_brain_output(
        {"brain": brain, "output_type": output_type, "recommendation": recommendation, "status": "ACTIVE", **extra}
    )


def test_coordinator_api_returns_empty_truth(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        decisions = client.get("/coordinator/decisions/recent").json()
        conflicts = client.get("/coordinator/conflicts/recent").json()

    assert decisions["mock_data"] is False
    assert decisions["count"] == 0
    assert conflicts["mock_data"] is False
    assert conflicts["count"] == 0


def test_coordinator_api_reads_decisions(postgres_test_schema) -> None:
    _clear()
    output = _brain_output("no_trade", "NO_TRADE_HINT", "NO_TRADE", market_id="m-api", position_id="p-api", confidence=0.8)
    created = BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    with _client() as client:
        recent = client.get("/coordinator/decisions/recent").json()
        one = client.get(f"/coordinator/decisions/{created['coordinator_decision_id']}").json()
        by_market = client.get("/coordinator/market/m-api").json()
        by_position = client.get("/coordinator/position/p-api").json()

    assert recent["count"] == 1
    assert one["decision"]["final_state"] == "NO_TRADE"
    assert by_market["count"] == 1
    assert by_position["count"] == 1


def test_safe_post_coordinate_outputs_is_non_executing(postgres_test_schema) -> None:
    _clear()
    opportunity = _brain_output("opportunity", "OPPORTUNITY_HINT", "OPPORTUNITY_HINT", market_id="m-post")
    risk = _brain_output("risk", "RISK_WARNING", "CAUTION", market_id="m-post", confidence=0.9, risk_flags=["risk_high"])

    with _client() as client:
        response = client.post(
            "/coordinator/coordinate/outputs",
            json={"brain_output_ids": [opportunity["brain_output_id"], risk["brain_output_id"]], "market_id": "m-post"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["decision"]["final_state"] == "RISK_BLOCKED"
    assert payload["decision"]["execution_allowed"] is False
