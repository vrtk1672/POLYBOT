from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.advisory_resolution import AdvisoryResolutionService
from app.services.command_intent_staging import (
    COMMAND_INTENT_VERSION,
    CommandIntentRunResult,
    CommandIntentStagingService,
    main as command_intent_main,
)
from app.services.exit_advisory import ADVISORY_VERSION, ExitAdvisoryService
from app.services.query.command_intent_query_service import CommandIntentQueryService
from test_phase8b_exit_advisory import (
    _seed_invalidation_policy_record,
    _seed_live_order,
    _seed_live_position,
    _seed_paper_order,
    _seed_paper_position,
    _seed_shadow_order,
    _seed_shadow_position,
)
from test_phase8c_advisory_resolution import _seed_conflicting_exit_advisories


def _seed_custom_exit_advisories(
    *,
    market_id: str,
    invalidation_policy_record_id: str,
    advisories: list[dict[str, object]],
) -> str:
    factory = DatabaseConnectionFactory()
    run_id = str(uuid4())
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO exit_advisory_runs (
                id, source_type, source_ref, status, advisory_version,
                started_at, ended_at, input_count, success_count, failure_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, now(), now(), %s, %s, %s, %s)
            """,
            (
                run_id,
                "phase8d_seed",
                market_id,
                "COMPLETED",
                ADVISORY_VERSION,
                len(advisories),
                len(advisories),
                0,
                Jsonb({"seed": "phase8d"}),
            ),
        )
        for advisory in advisories:
            conn.execute(
                """
                INSERT INTO exit_advisory_records (
                    id, exit_advisory_run_id, market_id, invalidation_policy_record_id,
                    exposure_type, exposure_ref_id, advisory_action_class, advisory_priority_class,
                    advisory_reason_codes_json, advisory_reason_text, explanation_json, advisory_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    run_id,
                    market_id,
                    invalidation_policy_record_id,
                    str(advisory["exposure_type"]),
                    str(advisory["exposure_ref_id"]),
                    str(advisory["advisory_action_class"]),
                    str(advisory["advisory_priority_class"]),
                    Jsonb(list(advisory.get("reason_codes", ["seeded_exit_advisory"]))),
                    str(advisory.get("reason_text", "seeded exit advisory")),
                    Jsonb(dict(advisory.get("explanation", {"seed": "phase8d"}))),
                    ADVISORY_VERSION,
                ),
            )
    return run_id


def _run_upstream_resolution_for_market(market_id: str) -> tuple[object, object]:
    advisory_run = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8d_test")
    assert advisory_run is not None
    resolution_run = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8d_test")
    assert resolution_run is not None
    return advisory_run, resolution_run


def test_command_intent_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"command_intent_runs", "command_intent_records"} <= table_names


