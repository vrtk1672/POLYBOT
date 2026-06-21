from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_runtime_decision


def test_autopsy_endpoints_return_non_empty_output(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-report",
        market_id="m-report",
        side="NO",
        decision="WATCH",
        score=55.46,
        blockers=["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
    )
    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)

    assert client.get("/dashboard/api/v2/control/decision-autopsy").json()["items"]
    assert client.get("/dashboard/api/v2/control/decision-autopsy/top-blockers").json()["top_blockers"]
    assert client.get("/dashboard/api/v2/control/decision-autopsy/closest-actionable").json()["items"]
    assert client.get("/dashboard/api/v2/control/supervisor-autopsy").json()["status"] == "OK"
    assert client.get("/dashboard/api/v2/control/paper-delta-autopsy").json()["status"] == "OK"
