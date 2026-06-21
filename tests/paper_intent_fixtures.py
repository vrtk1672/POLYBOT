from __future__ import annotations

import json

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_eligibility import PaperEligibilityService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain, table_exists


def prepare_paper_intent_schema() -> None:
    prepare_paper_eligibility_schema()
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("paper_intent_runs", "no_trade_runs", "paper_intents", "no_trade_log"):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def seed_eligible_candidate(suffix: str = "eligible") -> dict[str, str | None]:
    ids = seed_paper_eligibility_chain(suffix)
    PaperEligibilityService().evaluate_candidates(limit=10)
    return ids


def seed_blocked_candidate(
    suffix: str = "blocked",
    *,
    status: str = "BLOCKED",
    thesis_id: str | None = "thesis-blocked",
    risk_decision_id: str | None = "risk-blocked",
    exit_plan_id: str | None = "exit-blocked",
    market_id: str | None = "market-blocked",
    side: str | None = "YES",
    orderbook_snapshot_id: int | None = 1,
    risk_approved: bool = False,
    exit_ready: bool = False,
    lineage_trusted: bool = False,
    not_dry_run: bool = True,
    is_dry_run_generated: bool = False,
    blockers: list[str] | None = None,
    missing: list[str] | None = None,
) -> str:
    eligibility_id = f"eligibility-{suffix}"
    blockers = blockers if blockers is not None else ["RISK_NOT_APPROVED"]
    missing = missing if missing is not None else ["RISK_NOT_APPROVED"]
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                coordinator_decision_id, brain_output_ids, signal_ids, market_id,
                side, status, eligibility_score, eligibility_blockers,
                missing_requirements, evidence, orderbook_snapshot_id,
                link_confidence, lineage_trusted, risk_approved, exit_ready,
                not_dry_run, paper_intent_allowed, execution_allowed,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, 'coord-blocked', %s::jsonb, %s::jsonb,
                %s, %s, %s, 0, %s::jsonb, %s::jsonb, '{}'::jsonb,
                %s, 0.9, %s, %s, %s, %s, false, false,
                'runtime', 'paper_eligibility_gate', true, %s, now(), now()
            )
            """,
            (
                eligibility_id,
                thesis_id,
                risk_decision_id,
                exit_plan_id,
                json.dumps(["brain-blocked"]),
                json.dumps(["signal-blocked"]),
                market_id,
                side,
                status,
                json.dumps(blockers),
                json.dumps(missing),
                orderbook_snapshot_id,
                lineage_trusted,
                risk_approved,
                exit_ready,
                not_dry_run,
                is_dry_run_generated,
            ),
        )
    return eligibility_id
