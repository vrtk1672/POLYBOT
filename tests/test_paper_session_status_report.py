from __future__ import annotations

from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import PaperSessionService
from paper_session_helpers import prepare_paper_session_fixture


def test_status_endpoint_separates_current_and_historical_counts(postgres_test_schema) -> None:
    prepare_paper_session_fixture()
    PaperSessionService().reset(balance=1000, reason="status test", created_by="test")

    fastapi_app = FastAPI()
    fastapi_app.include_router(create_router())
    app = TestClient(fastapi_app)
    response = app.get("/dashboard/api/v2/control/paper-session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_session"]["starting_balance"] == 1000.0
    assert payload["current_session_counts"]["paper_intents"] == 0
    assert payload["historical_totals"]["paper_intents"] == 1
    assert payload["previous_session_summary"]["status"] == "RESET_CLOSED"


def test_history_endpoint_returns_archived_session(postgres_test_schema) -> None:
    prepare_paper_session_fixture()
    PaperSessionService().reset(balance=1000, reason="history test", created_by="test")

    fastapi_app = FastAPI()
    fastapi_app.include_router(create_router())
    response = TestClient(fastapi_app).get("/dashboard/api/v2/control/paper-session/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert any(item["status"] == "RESET_CLOSED" for item in payload["sessions"])


def test_session_scoped_optional_filter_is_typed_for_null_and_non_null(postgres_test_schema) -> None:
    prepare_paper_session_fixture()
    result = PaperSessionService().reset(balance=1000, reason="typed optional filter test", created_by="test")
    active_session_id = result["new_session_id"]

    with DatabaseConnectionFactory().connect() as conn:
        null_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_position_closes
            WHERE (%s::text IS NULL OR paper_session_id = %s::text)
            """,
            (None, None),
        ).fetchone()
        scoped_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_position_closes
            WHERE (%s::text IS NULL OR paper_session_id = %s::text)
            """,
            (active_session_id, active_session_id),
        ).fetchone()

    assert int(null_row["count"]) >= 1
    assert int(scoped_row["count"]) == 0
