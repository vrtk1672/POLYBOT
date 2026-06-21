from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import PaperSessionService
from paper_session_helpers import prepare_paper_session_fixture


def test_reset_refuses_when_live_orders_exist(postgres_test_schema) -> None:
    prepare_paper_session_fixture()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO cycles (
                id, started_at, completed_at, status, mode, trigger_source, top_n
            )
            VALUES (
                '66666666-6666-4666-8666-666666666666',
                now(), now(), 'COMPLETED', 'PAPER', 'test', 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO live_orders (
                id, client_order_id, cycle_id, decision_id, market_id, token_id,
                side, action, price, size, notional, status, exchange_status,
                raw_request, raw_response
            )
            VALUES ('99999999-9999-4999-8999-999999999999','live-order-test','66666666-6666-4666-8666-666666666666',NULL,'market','token','YES','BUY',0.5,1,0.5,'PENDING','PENDING',%s,%s)
            """,
            (Jsonb({}), Jsonb({})),
        )

    result = PaperSessionService().reset(balance=1000, reason="safety test", created_by="test")

    assert result["status"] == "REJECTED"
    assert "LIVE_ORDERS_PRESENT" in result["errors"]


def test_reset_does_not_touch_shadow_or_live_tables(postgres_test_schema) -> None:
    prepare_paper_session_fixture()

    result = PaperSessionService().reset(balance=1000, reason="safety clean", created_by="test")

    assert result["status"] == "COMPLETED"
    with DatabaseConnectionFactory().connect() as conn:
        live = conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]
        shadow = conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]
    assert live == 0
    assert shadow == 0
