from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.main import app
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.paper_execution import PaperExecutionService
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate
from test_paper_execution_service import _Governor, _Power, _prepare as prepare_execution_schema, _seed_intent


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "truth_state_decision_links",
            "truth_state_transitions",
            "truth_state_registry",
            "risk_evidence_mesh_sources",
            "risk_evidence_mesh_evaluations",
            "freshness_governance_checks",
            "governance_blocker_calibration_traces",
            "governance_blocker_calibration_runs",
            "same_market_side_guard_decisions",
            "lifecycle_governance_sources",
            "lifecycle_governance_decisions",
            "trade_lifecycle_brain_contributions",
            "trade_lifecycle_plan_sources",
            "trade_lifecycle_plans",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_position_closes",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_intents",
            "paper_eligibility_candidates",
            "orderbook_snapshots",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def test_critical_blocker_creates_hard_block(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(missing=["RISK_BLOCKED"])

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="PAPER_INTENT")

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert decision["allow_paper_intent"] is False
    assert "RISK_BLOCKED" in decision["critical_blockers_json"]


def test_optional_missing_only_is_watch_not_hard_block(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(missing=["MEMORY_CONTEXT_MISSING", "WHALE_CONTEXT_MISSING"])

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "WATCH_FOR_CONFIRMATION"
    assert decision["critical_blockers_json"] == []
    assert set(decision["optional_missing_json"]) == {"MEMORY_CONTEXT_MISSING", "WHALE_CONTEXT_MISSING"}


def test_context_dependent_missing_classified_without_fake_time(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(missing=["TIME_TO_RESOLUTION_MISSING", "RULES_RISK_UNKNOWN"])

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "WATCH_FOR_CONFIRMATION"
    assert set(decision["context_dependent_missing_json"]) == {"TIME_TO_RESOLUTION_MISSING", "RULES_RISK_UNKNOWN"}


def test_stale_lifecycle_plan_blocks_paper_intent(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(created_at=datetime.now(UTC) - timedelta(minutes=30))

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(
            conn,
            dict(plan),
            request_action="PAPER_INTENT",
            metadata={
                "same_market_guard_decision": {"decision": "ALLOW"},
                "risk_approved": True,
                "exit_ready": True,
                "lineage_trusted": True,
                "not_dry_run": True,
            },
        )

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert decision["allow_paper_intent"] is False
    assert "STALE_LIFECYCLE_PLAN" in decision["critical_blockers_json"]


def test_stale_orderbook_source_blocks_paper_authorization(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('stale-book-governance','governance-market','YES',0.5,0.55,0.05,0.525,0.8,'test','OK',false,%s,%s,%s)
            RETURNING orderbook_snapshot_id
            """,
            (
                datetime.now(UTC) - timedelta(minutes=20),
                datetime.now(UTC) - timedelta(minutes=20),
                datetime.now(UTC) - timedelta(minutes=20),
            ),
        ).fetchone()
    plan_id = _seed_plan(source_refs={"orderbook_snapshot_id": row["orderbook_snapshot_id"]})

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(
            conn,
            dict(plan),
            request_action="PAPER_EXECUTION",
            metadata={"same_market_guard_decision": {"decision": "ALLOW"}},
        )

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "STALE_ORDERBOOK" in decision["critical_blockers_json"]
    assert "REFRESH_REQUIRED_BEFORE_EXECUTION" in decision["critical_blockers_json"]


def test_missing_lifecycle_plan_blocks_paper_intent_authorization(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        decision = LifecycleGovernanceGateService().evaluate_subject_with_conn(
            conn,
            subject_type="PAPER_CANDIDATE",
            subject_id="missing-candidate",
            request_action="PAPER_INTENT",
            allow_build=False,
        )

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert decision["allow_paper_intent"] is False
    assert "LIFECYCLE_PLAN_MISSING" in decision["critical_blockers_json"]


def test_actionable_small_paper_allowed_when_critical_clear_and_guard_allows(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(subject_type="PAPER_CANDIDATE", subject_id="candidate-actionable", missing=["MEMORY_CONTEXT_MISSING"])

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(
            conn,
            dict(plan),
            request_action="PAPER_INTENT",
            metadata={
                "same_market_guard_decision": {"decision": "ALLOW", "decision_id": "guard-ok", "created_at": datetime.now(UTC).isoformat()},
                "risk_approved": True,
                "exit_ready": True,
                "lineage_trusted": True,
                "not_dry_run": True,
            },
        )

    assert decision["actionability_class"] == "ACTIONABLE_SMALL_PAPER"
    assert decision["allow_paper_intent"] is True


def test_stale_same_market_guard_does_not_become_current_opposing_block(postgres_test_schema) -> None:
    _prepare()
    stale_at = datetime.now(UTC) - timedelta(hours=12)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO same_market_side_guard_decisions (
                decision_id, market_id, proposed_side, existing_exposure_json,
                existing_open_positions_count, existing_opposite_positions_count,
                existing_same_side_positions_count, existing_opposite_intents_count,
                existing_same_side_intents_count, recent_opposite_closes_count,
                batch_opposite_candidates_count, source_backed, decision, blocker_reason,
                dry_run, metadata_json, created_at
            )
            VALUES (
                'stale-same-market-guard', 'stale-market', 'YES', '{}'::jsonb,
                0,0,0,1,0,0,0,false,'BLOCK','SAME_MARKET_OPPOSING_SIDE_BLOCK',
                false, '{}'::jsonb, %s
            )
            """,
            (stale_at,),
        )
    plan_id = _seed_plan(
        market_id="stale-market",
        strategy_type="SAME_MARKET_BLOCKED",
        plan_status="BLOCKED",
        decision_class="BLOCKED",
        source_refs={"same_market_guard_decision_id": "stale-same-market-guard"},
        created_at=datetime.now(UTC),
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = dict(conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone())
        plan["same_market_summary_json"] = {
            "decision_id": "stale-same-market-guard",
            "decision": "BLOCK",
            "blocker_reason": "SAME_MARKET_OPPOSING_SIDE_BLOCK",
        }
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, plan, request_action="PAPER_INTENT")

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "STALE_SAME_MARKET_GUARD" in decision["critical_blockers_json"]
    assert "SAME_MARKET_OPPOSING_SIDE_BLOCK" not in decision["critical_blockers_json"]
    assert decision["metadata_json"]["truth_state"]["same_market_guard"]["decision_permission"] == "MUST_REFRESH"


def test_paper_intent_creation_blocked_if_governance_denies(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("governance-deny")
    with DatabaseConnectionFactory().connect() as conn:
        candidate = dict(conn.execute("SELECT * FROM paper_eligibility_candidates ORDER BY created_at DESC,id DESC LIMIT 1").fetchone())
    _seed_plan(
        subject_type="PAPER_CANDIDATE",
        subject_id=candidate["eligibility_id"],
        market_id=candidate["market_id"],
        side="YES",
        strategy_type="RISK_BLOCKED",
        plan_status="BLOCKED",
        decision_class="BLOCKED",
        missing=[],
    )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    assert result["no_trade_records_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM no_trade_log WHERE eligibility_id=%s", (candidate["eligibility_id"],)).fetchone()
    assert "LIFECYCLE_GOVERNANCE_DENIED" in row["blockers"]
    assert "RISK_BLOCKED" in row["blockers"]


def test_paper_execution_blocks_intent_with_insufficient_lifecycle_data(postgres_test_schema) -> None:
    prepare_execution_schema()
    intent_id = _seed_intent()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM trade_lifecycle_plans WHERE subject_type='PAPER_INTENT' AND subject_id=%s", (intent_id,))

    result = PaperExecutionService(system_power=_Power(True), governor=_Governor(True)).run_execution(correlation_id="governance-block")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["LIFECYCLE_GOVERNANCE_DENIED"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "paper_positions") == 0


def test_dashboard_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()
    _seed_plan(missing=["MEMORY_CONTEXT_MISSING"])
    LifecycleGovernanceGateService().evaluate_recent(limit=10)

    payload = TestClient(app).get("/dashboard/api/v2/lifecycle-governance").json()

    assert payload["mock_data"] is False
    assert payload["total_decisions"] == 1
    assert payload["security_governance_status"] == "YELLOW_ACCEPTED_BY_OPERATOR"


def test_fresh_risk_review_ignores_stale_legacy_risk_blockers(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(
        missing=["RISK_BLOCKED", "RISK_BLOCKED_NO_EDGE", "RISK_BLOCKED_LINEAGE", "STALE_RISK_DECISION", "MEMORY_CONTEXT_MISSING"],
        plan_status="BLOCKED",
        decision_class="BLOCKED",
        strategy_type="RISK_BLOCKED",
    )
    _seed_risk_evidence(
        subject_type="LIFECYCLE_PLAN",
        subject_id=plan_id,
        risk_decision="RISK_REVIEW",
        risk_blocker_subtype="RISK_REVIEW_EDGE_WEAK",
        edge_source_type="PRICE_PAYOUT_ASYMMETRY",
        edge_status="SOURCE_BACKED_EDGE_PRESENT",
        optional=["FAIR_PROBABILITY_MISSING", "MEMORY_CONTEXT_MISSING", "WHALE_CONTEXT_MISSING"],
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "WATCH_FOR_CONFIRMATION"
    assert not set(decision["critical_blockers_json"]) & {"RISK_BLOCKED", "RISK_BLOCKED_NO_EDGE", "RISK_BLOCKED_LINEAGE", "STALE_RISK_DECISION"}
    trace = decision["metadata_json"]["risk_source_trace"]
    assert trace["selected_risk_source"] == "RISK_EVIDENCE_MESH"
    assert trace["legacy_ignored"] is True
    assert "STALE_RISK_DECISION" in trace["ignored_legacy_risk_sources"]


def test_stale_risk_evidence_does_not_override_legacy_risk_source(postgres_test_schema) -> None:
    _prepare()
    stale_at = datetime.now(UTC) - timedelta(minutes=30)
    plan_id = _seed_plan(missing=["RISK_BLOCKED"], plan_status="BLOCKED", decision_class="BLOCKED", strategy_type="RISK_BLOCKED")
    _seed_risk_evidence(
        subject_type="LIFECYCLE_PLAN",
        subject_id=plan_id,
        risk_decision="RISK_REVIEW",
        risk_blocker_subtype="RISK_REVIEW_EDGE_WEAK",
        edge_source_type="PRICE_PAYOUT_ASYMMETRY",
        edge_status="SOURCE_BACKED_EDGE_PRESENT",
        created_at=stale_at,
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "STALE_RISK_SOURCE_REFRESH_REQUIRED" in decision["critical_blockers_json"]
    trace = decision["metadata_json"]["risk_source_trace"]
    assert trace["selected_risk_source"] == "LAST_KNOWN_RISK_CONTEXT"
    assert trace["selected_risk_source_freshness"] == "LAST_KNOWN"
    assert trace["legacy_ignored"] is False


def test_fresh_risk_review_keeps_non_risk_critical_blockers(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(
        missing=["STALE_RISK_DECISION", "STALE_EXIT_PLAN"],
        plan_status="BLOCKED",
        decision_class="BLOCKED",
    )
    _seed_risk_evidence(
        subject_type="LIFECYCLE_PLAN",
        subject_id=plan_id,
        risk_decision="RISK_REVIEW",
        risk_blocker_subtype="RISK_REVIEW_EDGE_WEAK",
        edge_source_type="NEWS_REPRICING_SIGNAL",
        edge_status="EDGE_WEAK",
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "STALE_EXIT_PLAN" in decision["critical_blockers_json"]
    assert "STALE_RISK_DECISION" not in decision["critical_blockers_json"]


def test_fresh_risk_block_remains_hard_block(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(missing=[])
    _seed_risk_evidence(
        subject_type="LIFECYCLE_PLAN",
        subject_id=plan_id,
        risk_decision="RISK_BLOCK",
        risk_blocker_subtype="RISK_BLOCKED_STALE_CRITICAL_SOURCE",
        edge_source_type="UNKNOWN",
        edge_status="EDGE_NOT_EVALUATED",
        critical_missing=["TRUSTED_ORDERBOOK_STALE"],
        blocking=["RISK_BLOCKED_STALE_CRITICAL_SOURCE"],
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        decision = LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "RISK_BLOCKED" in decision["critical_blockers_json"]
    assert "RISK_BLOCKED_STALE_CRITICAL_SOURCE" in decision["critical_blockers_json"]


def test_dashboard_exposes_risk_evidence_integration_counts(postgres_test_schema) -> None:
    _prepare()
    plan_id = _seed_plan(missing=["STALE_RISK_DECISION"])
    _seed_risk_evidence(subject_type="LIFECYCLE_PLAN", subject_id=plan_id)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        plan = conn.execute("SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,)).fetchone()
        LifecycleGovernanceGateService().evaluate_plan_with_conn(conn, dict(plan), request_action="OBSERVE")

    payload = TestClient(app).get("/dashboard/api/v2/lifecycle-governance").json()

    assert payload["mock_data"] is False
    assert payload["risk_evidence_used_count"] == 1
    assert payload["legacy_risk_ignored_count"] == 1
    assert payload["stale_legacy_risk_block_ignored_count"] == 1
    assert payload["risk_review_promoted_to_watch_count"] == 1
    assert payload["risk_source_selection_summary"][0]["selected_risk_source"] == "RISK_EVIDENCE_MESH"


def test_governance_service_does_not_create_trading_artifacts(postgres_test_schema) -> None:
    _prepare()
    _seed_plan(missing=["MEMORY_CONTEXT_MISSING"])
    before = _safety_counts()

    LifecycleGovernanceGateService().evaluate_recent(limit=10)

    after = _safety_counts()
    assert before == after


def _seed_plan(
    *,
    subject_type: str = "PAPER_CANDIDATE",
    subject_id: str | None = None,
    market_id: str = "governance-market",
    side: str = "YES",
    strategy_type: str = "WATCH_ONLY",
    plan_status: str = "PARTIAL",
    decision_class: str = "PAPER_CANDIDATE_REVIEW",
    missing: list[str] | None = None,
    source_refs: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> str:
    subject_id = subject_id or f"subject-{uuid4().hex}"
    plan_id = f"trade-lifecycle-governance-test-{uuid4().hex}"
    created_at = created_at or datetime.now(UTC) - timedelta(seconds=1)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO trade_lifecycle_plans (
                plan_id, subject_type, subject_id, market_id, condition_id, side, token_id, mesh_session_id,
                strategy_type, plan_status, decision_class, economic_thesis, entry_thesis, exit_thesis,
                hold_to_resolution_thesis, invalidation_rules_json, capital_plan_json, monitoring_plan_json,
                risk_summary_json, liquidity_summary_json, payout_summary_json, exit_hold_summary_json,
                capital_efficiency_summary_json, same_market_summary_json, coordinator_judgment_json,
                missing_inputs_json, source_refs_json, metadata_json, created_at, updated_at
            )
            VALUES (
                %s,%s,%s,%s,'condition-governance',%s,'token-governance',NULL,
                %s,%s,%s,'source-backed economic thesis','source-backed entry thesis','source-backed exit thesis',
                'source-backed hold thesis','[]'::jsonb,'{}'::jsonb,'[]'::jsonb,
                '{"decision":"APPROVE"}'::jsonb,'{"status":"OK"}'::jsonb,'{"evaluation_id":"payout-governance"}'::jsonb,
                '{"decision":"WAIT"}'::jsonb,'{"recommendation":"CAPITAL_WATCH"}'::jsonb,
                '{"decision":"ALLOW"}'::jsonb,'{"final_action":"PAPER_CANDIDATE_REVIEW"}'::jsonb,
                %s::jsonb,%s::jsonb,'{"test_fixture":true}'::jsonb, %s, %s
            )
            """,
            (
                plan_id,
                subject_type,
                subject_id,
                market_id,
                side,
                strategy_type,
                plan_status,
                decision_class,
                Jsonb(missing or []),
                Jsonb(source_refs or {}),
                created_at,
                created_at,
            ),
        )
    return plan_id


def _seed_risk_evidence(
    *,
    subject_type: str,
    subject_id: str,
    risk_decision: str = "RISK_REVIEW",
    risk_blocker_subtype: str = "RISK_REVIEW_EDGE_WEAK",
    edge_source_type: str = "PRICE_PAYOUT_ASYMMETRY",
    edge_status: str = "SOURCE_BACKED_EDGE_PRESENT",
    critical_missing: list[str] | None = None,
    optional: list[str] | None = None,
    blocking: list[str] | None = None,
    created_at: datetime | None = None,
) -> str:
    evaluation_id = f"risk-evidence-governance-test-{uuid4().hex}"
    created_at = created_at or datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO risk_evidence_mesh_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                critical_evidence_present_json, critical_evidence_missing_json, supporting_evidence_present_json,
                optional_context_missing_json, blocking_evidence_json, evidence_quality_score,
                edge_source_type, edge_status, risk_decision, risk_blocker_subtype, reason,
                source_refs_json, metadata_json, created_at, updated_at
            )
            VALUES (
                %s,%s,%s,'governance-market','condition-governance','YES','token-governance',
                '["ACTIVE_FRESH_TRUSTED_ORDERBOOK","EXECUTABLE_PRICE"]'::jsonb,%s::jsonb,
                '["PAYOUT_ODDS","CAPITAL_EFFICIENCY"]'::jsonb,%s::jsonb,%s::jsonb,0.91,
                %s,%s,%s,%s,'test risk evidence',
                '{}'::jsonb,'{"no_fake_edge":true,"no_fake_probability":true}'::jsonb,%s,%s
            )
            """,
            (
                evaluation_id,
                subject_type,
                subject_id,
                Jsonb(critical_missing or []),
                Jsonb(optional or ["FAIR_PROBABILITY_MISSING"]),
                Jsonb(blocking or []),
                edge_source_type,
                edge_status,
                risk_decision,
                risk_blocker_subtype,
                created_at,
                created_at,
            ),
        )
    return evaluation_id


def _safety_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count(conn, table)
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")
        }


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
