from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.brain_dialogue import BrainDialogueService
from app.services.paper_intents import PaperIntentGateService
from app.services.paper_trade_forensics import PaperTradeForensicsService
from app.services.same_market_side_guard import SameMarketSideGuardService
from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate, seed_eligible_candidate
from test_paper_execution_service import _prepare as prepare_execution_schema
from test_paper_execution_service import _seed_intent, _service as execution_service


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "brain_dialogue_events",
            "same_market_side_guard_decisions",
            "paper_position_closes",
            "paper_capital_ledger",
            "paper_trade_ledger",
            "paper_fills",
            "paper_positions",
            "paper_runs",
            "paper_orders",
            "paper_intents",
            "no_trade_log",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_open_position(*, market_id: str = "guard-market", side: str = "YES", intent_id: str | None = None) -> str:
    position_id = uuid4()
    paper_run_id = uuid4()
    intent_id = intent_id or f"intent-{position_id.hex}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _insert_paper_run(conn, paper_run_id)
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size,
                avg_entry, mark_price, unrealized, realized, current_status,
                thesis_state, invalidation_state, opened_at, updated_at,
                closed_at, payload_json
            )
            VALUES (
                %s, %s, %s, %s, 10,
                0.50, 0.50, 0, 0, 'OPEN',
                'ACTIVE', 'NONE', now(), now(),
                NULL, %s
            )
            """,
            (position_id, paper_run_id, market_id, side, Jsonb({"source_intent_id": intent_id, "paper_only": True, "live": False})),
        )
    return str(position_id)


def _seed_closed_position(
    *,
    market_id: str = "guard-market",
    side: str = "NO",
    created_at: datetime | None = None,
    correlation_id: str | None = None,
) -> str:
    position_id = uuid4()
    paper_run_id = uuid4()
    created_at = created_at or datetime.now(UTC) - timedelta(days=2)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        _insert_paper_run(conn, paper_run_id)
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size,
                avg_entry, mark_price, unrealized, realized, current_status,
                thesis_state, invalidation_state, opened_at, updated_at,
                closed_at, payload_json
            )
            VALUES (
                %s, %s, %s, %s, 10,
                0.50, 0.55, 0, 0.5, 'CLOSED',
                'CLOSED', 'NONE', %s, %s,
                %s, %s
            )
            """,
            (
                position_id,
                paper_run_id,
                market_id,
                side,
                created_at - timedelta(minutes=1),
                created_at,
                created_at,
                Jsonb({"source_intent_id": f"intent-{position_id.hex}", "paper_only": True, "live": False}),
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_position_closes (
                close_id, position_id, market_id, side, entry_price, exit_price,
                quantity, realized_pnl, realized_pnl_pct, exit_reason,
                price_basis, source_exit_price, correlation_id, metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, 0.50, 0.55, 10, 0.5, 0.1, 'TAKE_PROFIT', 'TEST_MARK', 'test', %s, '{}'::jsonb, %s)
            """,
            (f"close-{position_id.hex}", position_id, market_id, side, correlation_id, created_at),
        )
    return str(position_id)


def _seed_active_intent(*, market_id: str = "guard-market", side: str = "NO", updated_at: datetime | None = None) -> str:
    intent_id = f"paper-intent-{uuid4().hex}"
    updated_at = updated_at or datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, coordinator_decision_id, market_id, side,
                price_basis, intended_price, max_slippage, confidence,
                intent_status, intent_type, intent_reason, evidence, blockers,
                paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at
            )
            VALUES (
                %s, %s, 'thesis-test', 'risk-test',
                'exit-test', NULL, %s, %s,
                'ORDERBOOK_LIMIT', 0.50, 0, 0.8,
                'CREATED', 'PAPER_ENTRY_INTENT', 'test active paper intent', '{}'::jsonb, '[]'::jsonb,
                true, false, false, false,
                'test', 'same_market_guard_test', true, false,
                %s, %s
            )
            """,
            (intent_id, f"eligibility-{intent_id}", market_id, side, updated_at, updated_at),
        )
    return intent_id


