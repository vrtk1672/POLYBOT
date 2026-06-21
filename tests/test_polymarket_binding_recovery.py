from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.brain_dialogue import BrainDialogueService
from app.main import create_app
from app.services.polymarket_binding import PolymarketIdentityBindingService
from app.services.system_power import SystemPowerService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "polymarket_binding_candidate_traces",
            "polymarket_binding_recovery_runs",
            "trusted_orderbook_evidence_links",
            "trusted_orderbook_evidence_runs",
            "paper_eligibility_candidates",
            "signal_market_links",
            "neuron_signal_bindings",
            "neuron_signals",
            "orderbook_snapshots",
            "market_snapshots",
            "markets_v2",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="polymarket_binding_prepare")


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
            raise RuntimeError("No orderbook exists for the requested token id")
        return payload, 7


def _book(*, token: str, condition: str = "condition-1", bid: str = "0.44", ask: str = "0.46") -> dict[str, object]:
    return {
        "market": condition,
        "asset_id": token,
        "bids": [{"price": bid, "size": "1500"}],
        "asks": [{"price": ask, "size": "1600"}],
    }


def _seed(
    suffix: str,
    *,
    market_id: str | None = None,
    side: str | None = "YES",
    insert_market: bool = True,
    condition_id: str | None = "condition-1",
    yes_token: str | None = None,
    no_token: str | None = None,
    closed: bool = False,
    accepting_orders: bool | None = True,
    candidate_market_id: str | None | object = ...,
    candidate_side: str | None | object = ...,
    link_market_ids: list[str] | None = None,
    link_side: str | None = None,
    with_snapshot_identity: bool = False,
) -> dict[str, str]:
    market_id = market_id or f"market-{suffix}"
    yes_token = yes_token or f"yes-{suffix}"
    no_token = no_token or f"no-{suffix}"
    signal_id = f"signal-{suffix}"
    eligibility_id = f"eligibility-{suffix}"
    candidate_market = market_id if candidate_market_id is ... else candidate_market_id
    candidate_side_value = side if candidate_side is ... else candidate_side
    link_side = link_side if link_side is not None else side
    link_market_ids = link_market_ids if link_market_ids is not None else [market_id]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if insert_market:
            conn.execute(
                """
                INSERT INTO markets_v2 (
                    market_id, condition_id, question, slug, yes_token_id, no_token_id,
                    accepting_orders, closed, archived, active, raw_market_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
                """,
                (
                    market_id,
                    condition_id,
                    f"Question {suffix}?",
                    f"slug-{suffix}",
                    yes_token,
                    no_token,
                    accepting_orders,
                    closed,
                    not closed,
                    Jsonb({"enableOrderBook": True, "conditionId": condition_id, "clobTokenIds": [yes_token, no_token], "outcomes": ["Yes", "No"]}),
                ),
            )
        conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, market_id,
                confidence, strength, evidence_json, status, raw_payload_ref,
                correlation_id, created_at, updated_at
            )
            VALUES (%s, 'market', 'binding_test', 'test', %s, 0.95, 0.8, %s, 'ACTIVE', %s, %s, now(), now())
            """,
            (signal_id, market_id, Jsonb({"sample_token_id": yes_token if side == "YES" else no_token}), f"raw-{suffix}", f"corr-{suffix}"),
        )
        for idx, link_market_id in enumerate(link_market_ids):
            conn.execute(
                """
                INSERT INTO signal_market_links (
                    signal_id, market_id, link_type, link_status, confidence, reason,
                    created_by, link_confidence, link_reason, link_evidence_json,
                    link_method, linked_by, is_auto_linked, is_review_required,
                    is_runtime_link, source_signal_id, matched_side
                )
                VALUES (
                    %s, %s, 'test', 'confirmed', 0.95, 'test', 'test', 0.95, 'test',
                    %s, 'explicit_market_id', 'test', true, false, true, %s, %s
                )
                """,
                (signal_id, link_market_id, Jsonb({"matched_side": link_side}), signal_id, link_side),
            )
        if with_snapshot_identity:
            conn.execute(
                """
                INSERT INTO market_snapshots_v2 (
                    snapshot_id, market_id, cycle_id, correlation_id, accepting_orders,
                    closed, data_completeness_score, stale, snapshot_at, raw_snapshot_json
                )
                VALUES (
                    %s, %s, %s, %s, true, false, 1.0, false, now(), %s
                )
                """,
                (
                    f"snapshot-{suffix}",
                    market_id,
                    str(uuid4()),
                    f"corr-{suffix}",
                    Jsonb({
                        "id": market_id,
                        "conditionId": condition_id,
                        "question": f"Question {suffix}?",
                        "slug": f"slug-{suffix}",
                        "clobTokenIds": [yes_token, no_token],
                        "outcomes": ["Yes", "No"],
                        "active": True,
                        "closed": False,
                        "archived": False,
                        "acceptingOrders": True,
                        "enableOrderBook": True,
                    }),
                ),
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
                %s, %s, %s, %s, %s, %s, %s, 'BLOCKED', 0,
                %s, %s, '{}'::jsonb, 0.95, true, false, false, true, true, false
            )
            """,
            (
                eligibility_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                Jsonb([signal_id]),
                candidate_market,
                candidate_side_value,
                Jsonb(["MISSING_MARKET_ID", "MISSING_SIDE", "MISSING_FRESH_ORDERBOOK"]),
                Jsonb(["MISSING_MARKET_ID", "MISSING_SIDE", "MISSING_FRESH_ORDERBOOK"]),
            ),
        )
    return {
        "market_id": market_id,
        "condition_id": str(condition_id),
        "yes_token": str(yes_token),
        "no_token": str(no_token),
        "signal_id": signal_id,
        "eligibility_id": eligibility_id,
    }


