from __future__ import annotations

from typing import Any

from app.brains.contracts import ContextBrainInput, bounded


class ContextInputBuilder:
    def build(self, conn, market_id: str, manual: dict[str, Any] | None = None) -> ContextBrainInput:
        manual = manual or {}
        market_family = manual.get("market_family") or _family(conn, market_id)
        memory = manual.get("memory_snapshot") or _latest(conn, "market_memory_v2", market_id) or {}
        memory_confidence = float(memory.get("memory_confidence") or 0) if isinstance(memory, dict) else 0.0
        news = manual.get("news_signals") if "news_signals" in manual else _news(conn, market_id)
        social = manual.get("social_signals") if "social_signals" in manual else _social(conn, market_id)
        whale = manual.get("whale_signals") if "whale_signals" in manual else _whale(conn, market_id)
        tech = manual.get("technical_signals") if "technical_signals" in manual else _technical(conn, market_id)
        rules = manual.get("rules_signals") if "rules_signals" in manual else _rules(conn, market_id)
        reasons = []
        if not memory:
            reasons.append("missing_market_memory")
        if not any([news, social, whale, tech]):
            reasons.append("missing_context_signals")
        completeness = max([bounded(row.get("data_completeness_score")) for row in tech] or [0.0])
        completeness = max(completeness, memory_confidence)
        return ContextBrainInput(
            market_id=market_id,
            market_family=market_family,
            news_signals=news,
            rules_signals=rules,
            social_signals=social,
            whale_signals=whale,
            technical_signals=tech,
            memory_snapshot={**memory, "confidence": memory_confidence} if isinstance(memory, dict) else {},
            ai_analysis=manual.get("ai_analysis"),
            data_completeness_score=manual.get("data_completeness_score", completeness),
            insufficient_data_reasons=reasons,
        )


def _exists(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _latest(conn, table: str, market_id: str) -> dict[str, Any] | None:
    if not _exists(conn, table):
        return None
    rows = conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchall()
    return dict(rows[0]) if rows else None


def _family(conn, market_id: str) -> str | None:
    row = _latest(conn, "market_memory_v2", market_id)
    return row.get("market_family") if row else None


def _news(conn, market_id: str) -> list[dict[str, Any]]:
    if not _exists(conn, "news_impact_scores"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM news_impact_scores WHERE market_id = %s ORDER BY created_at DESC LIMIT 10", (market_id,)).fetchall()]


def _social(conn, market_id: str) -> list[dict[str, Any]]:
    if not _exists(conn, "social_hype_scores"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM social_hype_scores WHERE market_id = %s ORDER BY computed_at DESC LIMIT 10", (market_id,)).fetchall()]


def _whale(conn, market_id: str) -> list[dict[str, Any]]:
    if not _exists(conn, "whale_market_scores"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM whale_market_scores WHERE market_id = %s ORDER BY computed_at DESC LIMIT 10", (market_id,)).fetchall()]


def _technical(conn, market_id: str) -> list[dict[str, Any]]:
    if not _exists(conn, "market_technical_signals"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM market_technical_signals WHERE market_id = %s ORDER BY ts DESC LIMIT 10", (market_id,)).fetchall()]


def _rules(conn, market_id: str) -> list[dict[str, Any]]:
    if not _exists(conn, "rules_risk_memory"):
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM rules_risk_memory WHERE market_id = %s ORDER BY updated_at DESC LIMIT 5", (market_id,)).fetchall()]
