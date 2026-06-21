from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.polymarket_token_truth import PolymarketTokenTruthService, parse_gamma_token_binding
from app.services.system_power import SystemPowerService


class _FakeCLOB:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[dict[str, object], int]:
        token_id = str((params or {}).get("token_id"))
        self.calls.append({"url": url, "params": dict(params or {})})
        payload = self.payloads.get(token_id)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise RuntimeError("token not found")
        return payload, 5


def _book(*, token: str, condition: str = "condition-1", bid: str = "0.44", ask: str = "0.45") -> dict[str, object]:
    return {
        "market": condition,
        "asset_id": token,
        "bids": [{"price": bid, "size": "1500"}],
        "asks": [{"price": ask, "size": "1600"}],
    }


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "polymarket_token_truth_traces",
            "polymarket_token_truth_runs",
            "polymarket_token_bindings",
            "trusted_orderbook_evidence_links",
            "paper_eligibility_candidates",
            "orderbook_snapshots",
            "market_snapshots_v2",
            "markets_v2",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="token-truth-prepare")


def _seed(
    suffix: str,
    *,
    side: str | None = "YES",
    market_id: str | None = None,
    condition_id: str = "condition-1",
    stored_yes: str | None = None,
    stored_no: str | None = None,
    gamma_yes: str | None = None,
    gamma_no: str | None = None,
    raw_extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    market_id = market_id or f"market-{suffix}"
    stored_yes = stored_yes or f"yes-stored-{suffix}"
    stored_no = stored_no or f"no-stored-{suffix}"
    gamma_yes = gamma_yes or stored_yes
    gamma_no = gamma_no or stored_no
    candidate_id = f"eligibility-{suffix}"
    raw = {
        "id": market_id,
        "conditionId": condition_id,
        "question": f"Question {suffix}?",
        "slug": f"slug-{suffix}",
        "clobTokenIds": [gamma_yes, gamma_no],
        "outcomes": ["Yes", "No"],
        "active": True,
        "closed": False,
        "archived": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
    }
    raw.update(raw_extra or {})
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, yes_token_id, no_token_id,
                accepting_orders, closed, archived, active, raw_market_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, true, false, false, true, %s)
            """,
            (market_id, condition_id, f"Question {suffix}?", f"slug-{suffix}", stored_yes, stored_no, Jsonb(raw)),
        )
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (
                snapshot_id, market_id, cycle_id, correlation_id, accepting_orders,
                closed, data_completeness_score, stale, snapshot_at, raw_snapshot_json
            )
            VALUES (%s, %s, %s, %s, true, false, 1.0, false, now(), %s)
            """,
            (f"snapshot-{suffix}", market_id, str(uuid4()), f"corr-{suffix}", Jsonb(raw)),
        )
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                signal_ids, market_id, side, status, eligibility_score,
                eligibility_blockers, missing_requirements, evidence,
                link_confidence, lineage_trusted, risk_approved, exit_ready,
                not_dry_run, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, %s, %s, '[]'::jsonb, %s, %s, 'BLOCKED', 0,
                %s, %s, '{}'::jsonb, 0.95, true, false, false, true, true, false
            )
            """,
            (
                candidate_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                market_id,
                side,
                Jsonb(["MISSING_FRESH_ORDERBOOK"]),
                Jsonb(["MISSING_FRESH_ORDERBOOK"]),
            ),
        )
    return {
        "candidate_id": candidate_id,
        "market_id": market_id,
        "condition_id": condition_id,
        "stored_yes": stored_yes,
        "stored_no": stored_no,
        "gamma_yes": gamma_yes,
        "gamma_no": gamma_no,
    }


def _latest_trace(candidate_id: str) -> dict[str, Any]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute("SELECT * FROM polymarket_token_truth_traces WHERE candidate_id=%s ORDER BY id DESC LIMIT 1", (candidate_id,)).fetchone())


def test_gamma_token_json_array_parses_and_maps_yes_no() -> None:
    parsed = parse_gamma_token_binding({"conditionId": "condition", "clobTokenIds": '["yes-token","no-token"]', "outcomes": '["Yes","No"]'})

    assert parsed["status"] == "OK"
    assert parsed["tokens"]["YES"] == "yes-token"
    assert parsed["tokens"]["NO"] == "no-token"


def test_no_maps_to_no_token_and_condition_market_not_used_as_token(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("no", side="NO")
    fake = _FakeCLOB({ids["gamma_no"]: _book(token=ids["gamma_no"], condition=ids["condition_id"])})

    PolymarketTokenTruthService(http_client=fake).run_recovery(cycle_id="token-no", candidate_limit=1, gamma_market_limit=0)

    assert fake.calls[0]["params"]["token_id"] == ids["gamma_no"]
    trace = _latest_trace(ids["candidate_id"])
    assert trace["expected_token_id"] != ids["condition_id"]
    assert trace["expected_token_id"] != ids["market_id"]
    assert trace["classification"] == "VERIFIED_BY_CLOB_BOOK"


def test_token_outcome_order_mismatch_is_detected() -> None:
    parsed = parse_gamma_token_binding({"clobTokenIds": ["a", "b"], "outcomes": ["Up", "Down"]})

    assert parsed["status"] == "TOKEN_OUTCOME_ORDER_MISMATCH"


def test_ambiguous_token_mapping_blocks_book_request(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("ambiguous", raw_extra={"clobTokenIds": ["a", "b", "c"], "outcomes": []})
    fake = _FakeCLOB({})

    PolymarketTokenTruthService(http_client=fake).run_recovery(cycle_id="token-ambiguous", candidate_limit=1, gamma_market_limit=0)

    assert fake.calls == []
    assert _latest_trace(ids["candidate_id"])["classification"] == "AMBIGUOUS_TOKEN_MAPPING"


def test_valid_clob_book_creates_snapshot_and_trusted_link(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("valid", side="YES")

    result = PolymarketTokenTruthService(http_client=_FakeCLOB({ids["gamma_yes"]: _book(token=ids["gamma_yes"], condition=ids["condition_id"])})).run_recovery(
        cycle_id="token-valid",
        candidate_limit=1,
        gamma_market_limit=0,
    )

    assert result["verified_token_books"] == 1
    assert result["orderbook_snapshots_created"] == 1
    assert result["trusted_links_created"] == 1
    assert _latest_trace(ids["candidate_id"])["classification"] == "VERIFIED_BY_CLOB_BOOK"


def test_condition_mismatch_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("condition-mismatch", side="YES")

    PolymarketTokenTruthService(http_client=_FakeCLOB({ids["gamma_yes"]: _book(token=ids["gamma_yes"], condition="other")})).run_recovery(
        cycle_id="token-condition-mismatch",
        candidate_limit=1,
        gamma_market_limit=0,
    )

    assert _latest_trace(ids["candidate_id"])["classification"] == "CONDITION_ID_MISMATCH"


def test_token_not_found_classified_precisely(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("not-found", side="YES")

    PolymarketTokenTruthService(http_client=_FakeCLOB({})).run_recovery(cycle_id="token-not-found", candidate_limit=1, gamma_market_limit=0)

    assert _latest_trace(ids["candidate_id"])["classification"] == "CLOB_TOKEN_NOT_FOUND_DESPITE_GAMMA_TOKEN"


def test_non_tradable_closed_market_blocks_clob(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("closed", side="YES", raw_extra={"closed": True, "active": False})
    fake = _FakeCLOB({ids["gamma_yes"]: _book(token=ids["gamma_yes"], condition=ids["condition_id"])})

    PolymarketTokenTruthService(http_client=fake).run_recovery(cycle_id="token-closed", candidate_limit=1, gamma_market_limit=0)

    assert fake.calls == []
    assert _latest_trace(ids["candidate_id"])["classification"] == "MARKET_CLOSED"


def test_deterministic_backfill_updates_stale_candidate_identity(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("stale", side="YES", stored_yes="old-yes", gamma_yes="new-yes")

    PolymarketTokenTruthService(http_client=_FakeCLOB({"new-yes": _book(token="new-yes", condition=ids["condition_id"])})).run_recovery(
        cycle_id="token-stale",
        candidate_limit=1,
        gamma_market_limit=0,
    )

    with DatabaseConnectionFactory().connect() as conn:
        market = conn.execute("SELECT yes_token_id FROM markets_v2 WHERE market_id=%s", (ids["market_id"],)).fetchone()
    assert market["yes_token_id"] == "new-yes"
    assert _latest_trace(ids["candidate_id"])["expected_token_id"] == "new-yes"


def test_system_off_blocks_recovery_and_dashboard_mock_false(postgres_test_schema) -> None:
    _prepare()
    _seed("off")
    SystemPowerService().turn_off(actor="test", reason="token-off")

    result = PolymarketTokenTruthService(http_client=_FakeCLOB({})).run_recovery(cycle_id="token-off", candidate_limit=1, gamma_market_limit=0)
    dashboard = TestClient(create_app()).get("/dashboard/api/v2/polymarket-token-truth?limit=5").json()

    assert result["status"] == "BLOCKED"
    assert dashboard["mock_data"] is False


def test_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("safety", side="YES")
    with DatabaseConnectionFactory().connect() as conn:
        before = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2")}

    PolymarketTokenTruthService(http_client=_FakeCLOB({ids["gamma_yes"]: _book(token=ids["gamma_yes"], condition=ids["condition_id"])})).run_recovery(
        cycle_id="token-safety",
        candidate_limit=1,
        gamma_market_limit=0,
    )

    with DatabaseConnectionFactory().connect() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2")}
    assert after == before

