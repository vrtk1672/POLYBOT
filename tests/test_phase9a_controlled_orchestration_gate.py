from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.advisory_resolution import AdvisoryResolutionService
from app.services.command_intent_staging import COMMAND_INTENT_VERSION, CommandIntentStagingService
from app.services.controlled_orchestration_gate import (
    MAX_ACTIONS_PER_RUN,
    ORCHESTRATION_VERSION,
    ControlledOrchestrationGateService,
    OrchestrationGateRunResult,
    main as orchestration_gate_main,
)
from app.services.exit_advisory import ExitAdvisoryService
from app.services.query.controlled_orchestration_query_service import ControlledOrchestrationQueryService
from test_phase8b_exit_advisory import (
    _seed_invalidation_policy_record,
    _seed_live_position,
    _seed_paper_position,
    _seed_shadow_order,
)
from test_phase8d_command_intent_staging import _seed_custom_exit_advisories


def _run_upstream_command_intents_for_market(market_id: str):
    advisory_run = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase9a_test")
    assert advisory_run is not None
    resolution_run = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase9a_test")
    assert resolution_run is not None
    command_run = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase9a_test")
    assert command_run is not None
    return command_run


def _latest_resolution_record(market_id: str) -> dict[str, object]:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT * FROM advisory_resolution_records WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _latest_exit_advisory_record(market_id: str) -> dict[str, object]:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT * FROM exit_advisory_records WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _seed_custom_command_intent_run(
    *,
    market_id: str,
    resolution_record_id: str,
    intents: list[dict[str, object]],
) -> str:
    factory = DatabaseConnectionFactory()
    run_id = str(uuid4())
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO command_intent_runs (
                id, source_type, source_ref, status, command_intent_version,
                started_at, ended_at, input_count, success_count, failure_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, now(), now(), %s, %s, %s, %s)
            """,
            (
                run_id,
                "phase9a_seed",
                market_id,
                "COMPLETED",
                COMMAND_INTENT_VERSION,
                len(intents),
                len(intents),
                0,
                Jsonb({"seed": "phase9a"}),
            ),
        )
        for intent in intents:
            conn.execute(
                """
                INSERT INTO command_intent_records (
                    id, command_intent_run_id, market_id, advisory_resolution_record_id,
                    exit_advisory_record_id, exposure_type, exposure_ref_id,
                    command_intent_class, command_priority_class, command_status_class,
                    orchestration_eligibility_class, command_reason_codes_json,
                    command_reason_text, explanation_json, advisory_resolution_version,
                    command_intent_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    run_id,
                    market_id,
                    resolution_record_id,
                    intent.get("exit_advisory_record_id"),
                    str(intent["exposure_type"]),
                    str(intent["exposure_ref_id"]),
                    str(intent["command_intent_class"]),
                    str(intent["command_priority_class"]),
                    str(intent["command_status_class"]),
                    str(intent["orchestration_eligibility_class"]),
                    Jsonb(list(intent.get("reason_codes", ["seeded_command_intent"]))),
                    str(intent.get("reason_text", "seeded command intent")),
                    Jsonb(dict(intent.get("explanation", {"seed": "phase9a"}))),
                    str(intent.get("advisory_resolution_version", "phase8c-advisory-resolution-v1")),
                    COMMAND_INTENT_VERSION,
                ),
            )
    return run_id


def test_orchestration_gate_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"orchestration_gate_runs", "orchestration_gate_records", "orchestration_packets"} <= table_names


