from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.routes import create_router
from app.control_center.candidate_explanations import CandidateExplanationLedgerService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_blocked_candidate_returns_exact_blocker_stack(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("blocked-risk", blockers=["RISK_BLOCKED", "RISK_NOT_APPROVED", "EXIT_NOT_READY"], risk_approved=False, exit_ready=False)

    item = _first_item()

    assert item["explanation_state"] == "EXPLAINED_BLOCKED"
    assert item["final_outcome"] == "BLOCKED"
    assert {"RISK_BLOCKED", "RISK_NOT_APPROVED", "EXIT_NOT_READY"} <= set(item["blockers"])
    assert item["blocker_stack"][0]["required_to_clear"]


def test_missing_market_id_is_hard_missing_data_block(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("missing-market", market_id=None, blockers=["MISSING_MARKET_ID"])

    item = _first_item()

    assert "MISSING_MARKET_ID" in item["blockers"]
    assert item["final_blocker"] == "MISSING_MARKET_ID"
    assert "market_id" in item["missing_data"]


def test_missing_side_is_hard_missing_data_block(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("missing-side", side=None, blockers=["MISSING_SIDE"])

    item = _first_item()

    assert "MISSING_SIDE" in item["blockers"]
    assert item["final_blocker"] == "MISSING_SIDE"
    assert "side" in item["missing_data"]


def test_stale_orderbook_is_exposed(postgres_test_schema) -> None:
    _prepare(orderbook_age=timedelta(minutes=20))
    _seed_candidate("stale-book", status="ELIGIBLE")

    item = _first_item()

    assert "STALE_ORDERBOOK" in item["blockers"]
    assert "orderbook" in item["stale_data"]


def test_risk_blocked_candidate_exposes_risk_blockers(postgres_test_schema) -> None:
    _prepare(risk_approved=False)
    _seed_candidate("risk-blocked", blockers=["RISK_BLOCKED", "RISK_NOT_APPROVED"], risk_approved=False)

    item = _first_item()

    assert item["results"]["risk_result"] == "BLOCKED"
    assert "RISK_BLOCKED" in item["blockers"]
    assert "RISK_NOT_APPROVED" in item["blockers"]


def test_exit_not_ready_candidate_exposes_exit_blocker(postgres_test_schema) -> None:
    _prepare(exit_ready=False)
    _seed_candidate("exit-blocked", blockers=["EXIT_NOT_READY"], exit_ready=False)

    item = _first_item()

    assert item["results"]["exit_result"] == "NOT_READY"
    assert "EXIT_NOT_READY" in item["blockers"]


def test_thesis_incomplete_candidate_exposes_thesis_blocker(postgres_test_schema) -> None:
    _prepare(thesis_status="INCOMPLETE")
    _seed_candidate("thesis-blocked", blockers=["THESIS_NOT_COMPLETE"])

    item = _first_item()

    assert item["results"]["thesis_result"] == "INCOMPLETE"
    assert "THESIS_NOT_COMPLETE" in item["blockers"]


def test_governance_denied_candidate_exposes_lifecycle_blocker(postgres_test_schema) -> None:
    _prepare(governance_allowed=False)
    _seed_candidate("governance-blocked", status="ELIGIBLE")

    item = _first_item()

    assert item["results"]["governance_result"] == "DENIED"
    assert "LIFECYCLE_GOVERNANCE_DENIED" in item["blockers"]


def test_eligible_candidate_without_intent_is_not_success(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("eligible-no-intent", status="ELIGIBLE")

    item = _first_item()

    assert item["final_outcome"] == "READY_FOR_INTENT"
    assert item["explanation_state"] == "EXPLAINED_READY_FOR_INTENT"
    assert "NO_PAPER_INTENT" in item["blockers"]


def test_eligible_candidate_without_intent_appears_in_gap(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("eligible-gap", status="ELIGIBLE")

    payload = _service().list_explanations()

    assert payload["eligible_intent_gap"]["eligible_candidates"] == 1
    assert payload["eligible_intent_gap"]["eligible_without_intent"] == 1
    assert payload["eligible_intent_gap"]["top_reasons"][0]["reason"] == "NO_PAPER_INTENT"


def test_existing_intent_is_linked(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("with-intent", status="ELIGIBLE")
    _seed_intent("with-intent")

    item = _service().get_explanation("with-intent")["candidate"]

    assert item["final_outcome"] == "INTENT_CREATED"
    assert item["results"]["intent_result"] == "CREATED"
    assert item["evidence"]["intent"]["eligibility_id"] == "with-intent"


def test_missing_evidence_is_reported_as_explanation_incomplete(postgres_test_schema) -> None:
    _prepare(skip_sources=True)
    _seed_candidate("missing-sources", status="ELIGIBLE", thesis_id="missing-thesis", risk_decision_id="missing-risk", exit_plan_id="missing-exit")

    item = _first_item()

    assert "EXPLANATION_INCOMPLETE" in item["blockers"]
    assert {"risk_decision", "exit_plan", "thesis", "lifecycle_governance"} <= set(item["missing_data"])


def test_required_to_pass_is_populated_for_every_hard_blocker(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("required", blockers=["RISK_BLOCKED", "EXIT_NOT_READY", "MISSING_MARKET_ID"], risk_approved=False, exit_ready=False, market_id=None)

    item = _first_item()
    hard_blockers = [entry for entry in item["blocker_stack"] if entry["severity"] in {"HARD_BLOCK", "MISSING_DATA", "GOVERNANCE_DENIED"}]

    assert hard_blockers
    assert all(entry["required_to_clear"] for entry in hard_blockers)
    assert item["required_to_pass"]


def test_endpoint_is_read_only_and_creates_no_paper_artifacts(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("readonly", status="ELIGIBLE")
    before = _paper_artifact_counts()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/candidate-explanations")

    assert response.status_code == 200
    assert _paper_artifact_counts() == before


def test_response_includes_required_truth_fields(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("shape", status="ELIGIBLE")

    payload = _service().list_explanations()

    for key in ("source", "last_updated", "freshness_state", "readiness_state", "truth_state", "counts", "top_blockers", "items", "warnings", "errors"):
        assert key in payload
    assert payload["items"][0]["candidate_id"] == "shape"


def _service() -> CandidateExplanationLedgerService:
    return CandidateExplanationLedgerService(connection_factory=DatabaseConnectionFactory())


def _first_item() -> dict:
    payload = _service().list_explanations(limit=1)
    assert payload["items"]
    return payload["items"][0]


def _prepare(
    *,
    orderbook_age: timedelta = timedelta(seconds=5),
    risk_approved: bool = True,
    exit_ready: bool = True,
    thesis_status: str = "COMPLETE",
    governance_allowed: bool = True,
    skip_sources: bool = False,
) -> None:
    run_migrations()
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "lifecycle_governance_sources",
            "lifecycle_governance_decisions",
            "no_trade_log",
            "paper_intents",
            "paper_eligibility_candidates",
            "exit_plans",
            "risk_decisions",
            "thesis_profile_evidence_items",
            "thesis_profiles",
            "neuron_signal_bindings",
            "orderbook_snapshots",
            "market_snapshots_v2",
            "markets_v2",
            "paper_fills",
            "paper_positions",
            "paper_orders",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        if skip_sources:
            return
        snapshot_at = now - orderbook_age
        orderbook_id = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('book-candidate', 'candidate-market', 'YES', 0.50, 0.52,
                0.02, 0.51, 0.8, 'test', 'OK', false, %s, %s, %s)
            RETURNING id
            """,
            (snapshot_at, snapshot_at, now),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, active, closed, archived, last_seen_at, updated_at)
            VALUES ('candidate-market', 'Candidate test market?', true, false, false, %s, %s)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (
                snapshot_id, market_id, current_price_yes, current_price_no,
                best_bid, best_ask, spread, liquidity, data_completeness_score, stale, snapshot_at
            )
            VALUES ('candidate-market-snapshot', 'candidate-market', 0.52, 0.48, 0.50, 0.52, 0.02, 100, 1, false, %s)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now, confidence,
                evidence, missing_evidence, invalidation_rules, risk_notes,
                orderbook_snapshot_id, created_at, updated_at
            )
            VALUES ('thesis-candidate', 'candidate-market', 'YES', %s, 'RUNTIME_COORDINATOR_THESIS',
                'test thesis', 0.9, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, %s, %s, %s)
            """,
            (thesis_status, orderbook_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status,
                risk_score, confidence, risk_approved, blockers, created_at, updated_at
            )
            VALUES ('risk-candidate', 'thesis-candidate', 'candidate-market', %s, %s,
                0.1, 0.9, %s, %s, %s, %s)
            """,
            (
                "APPROVE" if risk_approved else "BLOCK",
                "LOW" if risk_approved else "BLOCKED",
                risk_approved,
                Jsonb([] if risk_approved else ["RISK_BLOCKED"]),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, engine, entry_price, entry_size,
                exit_mode, plan_status, status, exit_type, thesis_id, risk_decision_ref,
                paper_exit_ready, blockers, created_at, updated_at
            )
            VALUES ('exit-candidate', 'candidate-market', 'YES', 'EXIT_FOUNDATION', 0.52, 10,
                'PAPER_SIM_EXIT', %s, %s, 'BASIC_PROTECTIVE_EXIT', 'thesis-candidate', 'risk-candidate',
                %s, %s, %s, %s)
            """,
            (
                "ACTIVE" if exit_ready else "INSUFFICIENT_DATA",
                "COMPLETE" if exit_ready else "BLOCKED",
                exit_ready,
                Jsonb([] if exit_ready else ["EXIT_NOT_READY"]),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO lifecycle_governance_decisions (
                decision_id, subject_type, subject_id, market_id, side,
                actionability_class, allow_paper_intent, allow_paper_execution,
                critical_blockers_json, reason, created_at
            )
            VALUES ('governance-candidate', 'PAPER_CANDIDATE', 'candidate-default',
                'candidate-market', 'YES', %s, %s, %s, %s, 'test governance', %s)
            """,
            (
                "ACTIONABLE_SMALL_PAPER" if governance_allowed else "HARD_BLOCK",
                governance_allowed,
                governance_allowed,
                Jsonb([] if governance_allowed else ["LIFECYCLE_GOVERNANCE_DENIED"]),
                now,
            ),
        )


def _seed_candidate(
    eligibility_id: str,
    *,
    status: str = "BLOCKED",
    blockers: list[str] | None = None,
    missing: list[str] | None = None,
    market_id: str | None = "candidate-market",
    side: str | None = "YES",
    risk_approved: bool = True,
    exit_ready: bool = True,
    thesis_id: str | None = "thesis-candidate",
    risk_decision_id: str | None = "risk-candidate",
    exit_plan_id: str | None = "exit-candidate",
) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        orderbook_id = conn.execute("SELECT id FROM orderbook_snapshots LIMIT 1").fetchone()
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                brain_output_ids, signal_ids, market_id, side, status,
                eligibility_score, eligibility_blockers, missing_requirements,
                evidence, orderbook_snapshot_id, link_confidence, lineage_trusted,
                risk_approved, exit_ready, not_dry_run, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, '[]'::jsonb, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, 1, true, %s, %s, true, %s, %s)
            """,
            (
                eligibility_id,
                thesis_id,
                risk_decision_id,
                exit_plan_id,
                Jsonb([]),
                market_id,
                side,
                status,
                1 if status == "ELIGIBLE" else 0,
                Jsonb(blockers or []),
                Jsonb(missing or blockers or []),
                Jsonb({"orderbook_best_ask": 0.52, "orderbook_mid_price": 0.51}),
                orderbook_id["id"] if orderbook_id else None,
                risk_approved,
                exit_ready,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO no_trade_log (
                no_trade_id, market_id, side, source_layer, decision_status,
                primary_reason, reasons_json, created_at, eligibility_id,
                thesis_id, risk_decision_id, exit_plan_id, no_trade_reason,
                no_trade_category, blockers, missing_requirements, evidence,
                source_status, explanation, updated_at
            )
            VALUES (%s, %s, %s, 'paper_intent_gate', 'NO_TRADE',
                %s, %s, %s, %s, %s, %s, %s, %s, 'ELIGIBILITY_BLOCKED',
                %s, %s, '{}'::jsonb, %s, %s, %s)
            """,
            (
                f"no_trade_{eligibility_id}",
                market_id,
                side,
                (blockers or ["NO_PAPER_INTENT"])[0],
                Jsonb(blockers or ["NO_PAPER_INTENT"]),
                now,
                eligibility_id,
                thesis_id,
                risk_decision_id,
                exit_plan_id,
                (blockers or ["NO_PAPER_INTENT"])[0],
                Jsonb(blockers or []),
                Jsonb(missing or blockers or []),
                status,
                f"Candidate {eligibility_id} blocked for test explanation.",
                now,
            ),
        )
        governance = conn.execute("SELECT * FROM lifecycle_governance_decisions ORDER BY created_at DESC LIMIT 1").fetchone()
        if governance:
            conn.execute(
                """
                INSERT INTO lifecycle_governance_decisions (
                    decision_id, subject_type, subject_id, market_id, side,
                    actionability_class, allow_paper_intent, allow_paper_execution,
                    critical_blockers_json, reason, created_at
                )
                VALUES (%s, 'PAPER_CANDIDATE', %s, %s, %s, %s, %s, %s, %s, 'test governance', %s)
                ON CONFLICT (decision_id) DO NOTHING
                """,
                (
                    f"governance_{eligibility_id}",
                    eligibility_id,
                    market_id,
                    side,
                    governance["actionability_class"],
                    governance["allow_paper_intent"],
                    governance["allow_paper_execution"],
                    Jsonb(governance["critical_blockers_json"]),
                    now,
                ),
            )


def _seed_intent(eligibility_id: str) -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        orderbook_id = conn.execute("SELECT id FROM orderbook_snapshots LIMIT 1").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, orderbook_snapshot_id,
                intended_price, max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live, execution_allowed,
                order_intent_created, generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (%s, %s, 'thesis-candidate', 'risk-candidate', 'exit-candidate',
                'candidate-market', 'YES', 'ORDERBOOK_LIMIT', %s, 0.52, 0.02, 0.9,
                'CREATED', 'PAPER_ENTRY_INTENT', 'test intent', %s, '[]'::jsonb,
                true, false, false, false, 'test', 'paper_intent_gate', true, false, %s, %s)
            """,
            (f"paper_intent_{eligibility_id}", eligibility_id, orderbook_id, Jsonb({"quantity": 1}), now, now),
        )


def _paper_artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: _count_table(conn, table)
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions")
        }


def _count_table(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}
