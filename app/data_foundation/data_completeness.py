from __future__ import annotations

from typing import Any

from app.data_foundation.contracts import DataCompletenessScore


class DataCompletenessComputer:
    """Computes a 0-100 data completeness score."""

    DIMENSIONS = (
        "market_id",
        "question",
        "tokens",
        "price",
        "orderbook",
        "rules",
        "liquidity",
        "time_to_close",
        "resolution_source",
    )

    def compute_data_completeness(
        self,
        *,
        market: Any,
        rules: Any | None = None,
        latest_snapshot: Any | None = None,
        orderbook: Any | None = None,
        liquidity: Any | None = None,
        fees: Any | None = None,
        stale_fields: list[str] | None = None,
        require_orderbook: bool = True,
        require_rules: bool = True,
    ) -> DataCompletenessScore:
        stale_fields = stale_fields or []
        get = _getter
        market_id = str(get(market, "market_id") or "")
        has_market_id = bool(market_id)
        has_question = bool(get(market, "question"))
        yes_token = get(market, "yes_token_id") or _token_from_raw(market, 0)
        no_token = get(market, "no_token_id") or _token_from_raw(market, 1)
        has_tokens = bool(yes_token and no_token)
        has_price = any(
            value is not None
            for value in (
                get(latest_snapshot, "current_price_yes"),
                get(latest_snapshot, "best_bid"),
                get(latest_snapshot, "best_ask"),
                get(market, "current_price_yes"),
                get(market, "yes_price"),
                get(market, "best_bid"),
                get(market, "best_ask"),
            )
        )
        has_orderbook = orderbook is not None and (
            get(orderbook, "best_bid") is not None or get(orderbook, "best_ask") is not None or get(orderbook, "depth_2c") is not None
        )
        has_rules = rules is not None and bool(get(rules, "rules_text") or get(rules, "rules_hash") or get(rules, "rules_missing") is True)
        has_liquidity = liquidity is not None and get(liquidity, "liquidity_score") is not None
        has_time_to_close = get(latest_snapshot, "time_to_close_seconds") is not None or get(market, "time_to_close_seconds") is not None or get(market, "close_time") is not None
        has_resolution_source = bool(get(rules, "resolution_source") or get(market, "resolution_source"))

        checks = {
            "market_id": has_market_id,
            "question": has_question,
            "tokens": has_tokens,
            "price": has_price,
            "orderbook": has_orderbook,
            "rules": has_rules,
            "liquidity": has_liquidity,
            "time_to_close": has_time_to_close,
            "resolution_source": has_resolution_source,
        }
        missing = [name for name, present in checks.items() if not present]
        score = round((sum(1 for present in checks.values() if present) / len(checks)) * 100, 2)
        no_trade_reasons = [f"missing_{name}" for name in missing] + [f"stale_{name}" for name in stale_fields]
        if bool(get(market, "closed")):
            no_trade_reasons.append("market_closed")
        if get(market, "accepting_orders") is False:
            no_trade_reasons.append("market_not_accepting_orders")
        critical_missing = {"market_id", "question", "tokens", "price", "time_to_close"}
        if require_orderbook:
            critical_missing.add("orderbook")
            critical_missing.add("liquidity")
        if require_rules:
            critical_missing.add("rules")
        candidate_allowed = (
            not (critical_missing & set(missing))
            and not stale_fields
            and not bool(get(market, "closed"))
            and get(market, "accepting_orders") is not False
        )
        return DataCompletenessScore(
            market_id=market_id,
            has_market_id=has_market_id,
            has_question=has_question,
            has_tokens=has_tokens,
            has_price=has_price,
            has_orderbook=has_orderbook,
            has_rules=has_rules,
            has_liquidity=has_liquidity,
            has_time_to_close=has_time_to_close,
            has_resolution_source=has_resolution_source,
            score=score,
            missing_fields=missing,
            stale_fields=stale_fields,
            candidate_allowed=candidate_allowed,
            no_trade_reasons=no_trade_reasons,
        )


def _getter(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _token_from_raw(market: Any, index: int) -> str | None:
    raw = _getter(market, "raw_market_json") or _getter(market, "raw_market") or {}
    token_ids = raw.get("clobTokenIds") or raw.get("outcomeTokens")
    if isinstance(token_ids, str):
        import json

        try:
            token_ids = json.loads(token_ids)
        except json.JSONDecodeError:
            token_ids = []
    if isinstance(token_ids, list) and len(token_ids) > index:
        return str(token_ids[index])
    return None
