from __future__ import annotations

from enum import StrEnum


class NeuralEventType(StrEnum):
    NEWS_DETECTED = "NEWS_DETECTED"
    WHALE_DETECTED = "WHALE_DETECTED"
    SOCIAL_SPIKE = "SOCIAL_SPIKE"
    MARKET_REPRICING = "MARKET_REPRICING"
    LIQUIDITY_CHANGED = "LIQUIDITY_CHANGED"
    SPREAD_CHANGED = "SPREAD_CHANGED"
    ORDERBOOK_REFRESHED = "ORDERBOOK_REFRESHED"
    TOKEN_BOOK_UNAVAILABLE = "TOKEN_BOOK_UNAVAILABLE"
    MARKET_RESOLVED = "MARKET_RESOLVED"
    SIDE_DETERMINED = "SIDE_DETERMINED"
    TRUSTED_ORDERBOOK_CREATED = "TRUSTED_ORDERBOOK_CREATED"
    RISK_CHANGED = "RISK_CHANGED"
    EXIT_CHANGED = "EXIT_CHANGED"
    ELIGIBILITY_CHANGED = "ELIGIBILITY_CHANGED"
    PAPER_INTENT_CREATED = "PAPER_INTENT_CREATED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_ORDERBOOK_REFRESHED = "POSITION_ORDERBOOK_REFRESHED"
    POSITION_EXIT_RISK = "POSITION_EXIT_RISK"
    TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION = "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION"
    EXIT_REVIEW = "EXIT_REVIEW"
    HOLD_REVIEW = "HOLD_REVIEW"
    TOKEN_IDENTITY_DRIFT_REVIEW = "TOKEN_IDENTITY_DRIFT_REVIEW"
    MISSING_POSITION_TOKEN = "MISSING_POSITION_TOKEN"
    PNL_CHANGED = "PNL_CHANGED"
    CAPITAL_CHANGED = "CAPITAL_CHANGED"
    NO_TRADE_RECORDED = "NO_TRADE_RECORDED"
    AI_CONTEXT_UPDATED = "AI_CONTEXT_UPDATED"
    AI_CONTEXT_UNAVAILABLE = "AI_CONTEXT_UNAVAILABLE"
    MEMORY_UPDATED = "MEMORY_UPDATED"


EVENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    NeuralEventType.NEWS_DETECTED.value: "Source-backed news evidence changed market context.",
    NeuralEventType.WHALE_DETECTED.value: "Source-backed whale activity was observed.",
    NeuralEventType.SOCIAL_SPIKE.value: "Source-backed social attention changed materially.",
    NeuralEventType.MARKET_REPRICING.value: "Market price or probability evidence changed.",
    NeuralEventType.LIQUIDITY_CHANGED.value: "Liquidity evidence changed.",
    NeuralEventType.SPREAD_CHANGED.value: "Spread evidence changed.",
    NeuralEventType.ORDERBOOK_REFRESHED.value: "Orderbook evidence was refreshed.",
    NeuralEventType.TOKEN_BOOK_UNAVAILABLE.value: "A previously watched CLOB token book became unavailable.",
    NeuralEventType.MARKET_RESOLVED.value: "A watched market is closed, resolved, or no longer tradable.",
    NeuralEventType.SIDE_DETERMINED.value: "Candidate side evidence was determined.",
    NeuralEventType.TRUSTED_ORDERBOOK_CREATED.value: "Trusted side-aware orderbook evidence was created.",
    NeuralEventType.RISK_CHANGED.value: "Risk evaluation truth changed.",
    NeuralEventType.EXIT_CHANGED.value: "Exit plan truth changed.",
    NeuralEventType.ELIGIBILITY_CHANGED.value: "Eligibility truth changed.",
    NeuralEventType.PAPER_INTENT_CREATED.value: "A canonical paper intent was created.",
    NeuralEventType.POSITION_OPENED.value: "A paper position opened.",
    NeuralEventType.POSITION_CLOSED.value: "A paper position closed.",
    NeuralEventType.POSITION_ORDERBOOK_REFRESHED.value: "An open position token orderbook was refreshed.",
    NeuralEventType.POSITION_EXIT_RISK.value: "An open position has source-backed exit-risk evidence.",
    NeuralEventType.TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION.value: "An open position token book became unavailable.",
    NeuralEventType.EXIT_REVIEW.value: "An open position needs exit review; no exit is executed by this event.",
    NeuralEventType.HOLD_REVIEW.value: "An open position was reviewed and remains stable; no hold action is forced.",
    NeuralEventType.TOKEN_IDENTITY_DRIFT_REVIEW.value: "Current identity disagreed with the locked position token and needs review.",
    NeuralEventType.MISSING_POSITION_TOKEN.value: "An open position could not deterministically lock an entry token.",
    NeuralEventType.PNL_CHANGED.value: "Paper PnL ledger truth changed.",
    NeuralEventType.CAPITAL_CHANGED.value: "Paper or internal capital truth changed.",
    NeuralEventType.NO_TRADE_RECORDED.value: "A no-trade decision was recorded.",
    NeuralEventType.AI_CONTEXT_UPDATED.value: "AI or brain context evidence changed.",
    NeuralEventType.AI_CONTEXT_UNAVAILABLE.value: "AI context providers were unavailable and runtime continued safely.",
    NeuralEventType.MEMORY_UPDATED.value: "Memory truth changed.",
}


def validate_neural_event_type(value: NeuralEventType | str) -> str:
    normalized = value.value if isinstance(value, NeuralEventType) else str(value).strip().upper()
    if normalized not in EVENT_TYPE_DESCRIPTIONS:
        raise ValueError(f"unknown neural event_type: {normalized}")
    return normalized


def list_event_registry() -> list[dict[str, str]]:
    return [
        {"event_type": event_type, "description": description}
        for event_type, description in EVENT_TYPE_DESCRIPTIONS.items()
    ]