def _candidate(candidate_id: str) -> dict[str, object]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute("SELECT * FROM paper_eligibility_candidates WHERE eligibility_id=%s", (candidate_id,)).fetchone())


def _latest_trace(candidate_id: str) -> dict[str, object]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute("SELECT * FROM polymarket_binding_candidate_traces WHERE candidate_id=%s ORDER BY id DESC LIMIT 1", (candidate_id,)).fetchone())


def test_yes_candidate_maps_to_expected_yes_token_and_creates_trusted_link(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("yes", side="YES")
    result = PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})).run_recovery(cycle_id="bind-yes", limit=10)

    assert result["trusted_links_created"] == 1
    trace = _latest_trace(ids["eligibility_id"])
    assert trace["expected_token_id"] == ids["yes_token"]
    assert trace["clob_book_status"] == "OK"


def test_no_candidate_maps_to_expected_no_token(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("no", side="NO")
    fake = _FakeCLOB({ids["no_token"]: _book(token=ids["no_token"])})

    PolymarketIdentityBindingService(http_client=fake).run_recovery(cycle_id="bind-no", limit=10)

    assert fake.calls[0]["params"]["token_id"] == ids["no_token"]
    assert _latest_trace(ids["eligibility_id"])["expected_token_id"] == ids["no_token"]


def test_missing_side_blocks_book_request(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("missing-side", side="YES", candidate_side=None, link_side=None)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE signal_market_links
            SET matched_side = NULL, link_evidence_json = '{}'::jsonb
            WHERE signal_id = %s
            """,
            (ids["signal_id"],),
        )
    fake = _FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})

    PolymarketIdentityBindingService(http_client=fake).run_recovery(cycle_id="bind-missing-side", limit=10)

    assert fake.calls == []
    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "NO_SIDE"


def test_missing_token_mapping_blocks_book_request(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("missing-token", side="YES", yes_token=None, no_token=None)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("UPDATE markets_v2 SET yes_token_id=NULL, no_token_id=NULL WHERE market_id=%s", (ids["market_id"],))
    fake = _FakeCLOB({})

    PolymarketIdentityBindingService(http_client=fake).run_recovery(cycle_id="bind-missing-token", limit=10)

    assert fake.calls == []
    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "NO_YES_NO_TOKEN_MAPPING"


def test_asset_id_mismatch_is_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("asset-mismatch", side="YES")

    PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token="wrong-token")})).run_recovery(cycle_id="bind-asset-mismatch", limit=10)

    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "TOKEN_MISMATCH"


def test_condition_id_mismatch_is_rejected(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("condition-mismatch", side="YES")

    PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"], condition="other-condition")})).run_recovery(cycle_id="bind-condition-mismatch", limit=10)

    trace = _latest_trace(ids["eligibility_id"])
    assert trace["exact_fix_category"] == "CONDITION_ID_MISMATCH"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots").fetchone()["count"] == 0


def test_clob_no_book_records_precise_blocker(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("no-book", side="YES")

    PolymarketIdentityBindingService(http_client=_FakeCLOB({})).run_recovery(cycle_id="bind-no-book", limit=10)

    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "CLOB_NO_BOOK"


def test_market_closed_blocks_trust(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("closed", side="YES", closed=True, accepting_orders=False)
    fake = _FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})

    PolymarketIdentityBindingService(http_client=fake).run_recovery(cycle_id="bind-closed", limit=10)

    assert fake.calls == []
    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "MARKET_CLOSED"


def test_deterministic_backfill_from_gamma_snapshot_works(postgres_test_schema) -> None:
    _prepare()
    ids = _seed(
        "gamma-backfill",
        side="YES",
        insert_market=False,
        candidate_market_id=None,
        candidate_side=None,
        link_side="YES",
        with_snapshot_identity=True,
    )

    PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})).run_recovery(cycle_id="bind-gamma", limit=10)

    candidate = _candidate(ids["eligibility_id"])
    assert candidate["market_id"] == ids["market_id"]
    assert candidate["side"] == "YES"
    trace = _latest_trace(ids["eligibility_id"])
    assert trace["condition_id"] == ids["condition_id"]
    assert trace["expected_token_id"] == ids["yes_token"]


def test_ambiguous_backfill_does_not_write_fake_market_id(postgres_test_schema) -> None:
    _prepare()
    ids = _seed(
        "ambiguous",
        side="YES",
        candidate_market_id=None,
        link_market_ids=["market-a", "market-b"],
        link_side="YES",
    )

    PolymarketIdentityBindingService(http_client=_FakeCLOB({})).run_recovery(cycle_id="bind-ambiguous", limit=10)

    assert _candidate(ids["eligibility_id"])["market_id"] is None
    assert _latest_trace(ids["eligibility_id"])["exact_fix_category"] == "NO_MARKET_ID"


def test_system_off_blocks_recovery(postgres_test_schema) -> None:
    _prepare()
    _seed("off")
    SystemPowerService().turn_off(actor="test", reason="bind-off")

    result = PolymarketIdentityBindingService(http_client=_FakeCLOB({})).run_recovery(cycle_id="bind-off", limit=10)

    assert result["status"] == "BLOCKED"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM polymarket_binding_candidate_traces").fetchone()["count"] == 0


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    _seed("dashboard")

    summary = PolymarketIdentityBindingService(http_client=_FakeCLOB({})).get_dashboard_summary(limit=5)

    assert summary["mock_data"] is False
    assert "candidates_with_expected_token" in summary


def test_dashboard_route_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    _seed("dashboard-route")
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/polymarket-binding?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert "blocker_counts" in payload


def test_binding_trace_materializes_source_backed_dialogue(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("dialogue", side="YES")
    PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})).run_recovery(cycle_id="bind-dialogue", limit=10)

    BrainDialogueService().materialize_recent(limit_per_source=20)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM brain_dialogue_events
            WHERE component = 'Polymarket Binding'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    assert row["source_table"] == "polymarket_binding_candidate_traces"
    assert "Polymarket Binding:" in row["human_message"]


def test_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    ids = _seed("safety", side="YES")
    with DatabaseConnectionFactory().connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2")
        }

    PolymarketIdentityBindingService(http_client=_FakeCLOB({ids["yes_token"]: _book(token=ids["yes_token"])})).run_recovery(cycle_id="bind-safety", limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2")
        }
    assert after == before
