from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.last_mile_orderbook_refresh import LastMileOrderbookRefreshService
from app.services.paper_runtime_decisions import build_paper_runtime_decision


class _BookHttp:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def get_json(self, url: str, *, params=None):
        if self.fail:
            raise RuntimeError("connector down")
        token_id = (params or {}).get("token_id")
        return {
            "asset_id": token_id,
            "market": "condition-a",
            "bids": [{"price": "0.49", "size": "120"}],
            "asks": [{"price": "0.52", "size": "110"}],
        }, 10


def test_paper_candidate_stale_orderbook_triggers_refresh_and_clears_blocker(postgres_test_schema) -> None:
    _prepare()
    _insert_stale_snapshot()
    row = _review_row()
    service = LastMileOrderbookRefreshService(http_client=_BookHttp())

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        decision = build_paper_runtime_decision(conn, row, last_mile_orderbook_refresh=service)

    assert decision["decision"] == "ENTER"
    assert decision["paper_enter_allowed"] is True
    assert "STALE_ORDERBOOK" not in decision["blockers_json"]
    assert decision["last_mile_refresh_attempted"] is True
    assert decision["last_mile_refresh_state"] == "REFRESHED_FRESH"
    assert decision["orderbook_snapshot_id"] is not None


def test_failed_refresh_keeps_exact_blocker_and_no_enter(postgres_test_schema) -> None:
    _prepare()
    _insert_stale_snapshot()
    row = _review_row()
    service = LastMileOrderbookRefreshService(http_client=_BookHttp(fail=True))

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        decision = build_paper_runtime_decision(conn, row, last_mile_orderbook_refresh=service)

    assert decision["decision"] == "BLOCK"
    assert decision["paper_enter_allowed"] is False
    assert "ORDERBOOK_CONNECTOR_ERROR" in decision["blockers_json"]
    assert decision["last_mile_refresh_state"] == "FAILED"


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("last_mile_orderbook_refresh_attempts", "orderbook_snapshots"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _insert_stale_snapshot() -> None:
    old = datetime.now(UTC) - timedelta(minutes=20)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid,
                best_ask, spread, mid_price, liquidity_score, source,
                snapshot_status, is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('stale-book','market-a','token-yes','YES',0.48,0.52,0.04,0.50,0.6,'test',
                    'OK',false,%s,%s,%s)
            """,
            (old, old, old),
        )


def _review_row() -> dict[str, object]:
    return {
        "paper_observation_policy_review_id": "review-a",
        "proactive_candidate_seed_id": "seed-a",
        "seed_mesh_inquiry_id": "inquiry-a",
        "adapter_payload_id": "payload-a",
        "opportunity_score_id": "score-a",
        "market_id": "market-a",
        "condition_id": "condition-a",
        "side": "YES",
        "token_id": "token-yes",
        "observation_allowed_by_policy": True,
        "decision_band": "PAPER_OBSERVATION",
        "opportunity_score": 62,
        "edge_state": "EDGE_SUPPORTED",
        "thesis_state": "THESIS_SUPPORTED",
        "risk_state": "RISK_OK",
        "capital_state": "CAPITAL_WATCH",
        "exit_state": "EXIT_READY",
        "lifecycle_state": "DATA_ONLY_RESEARCH",
        "orderbook_state": "FRESH",
        "token_verification_state": "TOKENS_VERIFIED",
        "candidate_event_scope_state": "CANDIDATE_SCOPED",
        "lineage_state": "COMPLETE",
        "hard_blockers_json": [],
        "policy_blockers_json": [],
        "soft_blockers_json": ["capital_watch_not_full_paper_ready"],
        "lineage_json": {"source_event_id": "event-a"},
        "duplicate_group_size": 1,
        "market_side_rank": 1,
        "diversity_score": 70,
        "decision_batch_id": "batch-a",
        "selection_rank": 1,
        "execution_allowed": False,
        "paper_allowed": False,
        "shadow_allowed": False,
        "live_allowed": False,
    }


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
