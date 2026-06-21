"""
SQLite persistence helpers for Stage 3 paper trading.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DB_PATH = Path("logs/paper_trading.db")


@dataclass(slots=True)
class TradeRecord:
    id: int
    signal_id: int
    market_id: str | None
    question: str
    side: str
    entry_price: float
    size_usd: float
    entry_time: str
    exit_price: float | None
    exit_time: str | None
    realized_pnl: float | None
    status: str
    bucket: str | None = None


@dataclass(slots=True)
class PortfolioSnapshot:
    id: int
    timestamp: str
    total_balance: float
    bucket_safe: float
    bucket_high: float
    bucket_whale: float
    bucket_reserve: float
    open_positions: int
    total_pnl: float


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_trade(row: sqlite3.Row) -> TradeRecord:
    return TradeRecord(
        id=int(row["id"]),
        signal_id=int(row["signal_id"]),
        market_id=row["market_id"],
        question=str(row["question"]),
        side=str(row["side"]),
        entry_price=float(row["entry_price"]),
        size_usd=float(row["size_usd"]),
        entry_time=str(row["entry_time"]),
        exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
        exit_time=str(row["exit_time"]) if row["exit_time"] is not None else None,
        realized_pnl=float(row["realized_pnl"]) if row["realized_pnl"] is not None else None,
        status=str(row["status"]),
        bucket=row["bucket"] if "bucket" in row.keys() else None,
    )


def _row_to_snapshot(row: sqlite3.Row) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=int(row["id"]),
        timestamp=str(row["timestamp"]),
        total_balance=float(row["total_balance"]),
        bucket_safe=float(row["bucket_safe"]),
        bucket_high=float(row["bucket_high"]),
        bucket_whale=float(row["bucket_whale"]),
        bucket_reserve=float(row["bucket_reserve"]),
        open_positions=int(row["open_positions"]),
        total_pnl=float(row["total_pnl"]),
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT,
                timestamp     TEXT    NOT NULL,
                total_markets INTEGER NOT NULL DEFAULT 0,
                top_market    TEXT,
                top_score     REAL
            );

            CREATE TABLE IF NOT EXISTS signals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                scan_id    INTEGER REFERENCES scans(id),
                market_id  TEXT,
                question   TEXT    NOT NULL,
                yes_price  REAL,
                edge       REAL,
                score      REAL,
                ai_action  TEXT,
                confidence REAL,
                reason     TEXT,
                bucket     TEXT,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT,
                signal_id    INTEGER REFERENCES signals(id),
                market_id    TEXT,
                question     TEXT    NOT NULL,
                side         TEXT    NOT NULL,
                entry_price  REAL    NOT NULL,
                size_usd     REAL    NOT NULL,
                entry_time   TEXT    NOT NULL,
                exit_price   REAL,
                exit_time    TEXT,
                realized_pnl REAL,
                status       TEXT    NOT NULL DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS portfolio (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT,
                timestamp       TEXT NOT NULL,
                total_balance   REAL NOT NULL,
                bucket_safe     REAL NOT NULL DEFAULT 0,
                bucket_high     REAL NOT NULL DEFAULT 0,
                bucket_whale    REAL NOT NULL DEFAULT 0,
                bucket_reserve  REAL NOT NULL DEFAULT 0,
                open_positions  INTEGER NOT NULL DEFAULT 0,
                total_pnl       REAL NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_scans_session_id ON scans(session_id);
            CREATE INDEX IF NOT EXISTS idx_signals_scan_id ON signals(scan_id);
            CREATE INDEX IF NOT EXISTS idx_signals_session_id ON signals(session_id);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_session_id ON paper_trades(session_id);
            CREATE INDEX IF NOT EXISTS idx_trades_market_status ON paper_trades(market_id, status);
            CREATE INDEX IF NOT EXISTS idx_portfolio_timestamp ON portfolio(timestamp);
            CREATE INDEX IF NOT EXISTS idx_portfolio_session_id ON portfolio(session_id);
            """
        )
        _ensure_column(conn, "scans", "session_id", "TEXT")
        _ensure_column(conn, "signals", "session_id", "TEXT")
        _ensure_column(conn, "paper_trades", "session_id", "TEXT")
        _ensure_column(conn, "portfolio", "session_id", "TEXT")


def insert_scan(
    total_markets: int,
    top_market: str | None,
    top_score: float | None,
    session_id: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO scans (session_id, timestamp, total_markets, top_market, top_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, _utc_now(), total_markets, top_market, top_score),
        )
        return int(cur.lastrowid)


def insert_signal(
    scan_id: int,
    market_id: str | None,
    question: str,
    yes_price: float | None,
    edge: float | None,
    score: float,
    ai_action: str,
    confidence: float,
    reason: str,
    bucket: str | None,
    session_id: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO signals (
                session_id, scan_id, market_id, question, yes_price, edge, score,
                ai_action, confidence, reason, bucket, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                scan_id,
                market_id,
                question,
                yes_price,
                edge,
                score,
                ai_action,
                confidence,
                reason,
                bucket,
                _utc_now(),
            ),
        )
        return int(cur.lastrowid)