def test_successful_command_intent_run_persists_correctly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"cmd-run-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_paper_position(market_id=market_id)
    _run_upstream_resolution_for_market(market_id)

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test", source_ref="phase8d")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM command_intent_runs WHERE id = %s LIMIT 1", (result.command_intent_run_id,)).fetchone()
        record_row = conn.execute("SELECT * FROM command_intent_records WHERE command_intent_run_id = %s LIMIT 1", (result.command_intent_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["command_intent_version"] == COMMAND_INTENT_VERSION
    assert record_row is not None
    assert record_row["market_id"] == market_id
    assert str(record_row["advisory_resolution_record_id"]) != ""
    assert str(record_row["exit_advisory_record_id"]) != ""
    assert str(record_row["command_intent_class"]) == "REDUCE_POSITION"
    assert str(record_row["advisory_resolution_version"]) != ""
    assert str(record_row["command_intent_version"]) == COMMAND_INTENT_VERSION
    assert seeded["record_id"] is not None


@pytest.mark.parametrize(
    ("market_suffix", "policy_exit", "seed_fn", "seed_kwargs", "expected_intent"),
    [
        ("keep", "HOLD", _seed_paper_position, {}, "NO_OP"),
        ("watch", "MONITOR_CLOSELY", _seed_live_position, {}, "WATCH_ONLY"),
        ("reduce", "REDUCE_EXPOSURE", _seed_paper_position, {}, "REDUCE_POSITION"),
        ("prepare", "PREPARE_EXIT", _seed_shadow_position, {}, "PREPARE_POSITION_EXIT"),
        ("exit", "EXIT_RECOMMENDED", _seed_live_position, {}, "EXIT_POSITION"),
        ("cancel", "PREPARE_EXIT", _seed_paper_order, {"status": "OPEN"}, "CANCEL_PENDING_ORDER"),
        ("block", "BLOCK_NEW_DEPLOYMENT", _seed_shadow_order, {"status": "WOULD_SUBMIT"}, "BLOCK_NEW_ENTRY"),
    ],
)
def test_deterministic_command_intent_mapping_behaves_as_expected(
    postgres_test_schema,
    market_suffix: str,
    policy_exit: str,
    seed_fn,
    seed_kwargs: dict[str, object],
    expected_intent: str,
) -> None:
    run_migrations()
    market_id = f"cmd-map-{market_suffix}-{uuid4().hex[:6]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="WATCH" if policy_exit != "EXIT_RECOMMENDED" else "INVALIDATED",
        exit_policy_class=policy_exit,
        deployment_gate_effect="HARD_BLOCK" if policy_exit in {"EXIT_RECOMMENDED", "BLOCK_NEW_DEPLOYMENT"} else "SOFT_BLOCK" if policy_exit in {"REDUCE_EXPOSURE", "PREPARE_EXIT"} else "NONE",
    )
    exposure_id = seed_fn(market_id=market_id, **seed_kwargs)
    _run_upstream_resolution_for_market(market_id)

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test")
    assert result is not None
    record = CommandIntentQueryService().get_command_intent_record_details(
        exposure_type="PAPER_POSITION" if seed_fn is _seed_paper_position else
        "LIVE_POSITION" if seed_fn is _seed_live_position else
        "SHADOW_POSITION" if seed_fn is _seed_shadow_position else
        "PAPER_ORDER" if seed_fn is _seed_paper_order else
        "SHADOW_ORDER",
        exposure_ref_id=exposure_id,
    )
    assert record is not None
    assert record["command_intent_class"] == expected_intent


def test_command_priority_assignment_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    critical_market = f"cmd-pri-crit-{uuid4().hex[:6]}"
    medium_market = f"cmd-pri-med-{uuid4().hex[:6]}"
    low_market = f"cmd-pri-low-{uuid4().hex[:6]}"

    _seed_invalidation_policy_record(
        market_id=critical_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    critical_exposure_id = _seed_live_position(market_id=critical_market)
    _run_upstream_resolution_for_market(critical_market)

    _seed_invalidation_policy_record(
        market_id=medium_market,
        invalidation_state_class="WATCH",
        exit_policy_class="MONITOR_CLOSELY",
        deployment_gate_effect="NONE",
    )
    medium_exposure_id = _seed_live_position(market_id=medium_market)
    _run_upstream_resolution_for_market(medium_market)

    _seed_invalidation_policy_record(
        market_id=low_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    low_exposure_id = _seed_paper_position(market_id=low_market)
    _run_upstream_resolution_for_market(low_market)

    service = CommandIntentStagingService()
    assert service.generate_for_markets([critical_market, medium_market, low_market], source_type="phase8d_test") is not None

    query = CommandIntentQueryService()
    assert query.get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=critical_exposure_id)["command_priority_class"] == "CRITICAL"
    assert query.get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=medium_exposure_id)["command_priority_class"] == "MEDIUM"
    assert query.get_command_intent_record_details(exposure_type="PAPER_POSITION", exposure_ref_id=low_exposure_id)["command_priority_class"] == "LOW"


def test_suppression_rules_behave_honestly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"cmd-suppress-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    missing_exposure_id = str(uuid4())
    _seed_custom_exit_advisories(
        market_id=market_id,
        invalidation_policy_record_id=seeded["record_id"],
        advisories=[
            {
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": missing_exposure_id,
                "advisory_action_class": "EXIT",
                "advisory_priority_class": "CRITICAL",
            }
        ],
    )
    resolution = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8d_test")
    assert resolution is not None

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test")
    assert result is not None
    record = CommandIntentQueryService().get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=missing_exposure_id)
    assert record is not None
    assert record["command_intent_class"] == "EXIT_POSITION"
    assert record["command_status_class"] == "SUPPRESSED"
    assert record["orchestration_eligibility_class"] == "INELIGIBLE"
    assert "missing_exposure_row" in record["command_reason_codes_json"]


