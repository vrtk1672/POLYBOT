from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.advisory_resolution import (
    ADVISORY_RESOLUTION_VERSION,
    AdvisoryResolutionRunResult,
    AdvisoryResolutionService,
    main as advisory_resolution_main,
)
from app.services.exit_advisory import ADVISORY_VERSION, ExitAdvisoryService
from app.services.query.advisory_resolution_query_service import AdvisoryResolutionQueryService
from test_phase8b_exit_advisory import (
    _seed_invalidation_policy_record,
    _seed_live_order,
    _seed_live_position,
    _seed_paper_order,
    _seed_paper_position,
    _seed_shadow_order,
    _seed_shadow_position,
)


def _seed_conflicting_exit_advisories(*, market_id: str, invalidation_policy_record_id: str) -> str:
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
                "phase8c_seed",
                market_id,
                "COMPLETED",
                ADVISORY_VERSION,
                2,
                2,
                0,
                Jsonb({"seed": "phase8c-conflict"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO exit_advisory_records (
                id, exit_advisory_run_id, market_id, invalidation_policy_record_id,
                exposure_type, exposure_ref_id, advisory_action_class, advisory_priority_class,
                advisory_reason_codes_json, advisory_reason_text, explanation_json, advisory_version
            )
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid4()),
                run_id,
                market_id,
                invalidation_policy_record_id,
                "LIVE_POSITION",
                str(uuid4()),
                "EXIT",
                "CRITICAL",
                Jsonb(["seed_exit"]),
                "seed exit advisory",
                Jsonb({"seed": "exit"}),
                ADVISORY_VERSION,
                str(uuid4()),
                run_id,
                market_id,
                invalidation_policy_record_id,
                "SHADOW_ORDER",
                str(uuid4()),
                "BLOCK_NEW_ENTRY",
                "HIGH",
                Jsonb(["seed_block_new_entry"]),
                "seed block new entry advisory",
                Jsonb({"seed": "block_new_entry"}),
                ADVISORY_VERSION,
            ),
        )
    return run_id


def test_advisory_resolution_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"advisory_resolution_runs", "advisory_resolution_records"} <= table_names


