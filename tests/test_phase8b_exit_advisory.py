from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.exit_advisory import ADVISORY_VERSION, ExitAdvisoryRunResult, ExitAdvisoryService, main as exit_advisory_main
from app.services.invalidation_exit_policy import POLICY_VERSION
from app.services.query.exit_advisory_query_service import ExitAdvisoryQueryService


def _seed_invalidation_policy_record(
    *,
    market_id: str,
    invalidation_state_class: str,
    exit_policy_class: str,
    deployment_gate_effect: str,
    invalidation_severity_score: float = 0.5,
    exit_urgency_score: float = 0.5,
) -> dict[str, str]:
    factory = DatabaseConnectionFactory()
    run_id = str(uuid4())
    record_id = str(uuid4())
    started_at = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO invalidation_policy_runs (
                id, source_type, source_ref, status, policy_version,
                started_at, ended_at, input_count, success_count, failure_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                "phase8b_seed",
                market_id,
                "COMPLETED",
                POLICY_VERSION,
                started_at,
                started_at,
                1,
                1,
                0,
                Jsonb({"seed": "phase8b"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO invalidation_policy_records (
                id, invalidation_policy_run_id, market_id, cycle_id,
                ranking_policy_candidate_id, cognition_summary_id, invalidation_reasoning_id,
                trade_classification_id, bucket_allocation_id, invalidation_state_class,
                exit_policy_class, invalidation_severity_score, exit_urgency_score,
                deployment_gate_effect, policy_reason_codes_json, policy_reason_text,
                explanation_json, policy_version
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                record_id,
                run_id,
                market_id,
                None,
                None,
                None,
                None,
                None,
                None,
                invalidation_state_class,
                exit_policy_class,
                invalidation_severity_score,
                exit_urgency_score,
                deployment_gate_effect,
                Jsonb(["seeded_policy_record"]),
                "seeded policy record for phase8b test",
                Jsonb({"seed": "phase8b"}),
                POLICY_VERSION,
            ),
        )
    return {"run_id": run_id, "record_id": record_id}


def _seed_paper_position(*, market_id: str, current_status: str = "OPEN") -> str:
    factory = DatabaseConnectionFactory()
    paper_run_id = str(uuid4())
    position_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, cycle_id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (paper_run_id, None, "EXECUTION_AWARE_PAPER", now, now, "COMPLETED", 1, 1, 0, 0, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry, mark_price,
                unrealized, realized, current_status, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                position_id,
                paper_run_id,
                market_id,
                "NO",
                10.0,
                0.62,
                0.58,
                -0.4,
                0.0,
                current_status,
                "ACTIVE",
                "NONE",
                now,
                now,
                None,
                Jsonb({"seed": "paper_position"}),
            ),
        )
    return position_id


def _seed_paper_order(*, market_id: str, status: str = "OPEN") -> str:
    factory = DatabaseConnectionFactory()
    paper_run_id = str(uuid4())
    signal_id = str(uuid4())
    order_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, cycle_id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (paper_run_id, None, "EXECUTION_AWARE_PAPER", now, now, "COMPLETED", 1, 1, 1, 1, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, cycle_id, market_id, decision_id, signal_type, intended_outcome,
                trade_type, bucket_type, confidence, expected_edge_proxy, intended_price,
                intended_size, guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                signal_id,
                paper_run_id,
                None,
                market_id,
                None,
                "WOULD_ENTER",
                "NO",
                "FAST_TRADE",
                "FAST_BUCKET",
                0.7,
                0.05,
                0.71,
                5.0,
                "ALLOW",
                "seed",
                "seed",
                Jsonb({}),
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, cycle_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status, fill_ratio,
                filled_size, remaining_size, avg_fill_price, min_size_check_passed, stale_at, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                paper_run_id,
                signal_id,
                None,
                market_id,
                "NO",
                "BUY_NO",
                0.71,
                5.0,
                3.55,
                status,
                0.0,
                0.0,
                5.0,
                None,
                True,
                None,
                Jsonb({"seed": "paper_order"}),
            ),
        )
    return order_id