def test_eligibility_classification_behaves_conservatively_and_correctly(postgres_test_schema) -> None:
    run_migrations()
    orchestration_market = f"cmd-elig-orch-{uuid4().hex[:6]}"
    review_market = f"cmd-elig-review-{uuid4().hex[:6]}"
    ineligible_market = f"cmd-elig-none-{uuid4().hex[:6]}"

    _seed_invalidation_policy_record(
        market_id=orchestration_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    orchestration_id = _seed_live_position(market_id=orchestration_market)
    _run_upstream_resolution_for_market(orchestration_market)

    _seed_invalidation_policy_record(
        market_id=review_market,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    review_id = _seed_paper_position(market_id=review_market)
    _run_upstream_resolution_for_market(review_market)

    _seed_invalidation_policy_record(
        market_id=ineligible_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    ineligible_id = _seed_paper_position(market_id=ineligible_market)
    _run_upstream_resolution_for_market(ineligible_market)

    service = CommandIntentStagingService()
    assert service.generate_for_markets([orchestration_market, review_market, ineligible_market], source_type="phase8d_test") is not None

    query = CommandIntentQueryService()
    assert query.get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=orchestration_id)["orchestration_eligibility_class"] == "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION"
    assert query.get_command_intent_record_details(exposure_type="PAPER_POSITION", exposure_ref_id=review_id)["orchestration_eligibility_class"] == "REVIEW_REQUIRED"
    assert query.get_command_intent_record_details(exposure_type="PAPER_POSITION", exposure_ref_id=ineligible_id)["orchestration_eligibility_class"] == "INELIGIBLE"


def test_mixed_action_handling_is_honest(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"cmd-mixed-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    live_position_id = _seed_live_position(market_id=market_id)
    shadow_order_id = _seed_shadow_order(market_id=market_id, status="WOULD_SUBMIT")
    _seed_custom_exit_advisories(
        market_id=market_id,
        invalidation_policy_record_id=seeded["record_id"],
        advisories=[
            {
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": live_position_id,
                "advisory_action_class": "EXIT",
                "advisory_priority_class": "CRITICAL",
            },
            {
                "exposure_type": "SHADOW_ORDER",
                "exposure_ref_id": shadow_order_id,
                "advisory_action_class": "BLOCK_NEW_ENTRY",
                "advisory_priority_class": "HIGH",
            },
        ],
    )
    resolution = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8d_test")
    assert resolution is not None

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test")
    assert result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        rows = conn.execute(
            """
            SELECT command_intent_class, command_status_class, orchestration_eligibility_class
            FROM command_intent_records
            WHERE market_id = %s
            ORDER BY command_intent_class ASC
            """,
            (market_id,),
        ).fetchall()
    assert len(rows) == 2
    assert {str(row["command_intent_class"]) for row in rows} == {"BLOCK_NEW_ENTRY", "EXIT_POSITION"}
    assert {str(row["command_status_class"]) for row in rows} == {"NOT_ELIGIBLE"}
    assert {str(row["orchestration_eligibility_class"]) for row in rows} == {"INELIGIBLE"}


def test_unsupported_or_sparse_contexts_are_handled_honestly(postgres_test_schema) -> None:
    run_migrations()
    sparse_market = f"cmd-sparse-{uuid4().hex[:8]}"
    irrelevant_market = f"cmd-irrelevant-{uuid4().hex[:8]}"

    _seed_invalidation_policy_record(
        market_id=sparse_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    sparse_resolution = AdvisoryResolutionService().generate_for_markets([sparse_market], source_type="phase8d_test")
    assert sparse_resolution is not None

    irrelevant_seeded = _seed_invalidation_policy_record(
        market_id=irrelevant_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    irrelevant_exposure_id = _seed_live_position(market_id=irrelevant_market, current_status="CLOSED")
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            "UPDATE positions SET closed_at = now() WHERE id = %s",
            (irrelevant_exposure_id,),
        )
    _seed_custom_exit_advisories(
        market_id=irrelevant_market,
        invalidation_policy_record_id=irrelevant_seeded["record_id"],
        advisories=[
            {
                "exposure_type": "LIVE_POSITION",
                "exposure_ref_id": irrelevant_exposure_id,
                "advisory_action_class": "EXIT",
                "advisory_priority_class": "CRITICAL",
            }
        ],
    )
    irrelevant_resolution = AdvisoryResolutionService().generate_for_markets([irrelevant_market], source_type="phase8d_test")
    assert irrelevant_resolution is not None

    service = CommandIntentStagingService()
    assert service.generate_for_markets([sparse_market, irrelevant_market], source_type="phase8d_test") is not None

    with factory.connect() as conn:
        sparse_count = conn.execute("SELECT COUNT(*) AS count FROM command_intent_records WHERE market_id = %s", (sparse_market,)).fetchone()["count"]
    assert sparse_count == 0

    irrelevant = CommandIntentQueryService().get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=irrelevant_exposure_id)
    assert irrelevant is not None
    assert irrelevant["command_status_class"] == "SUPPRESSED"
    assert "irrelevant_or_terminal_exposure" in irrelevant["command_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"cmd-query-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    exposure_id = _seed_live_position(market_id=market_id)
    _run_upstream_resolution_for_market(market_id)

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test")
    assert result is not None

    query = CommandIntentQueryService()
    summary = query.get_command_intent_run_summary(result.command_intent_run_id)
    rows = query.list_command_intent_records_for_run(result.command_intent_run_id)
    details = query.get_command_intent_record_details(exposure_type="LIVE_POSITION", exposure_ref_id=exposure_id)
    eligible = query.list_orchestration_eligible_command_intents()
    comparison = query.compare_command_intent_to_upstream_context(market_id)

    assert summary is not None
    assert summary["record_count"] == 1
    assert len(rows) == 1
    assert details is not None
    assert len(eligible) == 1
    assert comparison is not None
    assert len(comparison["command_intent_records"]) == 1
    assert comparison["advisory_resolution_record"] is not None
    assert comparison["invalidation_policy_record"] is not None
    assert len(comparison["exit_advisory_records"]) == 1


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    class DummyService:
        enabled = True

        def generate_for_markets(self, market_ids: list[str], *, source_type: str, source_ref: str | None):
            captured["market_ids"] = market_ids
            captured["source_type"] = source_type
            captured["source_ref"] = source_ref
            return CommandIntentRunResult(
                command_intent_run_id="phase8d-run",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

    monkeypatch.setattr("app.services.command_intent_staging.CommandIntentStagingService", DummyService)
    exit_code = command_intent_main(["--market-ids", "mkt-a", "mkt-b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["market_ids"] == ["mkt-a", "mkt-b"]
    assert "command_intent_run_id=phase8d-run" in output


def test_no_mutation_occurs_to_live_paper_shadow_orders_or_positions(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"cmd-isolated-{uuid4().hex[:8]}"
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
    _run_upstream_resolution_for_market(market_id)

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

    result = CommandIntentStagingService().generate_for_markets([market_id], source_type="phase8d_test")
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