def test_successful_resolution_run_persists_correctly(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"res-run-{uuid4().hex[:8]}"
    seeded = _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_paper_position(market_id=market_id)
    advisory_run = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8c_test")
    assert advisory_run is not None

    result = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8c_test", source_ref="phase8c")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM advisory_resolution_runs WHERE id = %s LIMIT 1", (result.advisory_resolution_run_id,)).fetchone()
        record_row = conn.execute("SELECT * FROM advisory_resolution_records WHERE advisory_resolution_run_id = %s LIMIT 1", (result.advisory_resolution_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["advisory_resolution_version"] == ADVISORY_RESOLUTION_VERSION
    assert record_row is not None
    assert record_row["market_id"] == market_id
    assert str(record_row["invalidation_policy_record_id"]) == seeded["record_id"]
    assert str(record_row["exit_advisory_run_id"]) == advisory_run.exit_advisory_run_id


@pytest.mark.parametrize(
    ("market_suffix", "policy_exit", "seed_fn", "expected_action"),
    [
        ("keep", "HOLD", _seed_paper_position, "KEEP"),
        ("watch", "MONITOR_CLOSELY", _seed_live_position, "WATCH"),
        ("reduce", "REDUCE_EXPOSURE", _seed_paper_position, "REDUCE"),
        ("prepare", "PREPARE_EXIT", _seed_shadow_position, "PREPARE_EXIT"),
        ("exit", "EXIT_RECOMMENDED", _seed_live_position, "EXIT"),
        ("none", "HOLD", None, "NO_ACTION"),
    ],
)
def test_deterministic_primary_action_selection_behaves_as_expected(
    postgres_test_schema,
    market_suffix: str,
    policy_exit: str,
    seed_fn,
    expected_action: str,
) -> None:
    run_migrations()
    market_id = f"res-primary-{market_suffix}-{uuid4().hex[:6]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="WATCH",
        exit_policy_class=policy_exit,
        deployment_gate_effect="NONE" if policy_exit != "EXIT_RECOMMENDED" else "HARD_BLOCK",
    )
    if seed_fn is not None:
        seed_fn(market_id=market_id)
        assert ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8c_test") is not None

    result = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8c_test")
    assert result is not None
    record = AdvisoryResolutionQueryService().get_advisory_resolution_record_details(market_id=market_id)
    assert record is not None
    assert record["primary_advisory_action_class"] == expected_action


def test_deterministic_priority_assignment_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    critical_market = f"res-priority-crit-{uuid4().hex[:6]}"
    medium_market = f"res-priority-med-{uuid4().hex[:6]}"
    low_market = f"res-priority-low-{uuid4().hex[:6]}"

    _seed_invalidation_policy_record(
        market_id=critical_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=critical_market)
    assert ExitAdvisoryService().generate_for_markets([critical_market], source_type="phase8c_test") is not None

    _seed_invalidation_policy_record(
        market_id=medium_market,
        invalidation_state_class="WATCH",
        exit_policy_class="MONITOR_CLOSELY",
        deployment_gate_effect="NONE",
    )
    _seed_live_position(market_id=medium_market)
    assert ExitAdvisoryService().generate_for_markets([medium_market], source_type="phase8c_test") is not None

    _seed_invalidation_policy_record(
        market_id=low_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )
    _seed_paper_position(market_id=low_market)
    assert ExitAdvisoryService().generate_for_markets([low_market], source_type="phase8c_test") is not None

    service = AdvisoryResolutionService()
    assert service.generate_for_markets([critical_market, medium_market, low_market], source_type="phase8c_test") is not None

    query = AdvisoryResolutionQueryService()
    assert query.get_advisory_resolution_record_details(market_id=critical_market)["primary_priority_class"] == "CRITICAL"
    assert query.get_advisory_resolution_record_details(market_id=medium_market)["primary_priority_class"] == "MEDIUM"
    assert query.get_advisory_resolution_record_details(market_id=low_market)["primary_priority_class"] == "LOW"


def test_conflict_detection_behaves_as_expected(postgres_test_schema) -> None:
    run_migrations()
    material_market = f"res-conflict-material-{uuid4().hex[:6]}"
    minor_market = f"res-conflict-minor-{uuid4().hex[:6]}"

    material_seeded = _seed_invalidation_policy_record(
        market_id=material_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_conflicting_exit_advisories(
        market_id=material_market,
        invalidation_policy_record_id=material_seeded["record_id"],
    )

    _seed_invalidation_policy_record(
        market_id=minor_market,
        invalidation_state_class="INVALIDATION_CANDIDATE",
        exit_policy_class="PREPARE_EXIT",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_live_position(market_id=minor_market)
    _seed_shadow_position(market_id=minor_market)
    assert ExitAdvisoryService().generate_for_markets([minor_market], source_type="phase8c_test") is not None

    service = AdvisoryResolutionService()
    assert service.generate_for_markets([material_market, minor_market], source_type="phase8c_test") is not None

    query = AdvisoryResolutionQueryService()
    material = query.get_advisory_resolution_record_details(market_id=material_market)
    minor = query.get_advisory_resolution_record_details(market_id=minor_market)

    assert material is not None
    assert material["primary_advisory_action_class"] == "MIXED_ACTIONS"
    assert material["conflict_status_class"] == "MATERIAL_CONFLICT"
    assert minor is not None
    assert minor["primary_advisory_action_class"] == "PREPARE_EXIT"
    assert minor["conflict_status_class"] == "MINOR_CONFLICT"


def test_action_readiness_assignment_behaves_conservatively_and_honestly(postgres_test_schema) -> None:
    run_migrations()
    orchestration_market = f"res-ready-orch-{uuid4().hex[:6]}"
    review_market = f"res-ready-review-{uuid4().hex[:6]}"
    not_ready_market = f"res-ready-none-{uuid4().hex[:6]}"

    _seed_invalidation_policy_record(
        market_id=orchestration_market,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=orchestration_market)
    assert ExitAdvisoryService().generate_for_markets([orchestration_market], source_type="phase8c_test") is not None

    _seed_invalidation_policy_record(
        market_id=review_market,
        invalidation_state_class="DEGRADED",
        exit_policy_class="REDUCE_EXPOSURE",
        deployment_gate_effect="SOFT_BLOCK",
    )
    _seed_paper_position(market_id=review_market)
    assert ExitAdvisoryService().generate_for_markets([review_market], source_type="phase8c_test") is not None

    _seed_invalidation_policy_record(
        market_id=not_ready_market,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )

    service = AdvisoryResolutionService()
    assert service.generate_for_markets([orchestration_market, review_market, not_ready_market], source_type="phase8c_test") is not None

    query = AdvisoryResolutionQueryService()
    assert query.get_advisory_resolution_record_details(market_id=orchestration_market)["action_readiness_class"] == "READY_FOR_CONTROLLED_ORCHESTRATION"
    assert query.get_advisory_resolution_record_details(market_id=review_market)["action_readiness_class"] == "READY_FOR_REVIEW"
    assert query.get_advisory_resolution_record_details(market_id=not_ready_market)["action_readiness_class"] == "NOT_READY"


def test_sparse_context_or_unsupported_advisories_are_honest(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"res-sparse-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="THESIS_INTACT",
        exit_policy_class="HOLD",
        deployment_gate_effect="NONE",
    )

    result = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8c_test")
    assert result is not None
    record = AdvisoryResolutionQueryService().get_advisory_resolution_record_details(market_id=market_id)
    assert record is not None
    assert record["primary_advisory_action_class"] == "NO_ACTION"
    assert record["action_readiness_class"] == "NOT_READY"
    assert record["exposure_count"] == 0


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"res-query-{uuid4().hex[:8]}"
    _seed_invalidation_policy_record(
        market_id=market_id,
        invalidation_state_class="INVALIDATED",
        exit_policy_class="EXIT_RECOMMENDED",
        deployment_gate_effect="HARD_BLOCK",
    )
    _seed_live_position(market_id=market_id)
    advisory_run = ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8c_test")
    assert advisory_run is not None
    result = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8c_test")
    assert result is not None

    query = AdvisoryResolutionQueryService()
    summary = query.get_advisory_resolution_run_summary(result.advisory_resolution_run_id)
    rows = query.list_advisory_resolution_records_for_run(result.advisory_resolution_run_id)
    details = query.get_advisory_resolution_record_details(market_id=market_id)
    ready = query.list_action_ready_records()
    comparison = query.compare_advisory_resolution_to_upstream_context(market_id)

    assert summary is not None
    assert summary["record_count"] == 1
    assert len(rows) == 1
    assert details is not None
    assert len(ready) == 1
    assert comparison is not None
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
            return AdvisoryResolutionRunResult(
                advisory_resolution_run_id="phase8c-run",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

    monkeypatch.setattr("app.services.advisory_resolution.AdvisoryResolutionService", DummyService)
    exit_code = advisory_resolution_main(["--market-ids", "mkt-a", "mkt-b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["market_ids"] == ["mkt-a", "mkt-b"]
    assert "advisory_resolution_run_id=phase8c-run" in output


def test_no_mutation_occurs_to_live_paper_shadow_exposure_state(postgres_test_schema) -> None:
    run_migrations()
    market_id = f"res-isolated-{uuid4().hex[:8]}"
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
    assert ExitAdvisoryService().generate_for_markets([market_id], source_type="phase8c_test") is not None

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

    result = AdvisoryResolutionService().generate_for_markets([market_id], source_type="phase8c_test")
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