def _seed_shadow_position(*, market_id: str, current_status: str = "PENDING_SUBMISSION") -> str:
    factory = DatabaseConnectionFactory()
    shadow_run_id = str(uuid4())
    order_id = str(uuid4())
    position_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO shadow_runs (
                id, cycle_id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, shadow_orders_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (shadow_run_id, None, "SHADOW_LIVE", now, now, "COMPLETED", 1, 1, 1, 1, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO shadow_orders (
                id, shadow_run_id, cycle_id, decision_id, market_id, token_id, intended_outcome,
                action, intended_price, intended_size, notional, guard_result, execution_policy_result,
                status, raw_intent_json, raw_guard_json, raw_policy_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                shadow_run_id,
                None,
                None,
                market_id,
                f"{market_id}2",
                "NO",
                "BUY_NO",
                0.70,
                5.0,
                3.5,
                "ALLOW",
                "ALLOW",
                "WOULD_SUBMIT",
                Jsonb({}),
                Jsonb({}),
                Jsonb({}),
            ),
        )
        conn.execute(
            """
            INSERT INTO shadow_positions (
                id, shadow_run_id, shadow_order_id, market_id, intended_outcome, size, avg_entry,
                current_status, mark_price, unrealized, realized, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                position_id,
                shadow_run_id,
                order_id,
                market_id,
                "NO",
                5.0,
                0.70,
                current_status,
                0.70,
                0.0,
                0.0,
                "ACTIVE",
                "NONE",
                now,
                now,
                None,
                Jsonb({"seed": "shadow_position"}),
            ),
        )
    return position_id


def _seed_shadow_order(*, market_id: str, status: str = "WOULD_SUBMIT") -> str:
    factory = DatabaseConnectionFactory()
    shadow_run_id = str(uuid4())
    order_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO shadow_runs (
                id, cycle_id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, shadow_orders_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (shadow_run_id, None, "SHADOW_LIVE", now, now, "COMPLETED", 1, 1, 1, 1, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO shadow_orders (
                id, shadow_run_id, cycle_id, decision_id, market_id, token_id, intended_outcome,
                action, intended_price, intended_size, notional, guard_result, execution_policy_result,
                status, raw_intent_json, raw_guard_json, raw_policy_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                shadow_run_id,
                None,
                None,
                market_id,
                f"{market_id}2",
                "NO",
                "BUY_NO",
                0.70,
                5.0,
                3.5,
                "ALLOW",
                "ALLOW",
                status,
                Jsonb({}),
                Jsonb({}),
                Jsonb({}),
            ),
        )
    return order_id


def _seed_live_position(*, market_id: str, current_status: str = "OPEN") -> str:
    factory = DatabaseConnectionFactory()
    position_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO positions (
                id, market_id, side, size, avg_entry, current_status, unrealized, realized,
                thesis_state, invalidation_state, opened_at, updated_at, closed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                position_id,
                market_id,
                "NO",
                5.0,
                0.69,
                current_status,
                0.0,
                0.0,
                "ACTIVE",
                "NONE",
                now,
                now,
                None,
            ),
        )
    return position_id


def _seed_live_order(*, market_id: str, status: str = "LIVE") -> str:
    factory = DatabaseConnectionFactory()
    order_id = str(uuid4())
    now = datetime.now(UTC)
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO live_orders (
                id, client_order_id, cycle_id, decision_id, market_id, token_id, side, action,
                price, size, notional, status, exchange_status, exchange_order_id, raw_request,
                raw_response, error_text, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                str(uuid4()),
                None,
                None,
                market_id,
                f"{market_id}2",
                "BUY",
                "BUY_NO",
                0.71,
                5.0,
                3.55,
                status,
                status,
                None,
                Jsonb({}),
                Jsonb({}),
                None,
                now,
                now,
            ),
        )
    return order_id


def test_exit_advisory_migrations_create_tables(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    table_names = {row["table_name"] for row in tables}
    assert {"exit_advisory_runs", "exit_advisory_records"} <= table_names


def test_successful_exit_advisory_run_persists_correctly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-run-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    position_id = _seed_paper_position(market_id=market_id)

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test", source_ref="phase8b")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM exit_advisory_runs WHERE id = %s LIMIT 1", (result.exit_advisory_run_id,)).fetchone()
        record_row = conn.execute("SELECT * FROM exit_advisory_records WHERE exit_advisory_run_id = %s LIMIT 1", (result.exit_advisory_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["advisory_version"] == ADVISORY_VERSION
    assert record_row is not None
    assert record_row["market_id"] == market_id
    assert str(record_row["invalidation_policy_record_id"]) == seeded["record_id"]
    assert record_row["exposure_type"] == "PAPER_POSITION"
    assert str(record_row["exposure_ref_id"]) == position_id


@pytest.mark.parametrize(
    ("exit_policy_class", "deployment_gate_effect", "exposure_kind", "expected_action"),
    [
        ("HOLD", "NONE", "paper_position", "KEEP"),
        ("MONITOR_CLOSELY", "NONE", "live_position", "WATCH"),
        ("REDUCE_EXPOSURE", "SOFT_BLOCK", "paper_position", "REDUCE"),
        ("PREPARE_EXIT", "SOFT_BLOCK", "shadow_position", "PREPARE_EXIT"),
        ("EXIT_RECOMMENDED", "HARD_BLOCK", "live_position", "EXIT"),
        ("PREPARE_EXIT", "SOFT_BLOCK", "paper_order", "CANCEL_PENDING"),
        ("BLOCK_NEW_DEPLOYMENT", "HARD_BLOCK", "shadow_order", "BLOCK_NEW_ENTRY"),
    ],
)
def test_exit_advisory_mapping_behaves_as_expected(
    postgres_test_schema,
    exit_policy_class: str,
    deployment_gate_effect: str,
    exposure_kind: str,
    expected_action: str,
) -> None:
    run_migrations()
    market_id = f"adv-map-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="WATCH",
        exit_policy_class=exit_policy_class,
        deployment_gate_effect=deployment_gate_effect,
    )

    if exposure_kind == "paper_position":
        exposure_type = "PAPER_POSITION"
        exposure_id = _seed_paper_position(market_id=market_id)
    elif exposure_kind == "live_position":
        exposure_type = "LIVE_POSITION"
        exposure_id = _seed_live_position(market_id=market_id)
    elif exposure_kind == "shadow_position":
        exposure_type = "SHADOW_POSITION"
        exposure_id = _seed_shadow_position(market_id=market_id)
    elif exposure_kind == "paper_order":
        exposure_type = "PAPER_ORDER"
        exposure_id = _seed_paper_order(market_id=market_id, status="OPEN")
    else:
        exposure_type = "SHADOW_ORDER"
        exposure_id = _seed_shadow_order(market_id=market_id, status="WOULD_SUBMIT")

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None
    record = ExitAdvisoryQueryService().get_exit_advisory_record_details(
        exposure_type=exposure_type,
        exposure_ref_id=exposure_id,
    )
    assert record is not None
    assert record["advisory_action_class"] == expected_action


def test_priority_assignment_behaves_deterministically(postgres_test_schema) -> None:
    run_migrations()
    critical_market = f"adv-pri-crit-{uuid4().hex[:6]}"
    low_market = f"adv-pri-low-{uuid4().hex[:6]}"
    _seed_invalidation_policy_record(
        market_id=critical_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_invalidation_policy_record(
        market_id=low_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    critical_position_id = _seed_live_position(market_id=critical_market)
    low_position_id = _seed_paper_position(market_id=low_market)

    service = ExitAdvisoryService()
    assert service.generate_for_markets([critical_market, low_market], source_type="phase8b_test") is not None

    query = ExitAdvisoryQueryService()
    critical_record = query.get_exit_advisory_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=critical_position_id)
    low_record = query.get_exit_advisory_record_details(exposure_type="PAPER_POSITION", exposure_ref_id=low_position_id)

    assert critical_record is not None
    assert critical_record["advisory_priority_class"] == "CRITICAL"
    assert low_record is not None
    assert low_record["advisory_priority_class"] == "LOW"


def test_pending_order_handling_is_honest(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-pending-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATION_CANDIDATE",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    order_id = _seed_live_order(market_id=market_id, status="LIVE")

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None
    record = ExitAdvisoryQueryService().get_exit_advisory_record_details(exposure_type="LIVE_ORDER", exposure_ref_id=order_id)

    assert record is not None
    assert record["advisory_action_class"] == "CANCEL_PENDING"
    assert "pending_order_cancel_recommended" in record["advisory_reason_codes_json"]


def test_open_position_handling_is_honest(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-open-pos-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATION_CANDIDATE",
        exit_policy_class="PREPARE_EXIT",
        deployment_gate_effect="SOFT_BLOCK",
    )
    position_id = _seed_shadow_position(market_id=market_id, current_status="PENDING_SUBMISSION")

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None
    record = ExitAdvisoryQueryService().get_exit_advisory_record_details(exposure_type="SHADOW_POSITION", exposure_ref_id=position_id)

    assert record is not None
    assert record["advisory_action_class"] == "PREPARE_EXIT"
    assert "open_position_prepare_exit" in record["advisory_reason_codes_json"]


def test_sparse_or_unsupported_exposure_contexts_are_handled_honestly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-unsupported-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    _seed_shadow_order(market_id=market_id, status="BLOCKED")

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM exit_advisory_records WHERE market_id = %s", (market_id,)).fetchone()["count"]
    assert count == 0


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-query-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_paper_position(market_id=market_id)
    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None

    query = ExitAdvisoryQueryService()
    summary = query.get_exit_advisory_run_summary(result.exit_advisory_run_id)
    rows = query.list_exit_advisory_records_for_run(result.exit_advisory_run_id)
    details = query.get_exit_advisory_record_details(market_id=market_id)
    critical = query.list_critical_exit_advisories()
    comparison = query.compare_exit_advisory_to_policy_context(market_id)

    assert summary is not None
    assert summary["record_count"] == 1
    assert len(rows) == 1
    assert details is not None
    assert str(details["invalidation_policy_record_id"]) == seeded["record_id"]
    assert len(critical) == 1
    assert comparison is not None
    assert comparison["invalidation_policy_record"] is not None
    assert len(comparison["exit_advisory_records"]) == 1
    assert len(comparison["paper_positions"]) == 1


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    class DummyService:
        enabled = True

        def generate_for_markets(self, market_ids: list[str], *, source_type: str, source_ref: str | None):
            captured["market_ids"] = market_ids
            captured["source_type"] = source_type
            captured["source_ref"] = source_ref
            return ExitAdvisoryRunResult(
                exit_advisory_run_id="phase8b-run",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

    monkeypatch.setattr("app.services.exit_advisory.ExitAdvisoryService", DummyService)
    exit_code = exit_advisory_main(["--market-ids", "mkt-a", "mkt-b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["market_ids"] == ["mkt-a", "mkt-b"]
    assert "exit_advisory_run_id=phase8b-run" in output


def test_no_live_paper_or_shadow_execution_path_is_mutated(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"adv-isolated-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_paper_position(market_id=market_id)
    _seed_paper_order(market_id=market_id, status="OPEN")
    _seed_shadow_position(market_id=market_id)
    _seed_shadow_order(market_id=market_id, status="WOULD_SUBMIT")
    _seed_live_position(market_id=market_id)
    _seed_live_order(market_id=market_id, status="LIVE")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_positions": conn.execute("SELECT COUNT(*) AS count FROM shadow_positions").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    result = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8b_test")
    assert result is not None

    with factory.connect() as conn:
        after = {
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_positions": conn.execute("SELECT COUNT(*) AS count FROM shadow_positions").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "positions": conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert before == after
