from __future__ import annotations

from typing import Any

from app.ai_brain.ai_errors import AICaseFileUnavailable
from app.ai_brain.contracts import AICaseFile, AITaskType
from app.ai_brain.redaction import redact_dict
from app.data_foundation.data_completeness import DataCompletenessComputer
from app.db.connection import DatabaseConnectionFactory


class AICaseFileBuilder:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._completeness = DataCompletenessComputer()

    def build_case_file(
        self,
        market_id: str,
        *,
        task_type: AITaskType | str | None = None,
        event_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AICaseFile:
        if not self._factory.enabled:
            raise AICaseFileUnavailable("database unavailable for AI case file")
        with self._factory.connect() as conn:
            market = conn.execute("SELECT * FROM markets_v2 WHERE market_id = %s", (market_id,)).fetchone()
            if market is None:
                raise AICaseFileUnavailable(f"market not found: {market_id}")
            rules = conn.execute(
                "SELECT * FROM market_rules WHERE market_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            snapshot = conn.execute(
                "SELECT * FROM market_snapshots_v2 WHERE market_id = %s ORDER BY snapshot_at DESC, id DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            orderbook = conn.execute(
                "SELECT * FROM orderbook_snapshots WHERE market_id = %s ORDER BY snapshot_at DESC, id DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            liquidity = conn.execute(
                "SELECT * FROM liquidity_snapshots WHERE market_id = %s ORDER BY snapshot_at DESC, id DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            fees = conn.execute(
                "SELECT * FROM fee_snapshots WHERE market_id = %s ORDER BY snapshot_at DESC, id DESC LIMIT 1",
                (market_id,),
            ).fetchone()
            family = conn.execute("SELECT * FROM market_family_map WHERE market_id = %s", (market_id,)).fetchone()

        stale_fields: list[str] = []
        if snapshot and snapshot.get("stale"):
            stale_fields.append("market_snapshot")
        score = self._completeness.compute_data_completeness(
            market=market,
            rules=rules,
            latest_snapshot=snapshot,
            orderbook=orderbook,
            liquidity=liquidity,
            fees=fees,
            stale_fields=stale_fields,
        )
        blocked_reason = None
        if bool(market.get("closed")):
            blocked_reason = "market_closed"
        elif score.score < 50:
            blocked_reason = "low_data_completeness"
        elif score.stale_fields:
            blocked_reason = "stale_data"
        elif not score.candidate_allowed:
            blocked_reason = "data_incomplete_for_candidate"
        allowed_for_ai = blocked_reason is None
        return AICaseFile(
            market_id=market.get("market_id"),
            question=market.get("question"),
            category=market.get("category"),
            market_family=(family or {}).get("market_family") or market.get("market_family"),
            prices={
                "current_price_yes": _float_or_none((snapshot or {}).get("current_price_yes")),
                "current_price_no": _float_or_none((snapshot or {}).get("current_price_no")),
            },
            bid_ask={
                "best_bid": _float_or_none((orderbook or snapshot or {}).get("best_bid")),
                "best_ask": _float_or_none((orderbook or snapshot or {}).get("best_ask")),
            },
            spread=_float_or_none((orderbook or snapshot or {}).get("spread")),
            liquidity={
                "liquidity_score": _float_or_none((liquidity or {}).get("liquidity_score")),
                "exit_quality": _float_or_none((liquidity or {}).get("exit_quality")),
                "max_safe_size": _float_or_none((liquidity or {}).get("max_safe_size")),
            },
            time_to_close=(snapshot or {}).get("time_to_close_seconds"),
            rules_summary_or_text=(rules or {}).get("rules_text"),
            resolution_source=(rules or {}).get("resolution_source") or market.get("resolution_source"),
            data_completeness_score=score.score,
            missing_fields=score.missing_fields,
            stale_fields=score.stale_fields,
            orderbook_missing=orderbook is None,
            rules_missing=rules is None or not bool((rules or {}).get("rules_text")),
            allowed_for_ai=allowed_for_ai,
            blocked_reason=blocked_reason,
            metadata=redact_dict(
                {
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                    "task_type": str(task_type) if task_type else None,
                    "closed": bool(market.get("closed")),
                    "accepting_orders": market.get("accepting_orders"),
                    "fee_snapshot_available": fees is not None,
                    "no_trade_reasons": score.no_trade_reasons,
                }
            ),
        )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
