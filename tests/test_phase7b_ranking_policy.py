from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.query.ranking_policy_query_service import RankingPolicyQueryService
from app.services.ranking_policy import (
    POLICY_VERSION,
    RankingPolicyRunResult,
    RankingPolicyService,
    main as ranking_policy_main,
)
from app.services.ranking_v2 import RankingV2Service
from test_phase7a_ranking_v2 import _seed_rankable_context


def _insert_ranking_candidate(
    *,
    market_id: str,
    total_rank_score: float,
    rank_position: int,
    rank_tier_class: str,
    rank_reason_codes: list[str] | None = None,
) -> tuple[str, str]:
    run_id = str(uuid4())
    candidate_id = str(uuid4())
    now = datetime.now(UTC)
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO ranking_v2_runs (
                id, source_type, source_ref, status, ranking_version,
                started_at, ended_at, input_count, success_count, failure_count, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                "phase7b_policy_seed",
                market_id,
                "COMPLETED",
                "phase7a-ranking-v2-foundation-v1",
                now,
                now,
                1,
                1,
                0,
                Jsonb({"seeded_for": "phase7b_policy_tests"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO ranking_v2_candidates (
                id, ranking_v2_run_id, market_id, cycle_id, market_snapshot_id,
                decision_id, cognition_summary_id, whale_market_score_id,
                trade_classification_id, bucket_allocation_id, total_rank_score,
                factor_scores_json, rank_position, rank_tier_class,
                rank_reason_codes_json, rank_reason_text, explanation_json, ranking_version
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                candidate_id,
                run_id,
                market_id,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                total_rank_score,
                Jsonb(
                    {
                        "market_quality_factor": 0.70,
                        "cognition_factor": 0.70,
                        "whale_factor": 0.40,
                        "trade_type_factor": 0.60,
                        "capital_deployability_factor": 0.70,
                        "time_pressure_factor": 0.80,
                        "risk_penalty": 0.20,
                    }
                ),
                rank_position,
                rank_tier_class,
                Jsonb(rank_reason_codes or []),
                f"Seeded {rank_tier_class.lower()} candidate for policy tests.",
                Jsonb({"seeded_for": "phase7b_policy_tests", "forced_reject": rank_tier_class == "REJECT"}),
                "phase7a-ranking-v2-foundation-v1",
            ),
        )
    return run_id, candidate_id


def _seed_policy_ready_market(
    *,
    market_id: str,
    question: str,
    slug: str,
    hours_to_close: int,
    cognition_conclusion: str | None = None,
    cognition_confidence: float = 0.0,
    cognition_caution: float = 0.0,
    cognition_usability: str = "DO_NOT_USE",
    whale_items: list | None = None,
) -> str:
    _seed_rankable_context(
        market_id=market_id,
        question=question,
        slug=slug,
        hours_to_close=hours_to_close,
        cognition_conclusion=cognition_conclusion,
        cognition_confidence=cognition_confidence,
        cognition_caution=cognition_caution,
        cognition_usability=cognition_usability,
        whale_items=whale_items,
    )
    result = RankingV2Service().rank_markets([market_id], source_type="phase7b_seed")
    assert result is not None
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT id FROM ranking_v2_candidates WHERE market_id = %s ORDER BY created_at DESC LIMIT 1",
            (market_id,),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def test_ranking_policy_migrations_create_tables(postgres_test_schema) -> None:
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
    assert {"ranking_policy_runs", "ranking_policy_candidates"} <= table_names


def test_successful_policy_run_persists_correctly(postgres_test_schema) -> None:
    market_id = f"policy-top-{uuid4().hex[:8]}"
    ranking_candidate_id = _seed_policy_ready_market(
        market_id=market_id,
        question="Will policy top market resolve well?",
        slug="policy-top",
        hours_to_close=24,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.83,
        cognition_caution=0.18,
        cognition_usability="USABLE_NOW",
    )

    result = RankingPolicyService().apply_policy_to_candidates([ranking_candidate_id], source_type="phase7b_test", source_ref="phase7b")
    assert result is not None
    assert result.status == "COMPLETED"
    assert result.success_count == 1

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        run_row = conn.execute("SELECT * FROM ranking_policy_runs WHERE id = %s LIMIT 1", (result.ranking_policy_run_id,)).fetchone()
        policy_row = conn.execute("SELECT * FROM ranking_policy_candidates WHERE ranking_policy_run_id = %s LIMIT 1", (result.ranking_policy_run_id,)).fetchone()

    assert run_row is not None
    assert run_row["policy_version"] == POLICY_VERSION
    assert policy_row is not None
    assert policy_row["market_id"] == market_id
    assert str(policy_row["ranking_v2_candidate_id"]) == ranking_candidate_id


def test_deterministic_gate_decision_behavior_works_as_expected(postgres_test_schema) -> None:
    top_market = f"policy-top-{uuid4().hex[:6]}"
    medium_market = f"policy-medium-{uuid4().hex[:6]}"
    reject_market = f"policy-reject-{uuid4().hex[:6]}"

    _, top_id = _insert_ranking_candidate(market_id=top_market, total_rank_score=82.0, rank_position=1, rank_tier_class="TOP")
    _, medium_id = _insert_ranking_candidate(market_id=medium_market, total_rank_score=49.0, rank_position=2, rank_tier_class="MEDIUM")
    _, reject_id = _insert_ranking_candidate(
        market_id=reject_market,
        total_rank_score=18.0,
        rank_position=3,
        rank_tier_class="REJECT",
        rank_reason_codes=["forced_reject_guardrail"],
    )

    RankingPolicyService().apply_policy_to_candidates([top_id, medium_id, reject_id], source_type="phase7b_test")
    queries = RankingPolicyQueryService()
    top = queries.get_ranking_policy_candidate_details(market_id=top_market)
    medium = queries.get_ranking_policy_candidate_details(market_id=medium_market)
    reject = queries.get_ranking_policy_candidate_details(market_id=reject_market)
    assert top is not None
    assert medium is not None
    assert reject is not None

    assert top["gate_decision_class"] == "SELECTABLE"
    assert medium["gate_decision_class"] == "REVIEW_ONLY"
    assert reject["gate_decision_class"] == "HARD_REJECT"


def test_top_high_medium_low_reject_map_correctly(postgres_test_schema) -> None:
    top_market = f"tier-top-{uuid4().hex[:6]}"
    high_market = f"tier-high-{uuid4().hex[:6]}"
    medium_market = f"tier-medium-{uuid4().hex[:6]}"
    low_market = f"tier-low-{uuid4().hex[:6]}"
    reject_market = f"tier-reject-{uuid4().hex[:6]}"

    _, top_id = _insert_ranking_candidate(market_id=top_market, total_rank_score=84.0, rank_position=1, rank_tier_class="TOP")
    _, high_id = _insert_ranking_candidate(market_id=high_market, total_rank_score=67.0, rank_position=2, rank_tier_class="HIGH")
    _, medium_id = _insert_ranking_candidate(market_id=medium_market, total_rank_score=50.0, rank_position=3, rank_tier_class="MEDIUM")
    _, low_id = _insert_ranking_candidate(market_id=low_market, total_rank_score=30.0, rank_position=4, rank_tier_class="LOW")
    _, reject_id = _insert_ranking_candidate(
        market_id=reject_market,
        total_rank_score=12.0,
        rank_position=5,
        rank_tier_class="REJECT",
        rank_reason_codes=["forced_reject_guardrail"],
    )

    RankingPolicyService().apply_policy_to_candidates([top_id, high_id, medium_id, low_id, reject_id], source_type="phase7b_test")
    queries = RankingPolicyQueryService()
    assert queries.get_ranking_policy_candidate_details(market_id=top_market)["gate_decision_class"] == "SELECTABLE"
    assert queries.get_ranking_policy_candidate_details(market_id=high_market)["gate_decision_class"] in {"SELECTABLE", "REVIEW_ONLY"}
    assert queries.get_ranking_policy_candidate_details(market_id=medium_market)["gate_decision_class"] == "REVIEW_ONLY"
    assert queries.get_ranking_policy_candidate_details(market_id=low_market)["gate_decision_class"] == "BLOCKED"
    assert queries.get_ranking_policy_candidate_details(market_id=reject_market)["gate_decision_class"] == "HARD_REJECT"


def test_max_selected_logic_works(postgres_test_schema) -> None:
    ids: list[str] = []
    markets: list[str] = []
    for idx in range(3):
        market_id = f"policy-max-{idx}-{uuid4().hex[:6]}"
        markets.append(market_id)
        _, candidate_id = _insert_ranking_candidate(
            market_id=market_id,
            total_rank_score=82.0 - (idx * 4.0),
            rank_position=idx + 1,
            rank_tier_class="TOP" if idx < 2 else "HIGH",
        )
        ids.append(candidate_id)

    RankingPolicyService().apply_policy_to_candidates(ids, source_type="phase7b_test")
    queries = RankingPolicyQueryService()
    rows = [queries.get_ranking_policy_candidate_details(market_id=market_id) for market_id in markets]
    selectable = [row for row in rows if row is not None and row["gate_decision_class"] == "SELECTABLE"]
    reserve = [row for row in rows if row is not None and row["gate_decision_class"] == "REVIEW_ONLY"]

    assert len(selectable) == 2
    assert len(reserve) >= 1


def test_hard_reject_handling_is_honest(postgres_test_schema) -> None:
    market_id = f"policy-hard-reject-{uuid4().hex[:6]}"
    candidate_id = _seed_policy_ready_market(
        market_id=market_id,
        question="Will hard reject market remain blocked?",
        slug="policy-hard-reject",
        hours_to_close=72,
        cognition_conclusion="CONTRADICTORY",
        cognition_confidence=0.38,
        cognition_caution=0.88,
        cognition_usability="DO_NOT_USE",
    )

    RankingPolicyService().apply_policy_to_candidates([candidate_id], source_type="phase7b_test")
    row = RankingPolicyQueryService().get_ranking_policy_candidate_details(market_id=market_id)
    assert row is not None
    assert row["gate_decision_class"] == "HARD_REJECT"
    assert row["gate_priority_class"] == "NONE"
    assert "hard_block_inherited_from_ranking" in row["selection_reason_codes_json"]


def test_query_layer_returns_coherent_results(postgres_test_schema) -> None:
    market_id = f"policy-query-{uuid4().hex[:6]}"
    ranking_run_id, _candidate_id = _insert_ranking_candidate(
        market_id=market_id,
        total_rank_score=80.0,
        rank_position=1,
        rank_tier_class="TOP",
    )

    result = RankingPolicyService().apply_policy_to_ranking_run(ranking_run_id)
    assert result is not None

    queries = RankingPolicyQueryService()
    summary = queries.get_ranking_policy_run_summary(result.ranking_policy_run_id)
    assert summary is not None
    assert summary["candidate_count"] == 1

    rows = queries.list_ranking_policy_candidates_for_run(result.ranking_policy_run_id)
    assert len(rows) == 1
    policy_id = str(rows[0]["id"])
    details = queries.get_ranking_policy_candidate_details(ranking_policy_candidate_id=policy_id)
    assert details is not None
    assert details["market_id"] == market_id

    selectable = queries.list_selectable_candidates(limit=200)
    assert any(str(row["market_id"]) == market_id for row in selectable)

    comparison = queries.compare_ranking_policy_to_ranking_v2(market_id)
    assert comparison is not None
    assert comparison["ranking_policy_candidate"] is not None
    assert comparison["ranking_v2_candidate"] is not None


def test_safe_entry_point_works(postgres_test_schema, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    run_migrations()
    called: dict[str, object] = {}

    class FakeRankingPolicyService:
        def apply_policy_to_candidates(self, ranking_v2_candidate_ids, *, source_type: str, source_ref: str | None = None, ranking_v2_run_id: str | None = None):  # noqa: ANN001
            called["ranking_v2_candidate_ids"] = ranking_v2_candidate_ids
            called["source_type"] = source_type
            called["source_ref"] = source_ref
            called["ranking_v2_run_id"] = ranking_v2_run_id
            return RankingPolicyRunResult(
                ranking_policy_run_id="ranking-policy-cli-test",
                status="COMPLETED",
                input_count=len(ranking_v2_candidate_ids),
                success_count=len(ranking_v2_candidate_ids),
                failure_count=0,
            )

        def apply_policy_to_ranking_run(self, ranking_v2_run_id: str, *, source_ref: str | None = None):  # noqa: ANN001
            called["ranking_v2_run_id"] = ranking_v2_run_id
            called["source_ref"] = source_ref
            return RankingPolicyRunResult(
                ranking_policy_run_id="ranking-policy-cli-test",
                status="COMPLETED",
                input_count=1,
                success_count=1,
                failure_count=0,
            )

    monkeypatch.setattr("app.services.ranking_policy.RankingPolicyService", FakeRankingPolicyService)

    exit_code = ranking_policy_main(["--ranking-v2-candidate-ids", "candidate-a", "--source-ref", "cli-test"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert called["ranking_v2_candidate_ids"] == ["candidate-a"]
    assert called["source_ref"] == "cli-test"
    assert "ranking-policy-cli-test" in output


def test_execution_paths_are_untouched(postgres_test_schema) -> None:
    market_id = f"policy-safe-{uuid4().hex[:6]}"
    candidate_id = _seed_policy_ready_market(
        market_id=market_id,
        question="Will policy stay isolated from execution?",
        slug="policy-safe",
        hours_to_close=36,
        cognition_conclusion="SUPPORTIVE",
        cognition_confidence=0.80,
        cognition_caution=0.19,
        cognition_usability="USABLE_NOW",
    )
    RankingPolicyService().apply_policy_to_candidates([candidate_id], source_type="phase7b_test")

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        live_orders = conn.execute("SELECT * FROM live_orders").fetchall()
        paper_orders = conn.execute("SELECT * FROM paper_orders").fetchall()
        shadow_orders = conn.execute("SELECT * FROM shadow_orders").fetchall()

    assert live_orders == []
    assert paper_orders == []
    assert shadow_orders == []
