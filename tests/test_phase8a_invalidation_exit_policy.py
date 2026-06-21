from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.bucket_allocation import BucketAllocationService
from app.services.invalidation_exit_policy import (
    POLICY_VERSION,
    InvalidationPolicyRunResult,
    InvalidationExitPolicyService,
    main as invalidation_exit_policy_main,
)
from app.services.query.invalidation_policy_query_service import InvalidationPolicyQueryService
from app.services.ranking_policy import RankingPolicyService
from app.services.ranking_v2 import RankingV2Service
from app.services.trade_classification import TradeClassificationService
from test_phase6a_trade_classification import _seed_cognition_summary, _seed_market_cycle


def _seed_policy_context(
    *,
    market_id: str,
    question: str,
    slug: str,
    hours_to_close: int,
    cognition_conclusion: str,
    cognition_confidence: float,
    cognition_caution: float,
    cognition_usability: str,
) -> dict[str, str]:
    cycle_id = _seed_market_cycle(
        market_id=market_id,
        question=question,
        slug=slug,
        hours_to_close=hours_to_close,
    )
    cognition_summary_id = _seed_cognition_summary(
        market_id=market_id,
        question=question,
        cognition_conclusion=cognition_conclusion,
        confidence=cognition_confidence,
        caution=cognition_caution,
        usability=cognition_usability,
    )
    classification_result = TradeClassificationService().classify_markets([market_id], source_type="phase8a_seed")
    assert classification_result is not None

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        classification_row = conn.execute(
            "SELECT id FROM trade_classifications WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert classification_row is not None
    trade_classification_id = str(classification_row["id"])

    allocation_result = BucketAllocationService().allocate_classifications([trade_classification_id], source_type="phase8a_seed")
    assert allocation_result is not None
    ranking_result = RankingV2Service().rank_markets([market_id], source_type="phase8a_seed")
    assert ranking_result is not None

    with factory.connect() as conn:
        ranking_row = conn.execute(
            "SELECT id FROM ranking_v2_candidates WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert ranking_row is not None

    policy_result = RankingPolicyService().apply_policy_to_candidates([str(ranking_row["id"])], source_type="phase8a_seed")
    assert policy_result is not None

    with factory.connect() as conn:
        allocation_row = conn.execute(
            "SELECT id FROM bucket_allocations WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
        ranking_policy_row = conn.execute(
            "SELECT id FROM ranking_policy_candidates WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
        invalidation_row = conn.execute(
            "SELECT id FROM invalidation_reasonings WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert allocation_row is not None
    assert ranking_policy_row is not None
    assert invalidation_row is not None

    return {
        "cycle_id": cycle_id,
        "cognition_summary_id": cognition_summary_id,
        "invalidation_reasoning_id": str(invalidation_row["id"]),
        "trade_classification_id": trade_classification_id,
        "bucket_allocation_id": str(allocation_row["id"]),
        "ranking_policy_candidate_id": str(ranking_policy_row["id"]),
    }


def _update_invalidation_context(
    *,
    market_id: str,
    thesis_effect_class: str,
    invalidation_risk_score: float,
    confidence_degradation_score: float,
    contradiction_strength_score: float,
    advisory_action_class: str,
    cognition_usability: str | None = None,
    cognition_caution: float | None = None,
) -> None:
    normalized_effect = thesis_effect_class.upper()
    if normalized_effect == "BREAKS_THESIS":
        normalized_effect = "INVALIDATES_THESIS"
    normalized_action = advisory_action_class.upper()
    if normalized_action == "INVALIDATE":
        normalized_action = "PREPARE_INVALIDATION_REVIEW"

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE invalidation_reasonings
            SET thesis_effect_class = %s,
                invalidation_risk_score = %s,
                confidence_degradation_score = %s,
                contradiction_strength_score = %s,
                advisory_action_class = %s
            WHERE id = (
                SELECT id FROM invalidation_reasonings
                WHERE market_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            )
            """,
            (
                normalized_effect,
                invalidation_risk_score,
                confidence_degradation_score,
                contradiction_strength_score,
                normalized_action,
                market_id,
            ),
        )
        if cognition_usability is not None or cognition_caution is not None:
            conn.execute(
                """
                UPDATE cognition_summaries
                SET usability_class = COALESCE(%s, usability_class),
                    caution_score = COALESCE(%s, caution_score)
                WHERE id = (
                    SELECT id FROM cognition_summaries
                    WHERE market_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                (cognition_usability, cognition_caution, market_id),
            )


def test_invalidation_policy_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"invalidation_policy_runs", "invalidation_policy_records"} <= table_names


def test_successful_policy_run_persists_correctly(postgres_test_schema) -> None:
    market_id = f"inv-policy-{uuid4().hex[:8]}"
    seeded = _seed_policy_context(
        market_id=market_id,
        question="Will invalidation policy persistence hold?",
        slug="inv-policy",
        hours_to_close=24,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.82,
        cognition_caution=0.18,
        cognition_usability="USABLE_NOW",
    )

    result = InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test", source_ref="phase8a")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM invalidation_policy_runs WHERE id = %s LIMIT 1", (result.invalidation_policy_run_id,)).fetchone()
        record_row = conn.execute("SELECT * FROM invalidation_policy_records WHERE invalidation_policy_run_id = %s LIMIT 1", (result.invalidation_policy_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["policy_version"] == POLICY_VERSION
    assert record_row is not None
    assert record_row["market_id"] == market_id
    assert str(record_row["cycle_id"]) == seeded["cycle_id"]
    assert str(record_row["ranking_policy_candidate_id"]) == seeded["ranking_policy_candidate_id"]


def test_deterministic_invalidation_state_assignment_behaves_as_expected(postgres_test_schema) -> None:
    intact_market = f"inv-intact-{uuid4().hex[:6]}"
    degraded_market = f"inv-degraded-{uuid4().hex[:6]}"
    invalid_market = f"inv-invalid-{uuid4().hex[:6]}"

    for market_id, question in [
        (intact_market, "Will intact thesis stay healthy?"),
        (degraded_market, "Will degraded thesis stay healthy?"),
        (invalid_market, "Will invalidated thesis stay healthy?"),
    ]:
        _seed_policy_context(
            market_id=market_id,
            question=question,
            slug=market_id,
            hours_to_close=24,
            cognition_conclusion="SUPPORTIVE",
            cognition_confidence=0.80,
            cognition_caution=0.20,
            cognition_usability="USABLE_NOW",
        )

    _update_invalidation_context(
        market_id=intact_market,
        thesis_effect_class="supports_thesis",
        invalidation_risk_score=0.08,
        confidence_degradation_score=0.10,
        contradiction_strength_score=0.06,
            advisory_action_class="NONE",
    )
    _update_invalidation_context(
        market_id=degraded_market,
        thesis_effect_class="warning",
        invalidation_risk_score=0.48,
        confidence_degradation_score=0.50,
        contradiction_strength_score=0.44,
        advisory_action_class="degrade_confidence",
    )
    _update_invalidation_context(
        market_id=invalid_market,
        thesis_effect_class="breaks_thesis",
        invalidation_risk_score=0.92,
        confidence_degradation_score=0.90,
        contradiction_strength_score=0.88,
        advisory_action_class="invalidate",
        cognition_usability="DO_NOT_USE",
        cognition_caution=0.90,
    )

    InvalidationExitPolicyService().evaluate_markets([intact_market, degraded_market, invalid_market], source_type="phase8a_test")
    queries = InvalidationPolicyQueryService()

    assert queries.get_invalidation_policy_record_details(market_id=intact_market)["invalidation_state_class"] == "THESIS_INTACT"
    assert queries.get_invalidation_policy_record_details(market_id=degraded_market)["invalidation_state_class"] == "DEGRADED"
    assert queries.get_invalidation_policy_record_details(market_id=invalid_market)["invalidation_state_class"] == "INVALIDATED"


def test_deterministic_exit_policy_assignment_behaves_as_expected(postgres_test_schema) -> None:
    watch_market = f"exit-watch-{uuid4().hex[:6]}"
    prepare_market = f"exit-prepare-{uuid4().hex[:6]}"
    block_market = f"exit-block-{uuid4().hex[:6]}"

    for market_id in [watch_market, prepare_market, block_market]:
        _seed_policy_context(
            market_id=market_id,
            question=f"Will {market_id} trigger exit handling?",
            slug=market_id,
            hours_to_close=20,
        cognition_conclusion="WATCHFUL",
            cognition_confidence=0.68,
            cognition_caution=0.40,
            cognition_usability="NEEDS_CONFIRMATION",
        )

    _update_invalidation_context(
        market_id=watch_market,
        thesis_effect_class="warning",
        invalidation_risk_score=0.26,
        confidence_degradation_score=0.24,
        contradiction_strength_score=0.22,
            advisory_action_class="NONE",
    )
    _update_invalidation_context(
        market_id=prepare_market,
        thesis_effect_class="warning",
        invalidation_risk_score=0.69,
        confidence_degradation_score=0.64,
        contradiction_strength_score=0.61,
            advisory_action_class="PREPARE_INVALIDATION_REVIEW",
        cognition_caution=0.72,
    )
    _update_invalidation_context(
        market_id=block_market,
        thesis_effect_class="supports_thesis",
        invalidation_risk_score=0.12,
        confidence_degradation_score=0.14,
        contradiction_strength_score=0.10,
            advisory_action_class="NONE",
    )
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE bucket_allocations
            SET deployability_class = 'BLOCKED', deployment_fraction = 0.0
            WHERE market_id = %s
            """,
            (block_market,),
        )

    InvalidationExitPolicyService().evaluate_markets([watch_market, prepare_market, block_market], source_type="phase8a_test")
    queries = InvalidationPolicyQueryService()

    assert queries.get_invalidation_policy_record_details(market_id=watch_market)["exit_policy_class"] == "MONITOR_CLOSELY"
    assert queries.get_invalidation_policy_record_details(market_id=prepare_market)["exit_policy_class"] == "PREPARE_EXIT"
    assert queries.get_invalidation_policy_record_details(market_id=block_market)["exit_policy_class"] == "BLOCK_NEW_DEPLOYMENT"


def test_deployment_gate_effects_behave_correctly(postgres_test_schema) -> None:
    none_market = f"gate-none-{uuid4().hex[:6]}"
    soft_market = f"gate-soft-{uuid4().hex[:6]}"
    hard_market = f"gate-hard-{uuid4().hex[:6]}"

    for market_id in [none_market, soft_market, hard_market]:
        _seed_policy_context(
            market_id=market_id,
            question=f"Will {market_id} test deployment gates?",
            slug=market_id,
            hours_to_close=28,
            cognition_conclusion="SUPPORTIVE",
            cognition_confidence=0.79,
            cognition_caution=0.22,
            cognition_usability="USABLE_NOW",
        )

    _update_invalidation_context(
        market_id=soft_market,
        thesis_effect_class="warning",
        invalidation_risk_score=0.51,
        confidence_degradation_score=0.47,
        contradiction_strength_score=0.46,
            advisory_action_class="DEGRADE_CONFIDENCE",
    )
    _update_invalidation_context(
        market_id=hard_market,
        thesis_effect_class="breaks_thesis",
        invalidation_risk_score=0.95,
        confidence_degradation_score=0.92,
        contradiction_strength_score=0.90,
        advisory_action_class="invalidate",
        cognition_usability="DO_NOT_USE",
        cognition_caution=0.92,
    )

    InvalidationExitPolicyService().evaluate_markets([none_market, soft_market, hard_market], source_type="phase8a_test")
    queries = InvalidationPolicyQueryService()

    assert queries.get_invalidation_policy_record_details(market_id=none_market)["deployment_gate_effect"] == "NONE"
    assert queries.get_invalidation_policy_record_details(market_id=soft_market)["deployment_gate_effect"] == "SOFT_BLOCK"
    assert queries.get_invalidation_policy_record_details(market_id=hard_market)["deployment_gate_effect"] == "HARD_BLOCK"


def test_invalidated_and_exit_recommended_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"exit-rec-{uuid4().hex[:8]}"
    _seed_policy_context(
        market_id=market_id,
        question="Will invalidated thesis recommend exit?",
        slug="exit-rec",
        hours_to_close=12,
        cognition_conclusion="CONTRADICTORY",
        cognition_confidence=0.18,
        cognition_caution=0.94,
        cognition_usability="DO_NOT_USE",
    )
    _update_invalidation_context(
        market_id=market_id,
        thesis_effect_class="breaks_thesis",
        invalidation_risk_score=0.97,
        confidence_degradation_score=0.96,
        contradiction_strength_score=0.93,
            advisory_action_class="PREPARE_INVALIDATION_REVIEW",
        cognition_usability="DO_NOT_USE",
        cognition_caution=0.96,
    )

    InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    record = InvalidationPolicyQueryService().get_invalidation_policy_record_details(market_id=market_id)
    assert record is not None
    assert record["invalidation_state_class"] == "INVALIDATED"
    assert record["exit_policy_class"] == "EXIT_RECOMMENDED"
    assert record["deployment_gate_effect"] == "HARD_BLOCK"


def test_sparse_context_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"sparse-policy-{uuid4().hex[:8]}"
    cycle_id = _seed_market_cycle(
        market_id=market_id,
        question="Will sparse policy context be handled honestly?",
        slug="sparse-policy",
        hours_to_close=30,
    )
    assert cycle_id is not None

    result = InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    assert result is not None
    record = InvalidationPolicyQueryService().get_invalidation_policy_record_details(market_id=market_id)
    assert record is not None
    assert record["invalidation_state_class"] == "WATCH"
    assert record["exit_policy_class"] == "BLOCK_NEW_DEPLOYMENT"
    assert "sparse_policy_context" in record["policy_reason_codes_json"]
    assert "block_new_deployment" in record["policy_reason_codes_json"]
    assert record["deployment_gate_effect"] == "HARD_BLOCK"


def test_prepare_invalidation_review_uses_real_upstream_enum_surface(postgres_test_schema) -> None:
    market_id = f"real-enum-{uuid4().hex[:8]}"
    _seed_policy_context(
        market_id=market_id,
        question="Will real advisory enums stay reachable?",
        slug="real-enum",
        hours_to_close=24,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.70,
        cognition_caution=0.50,
        cognition_usability="NEEDS_CONFIRMATION",
    )
    _update_invalidation_context(
        market_id=market_id,
        thesis_effect_class="warning",
        invalidation_risk_score=0.52,
        confidence_degradation_score=0.49,
        contradiction_strength_score=0.47,
        advisory_action_class="PREPARE_INVALIDATION_REVIEW",
    )

    result = InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    assert result is not None
    record = InvalidationPolicyQueryService().get_invalidation_policy_record_details(market_id=market_id)

    assert record is not None
    assert "invalidation_action_degrade" in record["policy_reason_codes_json"]
    assert "invalidation_action_escalated" not in record["policy_reason_codes_json"]


def test_blocked_ranking_signal_blocks_new_deployment_without_forcing_exit(postgres_test_schema) -> None:
    market_id = f"rank-block-{uuid4().hex[:8]}"
    _seed_policy_context(
        market_id=market_id,
        question="Will blocked ranking stay advisory but deployment-blocking?",
        slug="rank-block",
        hours_to_close=24,
        cognition_conclusion="WATCHFUL",
        cognition_confidence=0.76,
        cognition_caution=0.34,
        cognition_usability="USABLE_NOW",
    )
    _update_invalidation_context(
        market_id=market_id,
        thesis_effect_class="supports_thesis",
        invalidation_risk_score=0.12,
        confidence_degradation_score=0.10,
        contradiction_strength_score=0.10,
        advisory_action_class="NONE",
    )
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            UPDATE bucket_allocations
            SET deployability_class = 'DEPLOYABLE', deployment_fraction = 0.20
            WHERE market_id = %s
            """,
            (market_id,),
        )
        conn.execute(
            """
            UPDATE ranking_policy_candidates
            SET gate_decision_class = 'BLOCKED'
            WHERE market_id = %s
            """,
            (market_id,),
        )

    result = InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    assert result is not None
    record = InvalidationPolicyQueryService().get_invalidation_policy_record_details(market_id=market_id)

    assert record is not None
    assert record["invalidation_state_class"] == "THESIS_INTACT"
    assert record["exit_policy_class"] == "BLOCK_NEW_DEPLOYMENT"
    assert record["deployment_gate_effect"] == "SOFT_BLOCK"
    assert "block_new_deployment" in record["policy_reason_codes_json"]
    assert "exit_recommended" not in record["policy_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    market_id = f"query-policy-{uuid4().hex[:8]}"
    _seed_policy_context(
        market_id=market_id,
        question="Will query policy context stay coherent?",
        slug="query-policy",
        hours_to_close=22,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.81,
        cognition_caution=0.19,
        cognition_usability="USABLE_NOW",
    )
    result = InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    assert result is not None

    query = InvalidationPolicyQueryService()
    summary = query.get_invalidation_policy_run_summary(result.invalidation_policy_run_id)
    rows = query.list_invalidation_policy_records_for_run(result.invalidation_policy_run_id)
    details = query.get_invalidation_policy_record_details(market_id=market_id)
    comparison = query.compare_invalidation_policy_to_upstream_context(market_id)

    assert summary is not None
    assert summary["record_count"] == 1
    assert len(rows) == 1
    assert details is not None
    assert details["market_id"] == market_id
    assert comparison is not None
    assert comparison["invalidation_policy_record"] is not None
    assert comparison["cognition_summary"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    class DummyService:
        enabled = True

        def evaluate_markets(self, market_ids: list[str], *, source_type: str, source_ref: str | None):
            captured["market_ids"] = market_ids
            captured["source_type"] = source_type
            captured["source_ref"] = source_ref
            return InvalidationPolicyRunResult(
                invalidation_policy_run_id="phase8a-run",
                status="COMPLETED",
                input_count=len(market_ids),
                success_count=len(market_ids),
                failure_count=0,
            )

    monkeypatch.setattr("app.services.invalidation_exit_policy.InvalidationExitPolicyService", DummyService)
    exit_code = invalidation_exit_policy_main(["--market-ids", "mkt-a", "mkt-b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["market_ids"] == ["mkt-a", "mkt-b"]
    assert "invalidation_policy_run_id=phase8a-run" in output


def test_no_live_paper_or_shadow_execution_path_is_touched(postgres_test_schema) -> None:
    market_id = f"isolated-policy-{uuid4().hex[:8]}"
    _seed_policy_context(
        market_id=market_id,
        question="Will invalidation policy stay isolated?",
        slug="isolated-policy",
        hours_to_close=26,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.78,
        cognition_caution=0.24,
        cognition_usability="USABLE_NOW",
    )

    InvalidationExitPolicyService().evaluate_markets([market_id], source_type="phase8a_test")
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        signal_count = conn.execute("SELECT COUNT(*) AS count FROM paper_signals").fetchone()["count"]
        execution_count = conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]
        shadow_count = conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]

    assert signal_count == 0
    assert execution_count == 0
    assert shadow_count == 0