def _insert_paper_run(conn, paper_run_id) -> None:
    conn.execute(
        """
        INSERT INTO paper_runs (
            id, mode, started_at, ended_at, status, markets_seen_count,
            markets_ranked_count, candidates_selected_count, signals_emitted_count,
            metadata_json
        )
        VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1, '{}'::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (paper_run_id,),
    )


def _evaluate(**kwargs):
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        return SameMarketSideGuardService().evaluate(conn, **kwargs)


def test_new_yes_blocked_when_open_no_exists_without_rationale(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")

    decision = _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    assert decision.decision == "BLOCK"
    assert decision.blocker_reason == "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK"
    assert decision.existing_opposite_positions_count == 1


def test_new_no_blocked_when_open_yes_exists_without_rationale(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="YES")

    decision = _evaluate(market_id="guard-market", proposed_side="NO", proposed_candidate_id="candidate-no")

    assert decision.decision == "BLOCK"
    assert decision.blocker_reason == "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK"


def test_opposing_yes_no_batch_is_blocked_without_rationale(postgres_test_schema) -> None:
    _prepare()

    decision = _evaluate(
        market_id="guard-market",
        proposed_side="YES",
        proposed_candidate_id="candidate-yes",
        batch_sides={"guard-market": {"YES", "NO"}},
    )

    assert decision.decision == "BLOCK"
    assert decision.batch_opposite_candidates_count == 1


def test_opposing_side_allowed_only_with_source_backed_hedge_rationale(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")
    source_id = seed_blocked_candidate("hedge-source")

    decision = _evaluate(
        market_id="guard-market",
        proposed_side="YES",
        proposed_candidate_id="candidate-yes",
        metadata={
            "same_market_rationale_type": "HEDGE_RATIONALE",
            "rationale_source": "paper_eligibility_candidates",
            "rationale_source_id": source_id,
        },
    )

    assert decision.decision == "ALLOW"
    assert decision.rationale_type == "HEDGE_RATIONALE"
    assert decision.source_backed is True


def test_fake_or_non_source_backed_rationale_is_rejected(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")

    decision = _evaluate(
        market_id="guard-market",
        proposed_side="YES",
        proposed_candidate_id="candidate-yes",
        metadata={
            "same_market_rationale_type": "HEDGE_RATIONALE",
            "rationale_source": "paper_eligibility_candidates",
            "rationale_source_id": "missing-source",
        },
    )

    assert decision.decision == "BLOCK"
    assert decision.source_backed is False


def test_same_side_duplicate_goes_to_review_not_silent_allow(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="YES")

    decision = _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes-2")

    assert decision.decision == "REVIEW"
    assert decision.blocker_reason == "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW"


def test_old_closed_opposite_trade_does_not_hard_block(postgres_test_schema) -> None:
    _prepare()
    _seed_closed_position(side="NO", created_at=datetime.now(UTC) - timedelta(days=3))

    decision = _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    assert decision.decision == "ALLOW"


def test_stale_opposite_intent_is_historical_only_not_hard_block(postgres_test_schema) -> None:
    _prepare()
    _seed_active_intent(side="NO", updated_at=datetime.now(UTC) - timedelta(hours=3))

    decision = _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    assert decision.decision == "ALLOW"
    assert decision.existing_opposite_intents_count == 0
    assert len(decision.existing_exposure["stale_opposite_intents"]) == 1


def test_fresh_opposite_intent_still_blocks(postgres_test_schema) -> None:
    _prepare()
    _seed_active_intent(side="NO")

    decision = _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    assert decision.decision == "BLOCK"
    assert decision.blocker_reason == "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK"


def test_recent_closed_opposite_same_run_goes_to_review(postgres_test_schema) -> None:
    _prepare()
    _seed_closed_position(side="NO", created_at=datetime.now(UTC), correlation_id="same-run")

    decision = _evaluate(
        market_id="guard-market",
        proposed_side="YES",
        proposed_candidate_id="candidate-yes",
        metadata={"correlation_id": "same-run"},
    )

    assert decision.decision == "REVIEW"
    assert decision.blocker_reason == "SAME_MARKET_RECENT_OPPOSING_SIDE_REVIEW"


def test_guard_runs_before_paper_intent_creation(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("same-market-intent")
    with DatabaseConnectionFactory().connect() as conn:
        candidate = conn.execute("SELECT * FROM paper_eligibility_candidates ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    _seed_open_position(market_id=candidate["market_id"], side="NO" if candidate["side"] == "YES" else "YES")

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        no_trade = conn.execute("SELECT * FROM no_trade_log WHERE eligibility_id = %s", (candidate["eligibility_id"],)).fetchone()
        assert "SAME_MARKET_OPPOSING_SIDE_BLOCK" in no_trade["blockers"]


def test_guard_runs_before_paper_execution_and_blocks_existing_bad_intent(postgres_test_schema) -> None:
    prepare_execution_schema()
    intent_id = _seed_intent(market_id="guard-exec-market", side="YES")
    _seed_open_position(market_id="guard-exec-market", side="NO")

    result = execution_service().run_execution(correlation_id="guard-exec")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["SAME_MARKET_OPPOSING_SIDE_BLOCK"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert int(conn.execute("SELECT COUNT(*) AS count FROM paper_fills WHERE source_intent_id = %s", (intent_id,)).fetchone()["count"]) == 0


def test_dashboard_returns_mock_data_false_and_counts(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")
    _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    payload = SameMarketSideGuardService().get_dashboard_summary()

    assert payload["mock_data"] is False
    assert payload["blocked_count"] == 1
    assert payload["security_governance_status"] == "YELLOW_ACCEPTED_BY_OPERATOR"


def test_trade_forensics_shows_guard_decision(postgres_test_schema) -> None:
    _prepare()
    intent_id = "forensics-intent"
    position_id = _seed_open_position(side="YES", intent_id=intent_id)
    _evaluate(market_id="guard-market", proposed_side="YES", proposed_intent_id=intent_id)

    trace = PaperTradeForensicsService().get_trade(position_id)

    assert trace["same_market_guard_status"] == "REVIEW"
    assert trace["same_market_guard_decision"]["blocker_reason"] == "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW"


def test_dialogue_materializes_guard_decision(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")
    _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    result = BrainDialogueService(system_power=_Power(True)).materialize_recent(limit_per_source=10)

    assert result["events_created"] >= 1
    with DatabaseConnectionFactory().connect() as conn:
        event = conn.execute("SELECT * FROM brain_dialogue_events WHERE component = 'Same-Market Guard'").fetchone()
    assert event is not None
    assert "Blocked YES on market guard-market" in event["human_message"]


def test_guard_does_not_create_orders_fills_positions_or_live_artifacts(postgres_test_schema) -> None:
    _prepare()
    _seed_open_position(side="NO")
    before = _counts()
    _evaluate(market_id="guard-market", proposed_side="YES", proposed_candidate_id="candidate-yes")

    after = _counts()

    assert after["paper_orders"] == before["paper_orders"]
    assert after["paper_fills"] == before["paper_fills"]
    assert after["paper_positions"] == before["paper_positions"]
    assert after["live_orders"] == before["live_orders"]
    assert after["orders_v2"] == before["orders_v2"]
    assert after["fills_v2"] == before["fills_v2"]


class _Power:
    def __init__(self, on: bool = True) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


def _counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {table: _count(conn, table) for table in ("paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2")}


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
