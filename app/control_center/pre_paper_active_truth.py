from __future__ import annotations

from typing import Any


ACTIVE_INTENT_STATUSES = {
    "CREATED",
    "PENDING",
    "ACTIVE",
    "READY",
    "SUBMITTED",
    "OPEN",
}

TERMINAL_INTENT_STATUSES = {
    "CLOSED",
    "CANCELLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "EXECUTED",
    "FILLED",
    "QUARANTINED",
    "STALE",
    "ARCHIVED",
    "SUPERSEDED",
}

ACTIVE_POSITION_STATUSES = {"OPEN", "EXIT_PENDING"}


def pre_paper_active_counts(conn: Any) -> dict[str, int]:
    return {
        "duplicate_active_intent_risk": duplicate_active_intent_risk_count(conn),
        "open_paper_positions": active_open_position_count(conn),
    }


def duplicate_active_intent_risk_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    status_column = _intent_status_column(conn)
    if status_column is None:
        return 0
    consumed_clauses: list[str] = []
    if _table_exists(conn, "paper_fills") and _column_exists(conn, "paper_fills", "source_intent_id"):
        consumed_clauses.append("EXISTS (SELECT 1 FROM paper_fills pf WHERE pf.source_intent_id = paper_intents.paper_intent_id)")
    if _table_exists(conn, "paper_positions") and _column_exists(conn, "paper_positions", "payload_json"):
        consumed_clauses.append("EXISTS (SELECT 1 FROM paper_positions pp WHERE pp.payload_json->>'source_intent_id' = paper_intents.paper_intent_id)")
    consumed_filter = f"AND NOT ({' OR '.join(consumed_clauses)})" if consumed_clauses else ""
    rows = conn.execute(
        f"""
        SELECT market_id, side, COUNT(*) AS count
        FROM paper_intents
        WHERE upper(COALESCE({status_column}, '')) = ANY(%s)
          {consumed_filter}
          AND market_id IS NOT NULL
          AND side IS NOT NULL
        GROUP BY market_id, side
        HAVING COUNT(*) > 1
        """,
        (list(ACTIVE_INTENT_STATUSES),),
    ).fetchall()
    return len(rows)


def active_open_position_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_positions"):
        return 0
    if _column_exists(conn, "paper_positions", "current_status"):
        excluded_clause = (
            "AND COALESCE(excluded_from_active_paper_truth, false) = false"
            if _column_exists(conn, "paper_positions", "excluded_from_active_paper_truth")
            else ""
        )
        closed_clause = "AND closed_at IS NULL" if _column_exists(conn, "paper_positions", "closed_at") else ""
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM paper_positions
            WHERE upper(COALESCE(current_status, '')) = ANY(%s)
              {closed_clause}
              {excluded_clause}
            """,
            (list(ACTIVE_POSITION_STATUSES),),
        ).fetchone()
        return int(row["count"] or 0) if row else 0
    if _column_exists(conn, "paper_positions", "status"):
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_positions
            WHERE upper(COALESCE(status, 'OPEN')) = ANY(%s)
            """,
            (list(ACTIVE_POSITION_STATUSES),),
        ).fetchone()
        return int(row["count"] or 0) if row else 0
    if _column_exists(conn, "paper_positions", "closed_at"):
        row = conn.execute("SELECT COUNT(*) AS count FROM paper_positions WHERE closed_at IS NULL").fetchone()
        return int(row["count"] or 0) if row else 0
    return 0


def _intent_status_column(conn: Any) -> str | None:
    if _column_exists(conn, "paper_intents", "intent_status"):
        return "intent_status"
    if _column_exists(conn, "paper_intents", "status"):
        return "status"
    return None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)