def test_successful_gate_run_persists_correctly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-run-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)

    result = ControlledOrchestrationGateService().generate_for_markets([market_id], source_type="phase9a_test", source_ref="phase9a")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM orchestration_gate_runs WHERE id = %s LIMIT 1", (result.orchestration_gate_run_id,)).fetchone()
        gate_row = conn.execute("SELECT * FROM orchestration_gate_records WHERE orchestration_gate_run_id = %s LIMIT 1", (result.orchestration_gate_run_id,)).fetchone()
        packet_row = conn.execute("SELECT * FROM orchestration_packets WHERE orchestration_gate_run_id = %s LIMIT 1", (result.orchestration_gate_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["orchestration_version"] == ORCHESTRATION_VERSION
    assert gate_row is not None
    assert gate_row["market_id"] == market_id
    assert packet_row is not None
    assert packet_row["packet_status_class"] == "DRY_RUN_READY"


def test_deterministic_allow_defer_block_behavior_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    allow_market = f"gate-allow-{uuid4().hex[:6]}"
    defer_market = f"gate-defer-{uuid4().hex[:6]}"
    block_market = f"gate-block-{uuid4().hex[:6]}"

    _seed_invalidation_policy_record(
        market_id=allow_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    allow_exposure_id = _seed_live_position(market_id=allow_market)
    _run_upstream_command_intents_for_market(allow_market)
    first_gate = ControlledOrchestrationGateService().generate_for_markets([allow_market], source_type="phase9a_test")
    assert first_gate is not None

    _seed_invalidation_policy_record(
        market_id=defer_market,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    defer_exposure_id = _seed_paper_position(market_id=defer_market)
    _run_upstream_command_intents_for_market(defer_market)

    _seed_invalidation_policy_record(
        market_id=block_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    block_exposure_id = _seed_paper_position(market_id=block_market)
    _run_upstream_command_intents_for_market(block_market)

    second_gate = ControlledOrchestrationGateService().generate_for_markets(
        [allow_market, defer_market, block_market],
        source_type="phase9a_test",
    )
    assert second_gate is not None

    query = ControlledOrchestrationQueryService()
    allow_details = query.compare_orchestration_packet_to_upstream_context(allow_market)
    defer_details = query.compare_orchestration_packet_to_upstream_context(defer_market)
    block_details = query.compare_orchestration_packet_to_upstream_context(block_market)

    assert allow_details is not None
    assert any(
        str(row["orchestration_decision_class"]) == "DEFER"
        for row in allow_details["orchestration_gate_records"]
        if str(row["market_id"]) == allow_market
    )
    assert defer_details is not None
    assert any(
        str(row["orchestration_decision_class"]) == "DEFER"
        for row in defer_details["orchestration_gate_records"]
        if str(row["market_id"]) == defer_market
    )
    assert block_details is not None
    assert any(
        str(row["orchestration_decision_class"]) == "BLOCK"
        for row in block_details["orchestration_gate_records"]
        if str(row["market_id"]) == block_market
    )
    assert allow_exposure_id != defer_exposure_id != block_exposure_id


def test_duplicate_suppression_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-dup-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    exposure_id = _seed_live_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)
    resolution = _latest_resolution_record(market_id)
    exit_advisory = _latest_exit_advisory_record(market_id)
    custom_run_id = _seed_custom_command_intent_run(
        market_id=market_id,
        resolution_record_id=str(resolution["id"]),
        intents=[
            {
                "exit_advisory_record_id": str(exit_advisory["id"]),
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": exposure_id,
                "command_intent_class": "EXIT_POSITION",
                "command_priority_class": "CRITICAL",
                "command_status_class": "STAGED",
                "orchestration_eligibility_class": "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION",
            },
            {
                "exit_advisory_record_id": str(exit_advisory["id"]),
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": exposure_id,
                "command_intent_class": "EXIT_POSITION",
                "command_priority_class": "CRITICAL",
                "command_status_class": "STAGED",
                "orchestration_eligibility_class": "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION",
            },
        ],
    )

    result = ControlledOrchestrationGateService().generate_for_command_intent_run(custom_run_id, source_ref="dup")
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            """
            SELECT orchestration_decision_class
            FROM orchestration_gate_records
            WHERE orchestration_gate_run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (result.orchestration_gate_run_id,),
        ).fetchall()
    assert len(rows) == 2
    assert {str(row["orchestration_decision_class"]) for row in rows} == {"ALLOW_DRY_RUN", "SUPPRESS_DUPLICATE"}


def test_conflict_suppression_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-conflict-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    exposure_id = _seed_live_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)
    resolution = _latest_resolution_record(market_id)
    exit_advisory = _latest_exit_advisory_record(market_id)
    custom_run_id = _seed_custom_command_intent_run(
        market_id=market_id,
        resolution_record_id=str(resolution["id"]),
        intents=[
            {
                "exit_advisory_record_id": str(exit_advisory["id"]),
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": exposure_id,
                "command_intent_class": "EXIT_POSITION",
                "command_priority_class": "CRITICAL",
                "command_status_class": "STAGED",
                "orchestration_eligibility_class": "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION",
            },
            {
                "exit_advisory_record_id": str(exit_advisory["id"]),
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": exposure_id,
                "command_intent_class": "REDUCE_POSITION",
                "command_priority_class": "HIGH",
                "command_status_class": "STAGED",
                "orchestration_eligibility_class": "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION",
            },
        ],
    )

    result = ControlledOrchestrationGateService().generate_for_command_intent_run(custom_run_id, source_ref="conflict")
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            """
            SELECT orchestration_decision_class
            FROM orchestration_gate_records
            WHERE orchestration_gate_run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (result.orchestration_gate_run_id,),
        ).fetchall()
    assert len(rows) == 2
    assert {str(row["orchestration_decision_class"]) for row in rows} == {"ALLOW_DRY_RUN", "SUPPRESS_CONFLICT"}


def test_max_actions_per_run_handling_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    market_ids: list[str] = []
    for index in range(MAX_ACTIONS_PER_RUN + 1):
        market_id = f"gate-max-{index}-{uuid4().hex[:5]}"
        market_ids.append(market_id)
        _seed_invalidation_policy_record(
            market_id=market_id,
            invalidation_state_class="INVALIDATED",
            exit_policy_class="EXIT_RECOMMENDED",
            deployment_gate_effect="HARD_BLOCK",
        )
        _seed_live_position(market_id=market_id)
        _run_upstream_command_intents_for_market(market_id)

    result = ControlledOrchestrationGateService().generate_for_markets(market_ids, source_type="phase9a_test")
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        counts = conn.execute(
            """
            SELECT orchestration_decision_class, COUNT(*) AS count
            FROM orchestration_gate_records
            WHERE orchestration_gate_run_id = %s
            GROUP BY orchestration_decision_class
            """,
            (result.orchestration_gate_run_id,),
        ).fetchall()
    summary = {str(row["orchestration_decision_class"]): int(row["count"]) for row in counts}
    assert summary["ALLOW_DRY_RUN"] == MAX_ACTIONS_PER_RUN
    assert summary["DEFER"] == 1


def test_packet_formation_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    markets = []
    for suffix in ("a", "b"):
        market_id = f"gate-packet-{suffix}-{uuid4().hex[:5]}"
        markets.append(market_id)
        _seed_invalidation_policy_record(
            market_id=market_id,
            invalidation_state_class="INVALIDATED",
            exit_policy_class="EXIT_RECOMMENDED",
            deployment_gate_effect="HARD_BLOCK",
        )
        _seed_live_position(market_id=market_id)
        _run_upstream_command_intents_for_market(market_id)

    result = ControlledOrchestrationGateService().generate_for_markets(markets, source_type="phase9a_test")
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        packet = conn.execute(
            "SELECT * FROM orchestration_packets WHERE orchestration_gate_run_id = %s LIMIT 1",
            (result.orchestration_gate_run_id,),
        ).fetchone()
    assert packet is not None
    assert packet["packet_status_class"] == "DRY_RUN_READY"
    assert packet["packet_action_count"] == 2
    assert packet["markets_covered_count"] == 2
    assert len(packet["included_command_intent_ids_json"]) == 2


def test_packet_priority_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    critical_market = f"gate-pri-crit-{uuid4().hex[:5]}"
    high_market = f"gate-pri-high-{uuid4().hex[:5]}"

    _seed_invalidation_policy_record(
        market_id=critical_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=critical_market)
    _run_upstream_command_intents_for_market(critical_market)

    _seed_invalidation_policy_record(
        market_id=high_market,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_paper_position(market_id=high_market)
    _run_upstream_command_intents_for_market(high_market)

    result = ControlledOrchestrationGateService().generate_for_markets([critical_market, high_market], source_type="phase9a_test")
    assert result is not None
    query = ControlledOrchestrationQueryService()
    packet = query.list_dry_run_ready_packets(limit=10)[0]
    assert packet["packet_priority_class"] == "CRITICAL"


def test_empty_result_handling_is_explicit_and_honest(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-empty-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_paper_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)

    result = ControlledOrchestrationGateService().generate_for_markets([market_id], source_type="phase9a_test")
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        packet = conn.execute(
            "SELECT * FROM orchestration_packets WHERE orchestration_gate_run_id = %s LIMIT 1",
            (result.orchestration_gate_run_id,),
        ).fetchone()
    assert packet is not None
    assert packet["packet_status_class"] == "EMPTY"
    assert packet["packet_action_count"] == 0


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-query-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)

    result = ControlledOrchestrationGateService().generate_for_markets([market_id], source_type="phase9a_test")
    assert result is not None

    query = ControlledOrchestrationQueryService()
    summary = query.get_orchestration_gate_run_summary(result.orchestration_gate_run_id)
    rows = query.list_orchestration_gate_records_for_run(result.orchestration_gate_run_id)
    details = query.get_orchestration_gate_record_details(market_id=market_id)
    packets = query.list_dry_run_ready_packets()
    comparison = query.compare_orchestration_packet_to_upstream_context(market_id)

    assert summary is not None
    assert summary["gate_record_count"] == 1
    assert summary["packet_count"] == 1
    assert len(rows) == 1
    assert details is not None
    assert len(packets) == 1
    assert comparison is not None
    assert len(comparison["orchestration_gate_records"]) == 1
    assert len(comparison["orchestration_packets"]) == 1
    assert len(comparison["command_intent_records"]) == 1
    assert comparison["advisory_resolution_record"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    class DummyService:
        enabled = True

        def generate_for_markets(self, market_ids: list[str], *, source_type: str, source_ref: str | None):
            captured["market_ids"] = market_ids
            captured["source_type"] = source_type
            captured["source_ref"] = source_ref
            return OrchestrationGateRunResult(
                orchestration_gate_run_id="phase9a-run",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

    monkeypatch.setattr("app.services.controlled_orchestration_gate.ControlledOrchestrationGateService", DummyService)
    exit_code = orchestration_gate_main(["--market-ids", "mkt-a", "mkt-b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["market_ids"] == ["mkt-a", "mkt-b"]
    assert "orchestration_gate_run_id=phase9a-run" in output


def test_no_mutation_occurs_to_live_paper_shadow_orders_or_positions(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"gate-isolated-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=market_id)
    _run_upstream_command_intents_for_market(market_id)

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

    result = ControlledOrchestrationGateService().generate_for_markets([market_id], source_type="phase9a_test")
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
