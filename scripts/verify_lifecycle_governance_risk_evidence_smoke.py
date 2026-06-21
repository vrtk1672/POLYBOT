from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.lifecycle_governance import LifecycleGovernanceGateService


SAFETY_TABLES = (
    "live_orders",
    "paper_intents",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "paper_position_closes",
    "paper_capital_ledger",
    "orders_v2",
    "fills_v2",
    "positions",
)


def main() -> None:
    factory = DatabaseConnectionFactory()
    if not factory.enabled:
        print({"status": "DATABASE_DISABLED"})
        return

    with factory.connect() as conn, conn.transaction():
        before = _safety_counts(conn)

    result = LifecycleGovernanceGateService(connection_factory=factory).evaluate_recent(limit=50, dry_run=False)
    summary = LifecycleGovernanceGateService(connection_factory=factory).dashboard_summary(limit=20)

    with factory.connect() as conn, conn.transaction():
        after = _safety_counts(conn)

    print(
        {
            "status": result.get("status"),
            "plans_checked": result.get("plans_checked"),
            "decisions_created": result.get("decisions_created"),
            "trading_mutation": before != after,
            "safety_before": before,
            "safety_after": after,
            "risk_evidence_used_count": summary.get("risk_evidence_used_count"),
            "legacy_risk_ignored_count": summary.get("legacy_risk_ignored_count"),
            "stale_legacy_risk_block_ignored_count": summary.get("stale_legacy_risk_block_ignored_count"),
            "risk_review_promoted_to_watch_count": summary.get("risk_review_promoted_to_watch_count"),
            "risk_review_kept_blocked_count": summary.get("risk_review_kept_blocked_count"),
            "risk_review_actionable_count": summary.get("risk_review_actionable_count"),
            "allow_paper_intent_count": summary.get("allow_paper_intent_count"),
            "allow_paper_execution_count": summary.get("allow_paper_execution_count"),
        }
    )


def _safety_counts(conn) -> dict[str, object]:
    counts = {table: _count_table(conn, table) for table in SAFETY_TABLES}
    if _table_exists(conn, "paper_accounts"):
        row = conn.execute(
            """
            SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl
            FROM paper_accounts
            WHERE account_id='paper_default'
            """
        ).fetchone()
        counts["capital_balances"] = dict(row) if row else None
    else:
        counts["capital_balances"] = None
    return counts


def _count_table(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


if __name__ == "__main__":
    main()
