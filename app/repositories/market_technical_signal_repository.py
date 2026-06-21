from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_neuron.contracts import TechnicalMarketTruth


class MarketTechnicalSignalRepository:
    def insert_truth(self, conn: Connection, truth: TechnicalMarketTruth) -> dict[str, Any]:
        signal = truth.market_signal
        return conn.execute(
            """
            INSERT INTO market_technical_signals (
                market_id, ts, price_yes, price_no, price_change_1m, price_change_5m,
                price_change_15m, price_change_1h, volume_1h, volume_24h,
                volatility_score, momentum_score, trend_direction, trend_strength,
                candle_summary_json, market_regime, data_completeness_score, stale,
                technical_score, technical_blocked, block_reasons_json, source, raw_snapshot_json
            )
            VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                signal.market_id,
                signal.price_yes,
                signal.price_no,
                signal.price_change_1m,
                signal.price_change_5m,
                signal.price_change_15m,
                signal.price_change_1h,
                signal.volume_1h,
                signal.volume_24h,
                signal.volatility_score,
                signal.momentum_score,
                signal.trend_direction.value,
                signal.trend_strength,
                Jsonb(_jsonable(signal.candle_summary)),
                signal.market_regime.value,
                truth.data_completeness_score,
                signal.stale,
                truth.technical_score,
                truth.technical_blocked,
                Jsonb(truth.block_reasons),
                signal.source,
                Jsonb(_jsonable(signal.raw_snapshot)),
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM market_technical_signals WHERE market_id = %s ORDER BY ts DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def list_recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM market_technical_signals ORDER BY ts DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def list_blocked(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM market_technical_signals WHERE technical_blocked IS TRUE ORDER BY ts DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def list_top(self, conn: Connection, *, limit: int = 50, min_completeness: float = 0.5) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM market_technical_signals
            WHERE technical_blocked IS FALSE
              AND stale IS FALSE
              AND data_completeness_score >= %s
            ORDER BY technical_score DESC, ts DESC, id DESC
            LIMIT %s
            """,
            (min_completeness, limit),
        ).fetchall()

    def health(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT
                MAX(ts) AS last_signal_ts,
                COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS signals_today,
                COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND technical_blocked IS TRUE) AS blocked_today,
                COUNT(*) FILTER (WHERE stale IS TRUE) AS stale_count
            FROM market_technical_signals
            """
        ).fetchone()


def latest_component(conn: Connection, table: str, market_id: str) -> dict[str, Any] | None:
    if table not in {"orderbook_signals", "liquidity_signals", "time_signals", "fee_reward_signals"}:
        raise ValueError("unsupported table")
    return conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY ts DESC, id DESC LIMIT 1", (market_id,)).fetchone()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