def insert_paper_trade(
    signal_id: int,
    market_id: str | None,
    question: str,
    side: str,
    entry_price: float,
    size_usd: float,
    session_id: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO paper_trades (
                session_id, signal_id, market_id, question, side, entry_price, size_usd, entry_time, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            (session_id, signal_id, market_id, question, side, entry_price, size_usd, _utc_now()),
        )
        return int(cur.lastrowid)


def close_paper_trade(trade_id: int, exit_price: float, realized_pnl: float) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE paper_trades
            SET exit_price = ?, exit_time = ?, realized_pnl = ?, status = 'closed'
            WHERE id = ?
            """,
            (exit_price, _utc_now(), realized_pnl, trade_id),
        )


def insert_portfolio_snapshot(
    total_balance: float,
    bucket_safe: float,
    bucket_high: float,
    bucket_whale: float,
    bucket_reserve: float,
    open_positions: int,
    total_pnl: float,
    session_id: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO portfolio (
                session_id, timestamp, total_balance, bucket_safe, bucket_high,
                bucket_whale, bucket_reserve, open_positions, total_pnl
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                _utc_now(),
                total_balance,
                bucket_safe,
                bucket_high,
                bucket_whale,
                bucket_reserve,
                open_positions,
                total_pnl,
            ),
        )
        return int(cur.lastrowid)


def get_open_trades(session_id: str | None = None) -> list[TradeRecord]:
    where_clause = "WHERE t.status = 'open'"
    params: tuple[object, ...] = ()
    if session_id is not None:
        where_clause += " AND t.session_id = ?"
        params = (session_id,)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.bucket
            FROM paper_trades AS t
            LEFT JOIN signals AS s ON s.id = t.signal_id
            """ + where_clause + """
            ORDER BY t.entry_time ASC
            """,
            params,
        ).fetchall()
    return [_row_to_trade(row) for row in rows]


def get_closed_trades(session_id: str | None = None) -> list[TradeRecord]:
    where_clause = "WHERE t.status = 'closed'"
    params: tuple[object, ...] = ()
    if session_id is not None:
        where_clause += " AND t.session_id = ?"
        params = (session_id,)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.bucket
            FROM paper_trades AS t
            LEFT JOIN signals AS s ON s.id = t.signal_id
            """ + where_clause + """
            ORDER BY t.exit_time ASC, t.entry_time ASC
            """,
            params,
        ).fetchall()
    return [_row_to_trade(row) for row in rows]


def get_trade_counts(session_id: str | None = None) -> dict[str, int]:
    where_clause = ""
    params: tuple[object, ...] = ()
    if session_id is not None:
        where_clause = "WHERE session_id = ?"
        params = (session_id,)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_count
            FROM paper_trades
            """ + where_clause,
            params,
        ).fetchone()
    return {
        "open": int(row["open_count"] or 0),
        "closed": int(row["closed_count"] or 0),
    }


def get_latest_portfolio_snapshot(session_id: str | None = None) -> PortfolioSnapshot | None:
    where_clause = ""
    params: tuple[object, ...] = ()
    if session_id is not None:
        where_clause = "WHERE session_id = ?"
        params = (session_id,)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM portfolio
            """ + where_clause + """
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    return _row_to_snapshot(row) if row is not None else None


def has_open_trade_for_market(market_id: str | None, session_id: str | None = None) -> bool:
    if not market_id:
        return False
    params: tuple[object, ...]
    where_clause = "WHERE market_id = ? AND status = 'open'"
    if session_id is not None:
        where_clause += " AND session_id = ?"
        params = (market_id, session_id)
    else:
        params = (market_id,)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM paper_trades
            """ + where_clause + """
            LIMIT 1
            """,
            params,
        ).fetchone()
    return row is not None


def get_realized_pnl(session_id: str | None = None) -> float:
    where_clause = "WHERE status = 'closed'"
    params: tuple[object, ...] = ()
    if session_id is not None:
        where_clause += " AND session_id = ?"
        params = (session_id,)
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) AS realized_pnl FROM paper_trades "
            + where_clause,
            params,
        ).fetchone()
    return float(row["realized_pnl"] or 0.0)


def reset_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()


def row_to_dict(row: sqlite3.Row | PortfolioSnapshot | TradeRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, PortfolioSnapshot):
        return {
            "id": row.id,
            "timestamp": row.timestamp,
            "total_balance": row.total_balance,
            "bucket_safe": row.bucket_safe,
            "bucket_high": row.bucket_high,
            "bucket_whale": row.bucket_whale,
            "bucket_reserve": row.bucket_reserve,
            "open_positions": row.open_positions,
            "total_pnl": row.total_pnl,
        }
    return {
        "id": row.id,
        "signal_id": row.signal_id,
        "market_id": row.market_id,
        "question": row.question,
        "side": row.side,
        "entry_price": row.entry_price,
        "size_usd": row.size_usd,
        "entry_time": row.entry_time,
        "exit_price": row.exit_price,
        "exit_time": row.exit_time,
        "realized_pnl": row.realized_pnl,
        "status": row.status,
        "bucket": row.bucket,
    }
