from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.fresh_market_identity import FreshMarketIdentityGateService
from app.services.system_power import SystemPowerService


class _FakeGamma:
    def __init__(self, markets: dict[str, Any]) -> None:
        self.markets = markets
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, object] | None = None) -> tuple[Any, int]:
        market_id = str((params or {}).get("id"))
        self.calls.append({"url": url, "params": dict(params or {})})
        payload = self.markets.get(market_id, [])
        if isinstance(payload, Exception):
            raise payload
        return payload, 5


def _gamma_market(
    suffix: str,
    *,
    market_id: str | None = None,
    condition_id: str | None = None,
    yes_token: str | None = None,
    no_token: str | None = None,
    closed: bool = False,
    active: bool = True,
    accepting_orders: bool = True,
    raw_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market_id = market_id or f"market-{suffix}"
    raw = {
        "id": market_id,
        "conditionId": condition_id or f"condition-{suffix}",
        "question": f"Question {suffix}?",
        "slug": f"slug-{suffix}",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": [yes_token or f"yes-{suffix}", no_token or f"no-{suffix}"],
        "closed": closed,
        "archived": False,
        "active": active,
        "acceptingOrders": accepting_orders,
    }
    raw.update(raw_extra or {})
    return raw


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "fresh_market_identity_traces",
            "fresh_market_identity_runs",
            "paper_eligibility_candidates",
            "signal_market_links",
            "neuron_signal_bindings",
            "neuron_signals",
            "markets_v2",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")
    SystemPowerService().turn_on(actor="test", reason="fresh-identity-prepare")


def _seed_candidate(
    suffix: str,
    *,
    market_id: str | None = "__DEFAULT__",
    side: str | None = "YES",
    signal_ids: list[str] | None = None,
    blockers: list[str] | None = None,
    local_market: dict[str, Any] | None = None,
) -> str:
    candidate_id = f"eligibility-{suffix}"
    market_id = f"market-{suffix}" if market_id == "__DEFAULT__" else market_id
    signal_ids = signal_ids or []
    blockers = blockers or ["MISSING_FRESH_ORDERBOOK"]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        if local_market:
            conn.execute(
                """
                INSERT INTO markets_v2 (
                    market_id, condition_id, question, slug, yes_token_id, no_token_id,
                    accepting_orders, closed, archived, active, raw_market_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
                """,
                (
                    local_market["id"],
                    local_market.get("conditionId"),
                    local_market.get("question"),
                    local_market.get("slug"),
                    local_market.get("clobTokenIds", [None, None])[0],
                    local_market.get("clobTokenIds", [None, None])[1],
                    local_market.get("acceptingOrders", True),
                    local_market.get("closed", False),
                    local_market.get("active", True),
                    Jsonb(local_market),
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
                candidate_id,
                f"thesis-{suffix}",
                f"risk-{suffix}",
                f"exit-{suffix}",
                Jsonb(signal_ids),
                market_id,
                side,
                Jsonb(blockers),
                Jsonb(blockers),
            ),
        )
    return candidate_id


def _seed_link(signal_id: str, market_id: str, *, side: str | None = "YES", confidence: float = 0.95) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, market_id, correlation_id,
                raw_direction, strength, confidence, source_reliability, freshness_seconds,
                status, evidence_json, entity_count, evidence_count
            )
            VALUES (
                %s, 'Test Neuron', 'MARKET_REPRICING', 'test', %s, %s,
                'neutral', 1.0, %s, 1.0, 1, 'ACTIVE', '{}'::jsonb, 1, 1
            )
            ON CONFLICT (signal_id) DO NOTHING
            """,
            (signal_id, market_id, f"corr-{signal_id}", confidence),
        )
        conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_status, confidence, link_confidence,
                link_type, link_method, created_by, linked_by,
                is_review_required, matched_side, link_evidence_json
            )
            VALUES (%s, %s, 'confirmed', %s, %s, 'market_identity', 'deterministic_test', 'test', 'test', false, %s, %s)
            """,
            (signal_id, market_id, confidence, confidence, side, Jsonb({"matched_side": side})),
        )


def _latest_trace(candidate_id: str) -> dict[str, Any]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute("SELECT * FROM fresh_market_identity_traces WHERE candidate_id=%s ORDER BY id DESC LIMIT 1", (candidate_id,)).fetchone())


def _candidate(candidate_id: str) -> dict[str, Any]:
    with DatabaseConnectionFactory().connect() as conn:
        return dict(conn.execute("SELECT * FROM paper_eligibility_candidates WHERE eligibility_id=%s", (candidate_id,)).fetchone())


def test_complete_current_identity_becomes_fresh_verified(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("fresh")
    candidate_id = _seed_candidate("fresh", local_market=raw)

    result = FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-fresh": [raw]})).run_recovery(
        cycle_id="fresh",
        limit=1,
        dry_run=False,
    )

    assert result["fresh_verified_count"] == 1
    trace = _latest_trace(candidate_id)
    assert trace["identity_status"] == "FRESH_VERIFIED"
    assert trace["expected_token_id"] == "yes-fresh"
    assert _candidate(candidate_id)["identity_status"] == "FRESH_VERIFIED"


