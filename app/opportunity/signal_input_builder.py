from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.opportunity.contracts import OpportunityInput, bounded


class OpportunitySignalInputBuilder:
    def build(self, conn: Connection, market_id: str, *, side: str | None = None, manual: dict[str, Any] | None = None) -> OpportunityInput:
        manual = manual or {}
        context = manual.get("context_output") if "context_output" in manual else _latest(conn, "context_brain_outputs", market_id)
        capital = manual.get("capital_output") if "capital_output" in manual else _latest(conn, "capital_brain_outputs", market_id)
        market_signal = manual.get("market_signal") if "market_signal" in manual else _latest(conn, "market_technical_signals", market_id)
        orderbook = manual.get("orderbook_signal") if "orderbook_signal" in manual else _latest(conn, "orderbook_signals", market_id, order_by="ts")
        liquidity = manual.get("liquidity_signal") if "liquidity_signal" in manual else _latest(conn, "liquidity_signals", market_id, order_by="ts")
        time_signal = manual.get("time_signal") if "time_signal" in manual else _latest(conn, "time_signals", market_id, order_by="ts")
        fee = manual.get("fee_reward_signal") if "fee_reward_signal" in manual else _latest(conn, "fee_reward_signals", market_id, order_by="ts")
        memory = manual.get("market_memory") if "market_memory" in manual else _latest(conn, "market_memory_v2", market_id, order_by="updated_at")
        rules = manual.get("rules_signals") if "rules_signals" in manual else _rows(conn, "rules_risk_memory", market_id, order_by="updated_at", limit=5)
        social = manual.get("social_signals") if "social_signals" in manual else _rows(conn, "social_hype_scores", market_id, order_by="computed_at", limit=5)
        whale = manual.get("whale_signals") if "whale_signals" in manual else _rows(conn, "whale_market_scores", market_id, order_by="computed_at", limit=5)
        news = manual.get("news_signals") if "news_signals" in manual else _rows(conn, "news_impact_scores", market_id, order_by="created_at", limit=5)
        context = context or {}
        capital = capital or {}
        market_signal = market_signal or {}
        orderbook = orderbook or {}
        liquidity = liquidity or {}
        time_signal = time_signal or {}
        fee = fee or {}
        memory = memory or {}
        technical_truth = {
            **market_signal,
            "market_signal": market_signal,
            "orderbook_signal": orderbook,
            "liquidity_signal": liquidity,
            "time_signal": time_signal,
            "fee_reward_signal": fee,
            "technical_blocked": bool(market_signal.get("technical_blocked")),
            "block_reasons": market_signal.get("block_reasons_json") or [],
            "technical_score": market_signal.get("technical_score") or 0,
        }
        reasons: list[str] = []
        if not context:
            reasons.append("missing_context_output")
        if not capital:
            reasons.append("missing_capital_output")
        if not market_signal:
            reasons.append("missing_technical_truth")
        if not memory:
            reasons.append("missing_market_memory")
        if not context and not capital:
            reasons.append("missing_context_and_capital")
        if capital and capital.get("insufficient_data") is True:
            reasons.extend(_json_list(capital.get("insufficient_data_reasons_json")))
        if context and context.get("insufficient_data") is True:
            reasons.extend(_json_list(context.get("insufficient_data_reasons_json")))
        completeness = max(
            bounded(manual.get("data_completeness_score")),
            bounded(context.get("confidence")),
            bounded(capital.get("allocation_confidence")),
            bounded(market_signal.get("data_completeness_score")),
            bounded(memory.get("memory_confidence")),
        )
        market_family = manual.get("market_family") or context.get("market_family") or capital.get("market_family") or memory.get("market_family")
        return OpportunityInput(
            market_id=market_id,
            market_family=market_family,
            side=side or manual.get("side") or context.get("direction") or "UNKNOWN",
            context_output=context,
            capital_output=capital,
            technical_truth=technical_truth,
            market_memory=memory,
            news_signals=news,
            rules_signals=rules,
            social_signals=social,
            whale_signals=whale,
            fee_reward_signal=fee,
            data_completeness_score=completeness,
            insufficient_data_reasons=reasons,
        )


def _exists(conn: Connection, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _latest(conn: Connection, table: str, market_id: str, *, order_by: str = "created_at") -> dict[str, Any] | None:
    if not _exists(conn, table):
        return None
    rows = conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY {order_by} DESC, id DESC LIMIT 1", (market_id,)).fetchall()
    return dict(rows[0]) if rows else None


def _rows(conn: Connection, table: str, market_id: str, *, order_by: str, limit: int) -> list[dict[str, Any]]:
    if not _exists(conn, table):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY {order_by} DESC, id DESC LIMIT %s", (market_id, limit)).fetchall()]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []

