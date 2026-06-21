from __future__ import annotations

from typing import Any

from app.brains.contracts import CapitalBrainInput, bounded
from app.services.capital_allocator import PaperCapitalSource


class CapitalInputBuilder:
    def build(self, conn, *, market_id: str | None = None, candidate_engine: str | None = None, manual: dict[str, Any] | None = None, connection_factory=None) -> CapitalBrainInput:
        if manual is not None:
            return CapitalBrainInput(
                market_id=market_id or manual.get("market_id"),
                market_family=manual.get("market_family"),
                candidate_engine=candidate_engine or manual.get("candidate_engine"),
                balance=manual.get("balance"),
                available_capital=manual.get("available_capital"),
                locked_capital=manual.get("locked_capital", 0),
                open_positions=manual.get("open_positions") or [],
                engine_budgets=manual.get("engine_budgets") or {},
                risk_limits=manual.get("risk_limits") or {},
                capital_recycling_speed=manual.get("capital_recycling_speed", 0),
                memory_snapshot=manual.get("memory_snapshot") or _memory(conn, market_id),
                data_completeness_score=manual.get("data_completeness_score", 0.5),
            )
        reasons: list[str] = []
        memory = _memory(conn, market_id)
        try:
            snapshot = PaperCapitalSource(connection_factory=connection_factory).snapshot() if connection_factory else None
        except Exception:
            snapshot = None
        if snapshot is None:
            reasons.append("missing_capital_snapshot")
            return CapitalBrainInput(market_id=market_id, candidate_engine=candidate_engine, memory_snapshot=memory, insufficient_data_reasons=reasons)
        metadata = snapshot.metadata or {}
        risk_limits = {
            "min_cash_reserve_pct": float(metadata.get("paper_min_cash_reserve_pct") or 0.2),
            "max_alloc_pct": float(metadata.get("paper_max_alloc_per_trade_pct") or 0.05),
            "max_open_exposure_pct": float(metadata.get("paper_max_total_deployment_pct") or 0.5),
        }
        return CapitalBrainInput(
            market_id=market_id,
            market_family=memory.get("market_family"),
            candidate_engine=candidate_engine,
            balance=snapshot.total_equity_usd,
            available_capital=snapshot.available_cash_usd,
            locked_capital=snapshot.deployed_notional_usd + snapshot.pending_notional_usd,
            open_positions=[{"notional_usd": snapshot.deployed_notional_usd}],
            engine_budgets={candidate_engine: metadata.get("max_alloc_per_trade_usd", snapshot.available_cash_usd)} if candidate_engine else {},
            risk_limits=risk_limits,
            capital_recycling_speed=bounded((memory.get("avg_time_efficiency") or 0.0) if memory else 0.0),
            memory_snapshot=memory,
            data_completeness_score=bounded(memory.get("memory_confidence") if memory else 0.0),
            insufficient_data_reasons=[] if snapshot.source_status == "READY" else [f"capital_source_{snapshot.source_status.lower()}"],
        )


def _memory(conn, market_id: str | None) -> dict[str, Any]:
    if not market_id:
        return {}
    exists = conn.execute("SELECT to_regclass('market_memory_v2') AS name").fetchone()["name"]
    if not exists:
        return {}
    row = conn.execute("SELECT * FROM market_memory_v2 WHERE market_id = %s ORDER BY updated_at DESC LIMIT 1", (market_id,)).fetchone()
    if not row:
        return {}
    memory = dict(row)
    slip_exists = conn.execute("SELECT to_regclass('slippage_memory') AS name").fetchone()["name"]
    if slip_exists:
        slips = conn.execute("SELECT * FROM slippage_memory WHERE market_id = %s ORDER BY updated_at DESC LIMIT 1", (market_id,)).fetchall()
        memory["slippage_memory"] = [dict(row) for row in slips]
    return memory
