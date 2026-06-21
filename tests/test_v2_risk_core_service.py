from __future__ import annotations

import json

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.risk_core import RiskCoreService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "risk_decisions",
            "thesis_profile_evidence_items",
            "thesis_profiles",
            "orderbook_snapshots",
            "signal_market_links",
            "neuron_signals",
            "markets_v2",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        if _table_exists(conn, "risk_gate_runs"):
            conn.execute("DELETE FROM risk_gate_runs WHERE engine = 'RISK_CORE_FOUNDATION'")


def _seed_thesis(
    thesis_id: str = "thesis-runtime",
    *,
    status: str = "BLOCKED",
    market_id: str | None = "market-risk",
    confidence: float = 0.7,
    orderbook: bool = True,
    binding: bool = True,
    spread: float = 0.03,
    liquidity_score: float = 0.8,
    missing: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    missing_items = list(missing or [])
    if market_id is None and "MISSING_MARKET_ID" not in missing_items:
        missing_items.append("MISSING_MARKET_ID")
    if not orderbook and market_id and "MISSING_FRESH_ORDERBOOK" not in missing_items:
        missing_items.append("MISSING_FRESH_ORDERBOOK")
    if not binding and "MISSING_SIGNAL_MARKET_BINDING" not in missing_items:
        missing_items.append("MISSING_SIGNAL_MARKET_BINDING")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        orderbook_id = None
        if market_id:
            conn.execute("INSERT INTO markets_v2 (market_id, question, slug) VALUES (%s, 'Risk market?', %s) ON CONFLICT DO NOTHING", (market_id, market_id))
        if orderbook and market_id:
            orderbook_id = conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, best_bid, best_ask, spread,
                    liquidity_score, source, snapshot_status, is_stale, collected_at, created_at
                )
                VALUES (%s, %s, 0.45, 0.48, %s, %s, 'test', 'OK', false, now(), now())
                RETURNING id
                """,
                (f"book-{thesis_id}", market_id, spread, liquidity_score),
            ).fetchone()["id"]
        if binding and market_id:
            conn.execute(
                """
                INSERT INTO neuron_signals (
                    signal_id, neuron, event_type, source_name, market_id,
                    confidence, strength, evidence_json, status, created_at, updated_at
                )
                VALUES (%s, 'market', 'risk_test', 'runtime_source', %s, 0.8, 0.7, '{}'::jsonb, 'ACTIVE', now(), now())
                """,
                (f"signal-{thesis_id}", market_id),
            )
            conn.execute(
                "INSERT INTO signal_market_links (signal_id, market_id, link_type, link_status, confidence, reason, created_by) VALUES (%s, %s, 'test', 'confirmed', 0.95, 'test', 'test')",
                (f"signal-{thesis_id}", market_id),
            )
        conn.execute(
            """
            INSERT INTO thesis_profiles (
                thesis_id, market_id, side, status, thesis_type, why_now,
                expected_move, confidence, evidence, missing_evidence,
                invalidation_rules, risk_notes, source_coordinator_decision_id,
                source_brain_output_ids, source_signal_ids, orderbook_snapshot_id,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, paper_candidate_allowed, risk_required,
                exit_required, created_at, updated_at
            )
            VALUES (
                %s, %s, 'YES', %s, 'RUNTIME_COORDINATOR_THESIS',
                'Risk test thesis.', 'YES', %s, '{}'::jsonb, %s::jsonb,
                '[]'::jsonb, '["NO_RISK_CORE","NO_EXIT_FOUNDATION"]'::jsonb,
                'coord-test', '[]'::jsonb, %s::jsonb, %s,
                %s, 'thesis_profile_builder', %s, %s, false, true, true, now(), now()
            )
            """,
            (
                thesis_id,
                market_id,
                status,
                confidence,
                json.dumps(missing_items),
                json.dumps([f"signal-{thesis_id}"] if binding else []),
                orderbook_id,
                "dry_run" if dry_run else "runtime",
                not dry_run,
                dry_run,
            ),
        )


def test_risk_evaluates_blocked_thesis_as_block(postgres_test_schema) -> None:
    _prepare()
    _seed_thesis(status="BLOCKED")

    result = RiskCoreService().evaluate_risk(limit=10)

    assert result["mock_data"] is False
    assert result["thesis_profiles_checked"] == 1
    assert result["risk_decisions_created"] == 1
    assert result["blocked_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM risk_decisions").fetchone()
    assert row["decision"] == "BLOCK"
    assert row["risk_approved"] is False
    assert row["execution_allowed"] is False


def test_missing_market_orderbook_and_binding_block_approval(postgres_test_schema) -> None:
    _prepare()
    _seed_thesis("thesis-missing-market", market_id=None, orderbook=False, binding=False)
    _seed_thesis("thesis-missing-book", orderbook=False)
    _seed_thesis("thesis-missing-binding", binding=False)

    result = RiskCoreService().evaluate_risk(limit=10)

    assert result["blocked_count"] == 3
    with DatabaseConnectionFactory().connect() as conn:
        blockers = conn.execute(
            """
            SELECT jsonb_agg(blockers) AS blockers
            FROM risk_decisions
            """
        ).fetchone()["blockers"]
    flattened = {item for group in blockers for item in group}
    assert "MISSING_MARKET_ID" in flattened
    assert "MISSING_FRESH_ORDERBOOK" in flattened
    assert "MISSING_SIGNAL_MARKET_BINDING" in flattened


def test_low_confidence_wide_spread_and_low_liquidity_block_or_reject(postgres_test_schema) -> None:
    _prepare()
    _seed_thesis("thesis-low-confidence", status="COMPLETE", confidence=0.2)
    _seed_thesis("thesis-wide-spread", status="COMPLETE", spread=0.2)
    _seed_thesis("thesis-low-liquidity", status="COMPLETE", liquidity_score=0.1)

    result = RiskCoreService().evaluate_risk(limit=10)

    assert result["risk_decisions_created"] == 3
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT blockers, risk_score FROM risk_decisions ORDER BY thesis_id").fetchall()
    flattened = {item for row in rows for item in row["blockers"]}
    assert "CONFIDENCE_TOO_LOW" in flattened
    assert "SPREAD_TOO_WIDE" in flattened
    assert "LIQUIDITY_TOO_LOW" in flattened
    assert all(0 <= float(row["risk_score"]) <= 1 for row in rows)


def test_complete_low_risk_thesis_can_get_risk_layer_approval_without_paper(postgres_test_schema) -> None:
    _prepare()
    _seed_thesis("thesis-complete", status="COMPLETE")

    result = RiskCoreService().evaluate_risk(limit=10)

    assert result["approved_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM risk_decisions").fetchone()
    assert row["risk_approved"] is True
    assert row["paper_candidate_allowed"] is False
    assert row["execution_allowed"] is False


def test_dry_run_thesis_is_ignored(postgres_test_schema) -> None:
    _prepare()
    _seed_thesis("thesis-dry", dry_run=True)

    result = RiskCoreService().evaluate_risk(limit=10)

    assert result["thesis_profiles_checked"] == 0
    assert result["risk_decisions_created"] == 0

