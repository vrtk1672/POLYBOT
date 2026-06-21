from __future__ import annotations

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService
from app.services.fresh_seed_paper_path import FreshSeedPaperCandidateService
from app.services.system_power import SystemPowerService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "fresh_seed_paper_path_runs",
            "fresh_seed_candidate_conversions",
            "paper_intent_runs",
            "no_trade_runs",
            "no_trade_log",
            "paper_intents",
            "paper_eligibility_runs",
            "paper_eligibility_candidates",
            "exit_plan_rules",
            "exit_plan_runs",
            "exit_plans",
            "risk_decisions",
            "risk_gate_runs",
            "thesis_profile_evidence_items",
            "thesis_profile_runs",
            "thesis_profiles",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_outputs",
            "signal_market_links",
            "neuron_signals",
            "fresh_candidate_seeds",
            "trusted_orderbook_evidence_links",
            "orderbook_snapshots",
            "brain_dialogue_events",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_capital_ledger",
            "live_orders",
            "orders_v2",
            "fills_v2",
            "positions",
            "system_power_transitions",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
                conn.execute(f"DELETE FROM {table}")


def _seed_book_verified(
    suffix: str = "ok",
    *,
    status: str = "BOOK_VERIFIED",
    trusted: bool = True,
    spread: float = 0.02,
    liquidity: float = 0.8,
    rejection_reason: str | None = None,
) -> dict[str, object]:
    market_id = f"market-{suffix}"
    condition_id = f"condition-{suffix}"
    side = "YES"
    token = f"yes-token-{suffix}"
    seed_id = f"fresh_seed_{suffix}_YES"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        snapshot_id = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side,
                best_bid, best_ask, spread, mid_price, liquidity_score,
                source, snapshot_status, is_stale, collected_at, created_at
            )
            VALUES (%s, %s, %s, %s, 0.44, 0.46, %s, 0.45, %s, 'test', 'OK', false, now(), now())
            RETURNING id
            """,
            (f"book-{suffix}", market_id, token, side, spread, liquidity),
        ).fetchone()["id"]
        trusted_link_id = f"trusted_seed_{suffix}"
        if trusted:
            conn.execute(
                """
                INSERT INTO trusted_orderbook_evidence_links (
                    link_id, candidate_id, market_id, side, expected_token_id,
                    orderbook_snapshot_id, orderbook_snapshot_ref, orderbook_token_id,
                    trusted, trust_status, trust_reason, best_bid, best_ask,
                    mid_price, spread, liquidity_score, age_seconds,
                    evidence_json, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, true, 'TRUSTED',
                    'verified by test CLOB book', 0.44, 0.46, 0.45,
                    %s, %s, 0, '{}'::jsonb, now(), now()
                )
                """,
                (trusted_link_id, seed_id, market_id, side, token, snapshot_id, f"book-{suffix}", token, spread, liquidity),
            )
        conn.execute(
            """
            INSERT INTO fresh_candidate_seeds (
                seed_id, market_id, condition_id, slug, question, side,
                expected_token_id, yes_token_id, no_token_id, source, status,
                orderbook_snapshot_id, trusted_link_id, rejection_reason,
                metadata_json, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'test_gamma',
                %s, %s, %s, %s, %s, now(), now()
            )
            """,
            (
                seed_id,
                market_id,
                condition_id,
                f"slug-{suffix}",
                f"Question {suffix}?",
                side,
                token,
                token,
                f"no-token-{suffix}",
                status,
                snapshot_id if status == "BOOK_VERIFIED" else None,
                trusted_link_id if trusted and status == "BOOK_VERIFIED" else None,
                rejection_reason,
                Jsonb({"source": "test"}),
            ),
        )
    return {"seed_id": seed_id, "market_id": market_id, "snapshot_id": snapshot_id}


def _count(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def test_book_verified_seed_creates_candidate_thesis_risk_exit_eligibility_and_paper_intent(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("ok")
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")

    result = FreshSeedPaperCandidateService().run(limit=5)

    with DatabaseConnectionFactory().connect() as conn:
        conversion = conn.execute("SELECT * FROM fresh_seed_candidate_conversions LIMIT 1").fetchone()
    assert result["status"] == "OK"
    assert conversion["status"] == "PAPER_INTENT_CREATED"
    assert conversion["candidate_id"] is not None
    assert conversion["thesis_id"] is not None
    assert conversion["risk_decision_id"] is not None
    assert conversion["exit_plan_id"] is not None
    assert conversion["eligibility_id"] is not None
    assert conversion["paper_intent_id"] is not None
    assert _count("paper_intents") == 1
    assert _count("paper_orders") == 0
    assert _count("paper_fills") == 0
    assert _count("paper_positions") == 0


def test_seed_without_trusted_orderbook_is_blocked_and_no_generic_only_no_valid_reason(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("no-trust", trusted=False)
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")

    result = FreshSeedPaperCandidateService().run(limit=5)

    with DatabaseConnectionFactory().connect() as conn:
        conversion = conn.execute("SELECT status, blocker_reason FROM fresh_seed_candidate_conversions LIMIT 1").fetchone()
    assert result["paper_intents_created"] == 0
    assert conversion["status"] == "BLOCKED_NO_TRUSTED_ORDERBOOK"
    assert conversion["blocker_reason"] == "BLOCKED_NO_TRUSTED_ORDERBOOK"
    assert conversion["blocker_reason"] != "NO_VALID_PAPER_INTENTS"


def test_stale_market_seed_is_blocked_before_candidate_conversion(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("stale", status="BOOK_REJECTED", trusted=False, rejection_reason="STALE_MARKET")
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")

    FreshSeedPaperCandidateService().run(limit=5)

    with DatabaseConnectionFactory().connect() as conn:
        conversion = conn.execute("SELECT status, candidate_id, blocker_reason FROM fresh_seed_candidate_conversions LIMIT 1").fetchone()
    assert conversion["status"] == "BLOCKED_STALE_MARKET"
    assert conversion["candidate_id"] is None
    assert conversion["blocker_reason"] == "BLOCKED_STALE_MARKET"


def test_duplicate_seed_is_idempotent_and_does_not_duplicate_candidate_or_intent(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("dupe")
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")
    service = FreshSeedPaperCandidateService()

    service.run(limit=5)
    first_counts = {table: _count(table) for table in ("fresh_seed_candidate_conversions", "paper_eligibility_candidates", "paper_intents")}
    service.run(limit=5)
    second_counts = {table: _count(table) for table in ("fresh_seed_candidate_conversions", "paper_eligibility_candidates", "paper_intents")}

    assert second_counts == first_counts


def test_spread_or_liquidity_blocks_before_risk_and_no_paper_intent(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("wide", spread=0.20)
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")

    FreshSeedPaperCandidateService().run(limit=5)

    with DatabaseConnectionFactory().connect() as conn:
        conversion = conn.execute("SELECT status, blocker_reason FROM fresh_seed_candidate_conversions LIMIT 1").fetchone()
    assert conversion["status"] == "BLOCKED_RISK"
    assert conversion["blocker_reason"] == "SPREAD_TOO_WIDE"
    assert _count("paper_intents") == 0


def test_system_off_blocks_mutation_and_dashboard_is_truthful(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("off")
    SystemPowerService().turn_off(actor="test", reason="fresh-seed-paper-path-off")

    result = FreshSeedPaperCandidateService().run(limit=5)
    dashboard = TestClient(create_app()).get("/dashboard/api/v2/fresh-seed-paper-path?limit=5").json()

    assert result["status"] == "BLOCKED"
    assert result["error_message"] == "SYSTEM_POWER_OFF"
    assert _count("fresh_seed_candidate_conversions") == 0
    assert dashboard["mock_data"] is False
    assert dashboard["security_governance_status"] == "YELLOW_ACCEPTED_BY_OPERATOR"


def test_dialogue_materializes_conversion_and_no_live_or_real_mutation(postgres_test_schema) -> None:
    _prepare()
    _seed_book_verified("dialogue")
    SystemPowerService().turn_on(actor="test", reason="fresh-seed-paper-path")
    before = {table: _count(table) for table in ("live_orders", "orders_v2", "fills_v2", "positions", "paper_orders", "paper_fills", "paper_positions")}

    FreshSeedPaperCandidateService().run(limit=5)
    BrainDialogueService().materialize_recent(limit_per_source=5)

    after = {table: _count(table) for table in ("live_orders", "orders_v2", "fills_v2", "positions", "paper_orders", "paper_fills", "paper_positions")}
    with DatabaseConnectionFactory().connect() as conn:
        dialogue = conn.execute(
            "SELECT human_message FROM brain_dialogue_events WHERE component='Fresh Seed Paper Path' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert after == before
    assert "Fresh Seed Paper Path:" in dialogue["human_message"]