def test_missing_market_id_recovers_from_deterministic_signal_market_link(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("linked")
    signal_id = "signal-linked"
    candidate_id = _seed_candidate("linked", market_id=None, signal_ids=[signal_id], side=None, blockers=["MISSING_MARKET_ID", "MISSING_SIDE"])
    _seed_link(signal_id, "market-linked", side="NO")

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-linked": [raw]})).run_recovery(limit=1, dry_run=False)

    candidate = _candidate(candidate_id)
    trace = _latest_trace(candidate_id)
    assert candidate["market_id"] == "market-linked"
    assert candidate["side"] == "NO"
    assert candidate["expected_token_id"] == "no-linked"
    assert trace["identity_status"] == "FRESH_VERIFIED"


def test_ambiguous_market_match_does_not_backfill(postgres_test_schema) -> None:
    _prepare()
    candidate_id = _seed_candidate("ambiguous", market_id=None, signal_ids=["signal-amb"], side="YES", blockers=["MISSING_MARKET_ID"])
    _seed_link("signal-amb", "market-a")
    _seed_link("signal-amb", "market-b")

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({})).run_recovery(limit=1, dry_run=False)

    candidate = _candidate(candidate_id)
    trace = _latest_trace(candidate_id)
    assert candidate["market_id"] is None
    assert trace["identity_status"] == "AMBIGUOUS_MATCH"


def test_condition_id_remains_separate_from_market_id(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("condition", market_id="market-condition", condition_id="condition-real")
    candidate_id = _seed_candidate("condition", market_id="market-condition", side="YES", local_market=raw)

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-condition": [raw]})).run_recovery(limit=1, dry_run=False)

    trace = _latest_trace(candidate_id)
    assert trace["condition_id"] == "condition-real"
    assert trace["condition_id"] != trace["market_id"]


def test_side_missing_remains_blocked(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("noside")
    candidate_id = _seed_candidate("noside", side=None, local_market=raw, blockers=["MISSING_SIDE"])

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-noside": [raw]})).run_recovery(limit=1, dry_run=False)

    assert _latest_trace(candidate_id)["identity_status"] == "MISSING_SIDE"


def test_yes_and_no_side_expected_tokens(postgres_test_schema) -> None:
    _prepare()
    raw_yes = _gamma_market("yes")
    raw_no = _gamma_market("no")
    yes_id = _seed_candidate("yes", side="YES", local_market=raw_yes)
    no_id = _seed_candidate("no", side="NO", local_market=raw_no)

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-yes": [raw_yes], "market-no": [raw_no]})).run_recovery(limit=2, dry_run=False)

    assert _latest_trace(yes_id)["expected_token_id"] == "yes-yes"
    assert _latest_trace(no_id)["expected_token_id"] == "no-no"


def test_ambiguous_outcome_tokens_blocked(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("tokens", raw_extra={"outcomes": [], "clobTokenIds": ["a", "b", "c"]})
    candidate_id = _seed_candidate("tokens", local_market=raw)

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-tokens": [raw]})).run_recovery(limit=1, dry_run=False)

    assert _latest_trace(candidate_id)["identity_status"] == "MISSING_TOKEN_MAPPING"


def test_stale_local_market_becomes_stale_market(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("stale", market_id="824952")
    candidate_id = _seed_candidate("stale", market_id="824952", local_market=raw)

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"824952": []})).run_recovery(limit=1, dry_run=False)

    assert _latest_trace(candidate_id)["identity_status"] == "STALE_MARKET"
    assert _candidate(candidate_id)["identity_status"] == "STALE_MARKET"


def test_closed_and_accepting_orders_false_blocked(postgres_test_schema) -> None:
    _prepare()
    closed = _gamma_market("closed", closed=True, active=False)
    no_orders = _gamma_market("noorders", accepting_orders=False)
    closed_id = _seed_candidate("closed", local_market=closed)
    no_orders_id = _seed_candidate("noorders", local_market=no_orders)

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-closed": [closed], "market-noorders": [no_orders]})).run_recovery(limit=2, dry_run=False)

    assert _latest_trace(closed_id)["identity_status"] == "CLOSED_MARKET"
    assert _latest_trace(no_orders_id)["identity_status"] == "ACCEPTING_ORDERS_FALSE"


def test_system_off_blocks_mutating_recovery_and_dashboard_mock_false(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("off")
    candidate_id = _seed_candidate("off", local_market=raw)
    SystemPowerService().turn_off(actor="test", reason="fresh-identity-off")

    result = FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-off": [raw]})).run_recovery(limit=1, dry_run=False)
    dashboard = TestClient(create_app()).get("/dashboard/api/v2/fresh-market-identity?limit=5").json()

    assert result["status"] == "BLOCKED"
    assert _candidate(candidate_id)["identity_status"] is None
    assert dashboard["mock_data"] is False


def test_no_fake_ids_and_no_trading_mutation(postgres_test_schema) -> None:
    _prepare()
    raw = _gamma_market("safety")
    _seed_candidate("safety", local_market=raw)
    with DatabaseConnectionFactory().connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "positions")
        }

    FreshMarketIdentityGateService(gamma_client=_FakeGamma({"market-safety": [raw]})).run_recovery(
        cycle_id=f"safety-{uuid4().hex}",
        limit=1,
        dry_run=False,
    )

    with DatabaseConnectionFactory().connect() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "positions")
        }
    assert after == before
