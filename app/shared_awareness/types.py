from __future__ import annotations

from datetime import timedelta
from enum import StrEnum


class AwarenessDomain(StrEnum):
    NEWS = "NEWS"
    WHALE = "WHALE"
    SOCIAL = "SOCIAL"
    RULES = "RULES"
    LIQUIDITY = "LIQUIDITY"
    ORDERBOOK = "ORDERBOOK"
    FEES = "FEES"
    TIME = "TIME"
    RISK = "RISK"
    EXIT = "EXIT"
    CAPITAL = "CAPITAL"
    PNL = "PNL"
    MEMORY = "MEMORY"
    POSITION = "POSITION"
    CANDIDATE = "CANDIDATE"


class DomainStatus(StrEnum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


DOMAIN_STATE_COLUMNS: dict[AwarenessDomain, str] = {
    AwarenessDomain.NEWS: "news_state_json",
    AwarenessDomain.WHALE: "whale_state_json",
    AwarenessDomain.SOCIAL: "social_state_json",
    AwarenessDomain.RULES: "rules_state_json",
    AwarenessDomain.LIQUIDITY: "liquidity_state_json",
    AwarenessDomain.ORDERBOOK: "orderbook_state_json",
    AwarenessDomain.FEES: "fees_state_json",
    AwarenessDomain.TIME: "time_state_json",
    AwarenessDomain.RISK: "risk_state_json",
    AwarenessDomain.EXIT: "exit_state_json",
    AwarenessDomain.CAPITAL: "capital_state_json",
    AwarenessDomain.PNL: "pnl_state_json",
    AwarenessDomain.MEMORY: "memory_state_json",
    AwarenessDomain.POSITION: "position_state_json",
    AwarenessDomain.CANDIDATE: "candidate_state_json",
}


FRESHNESS_WINDOWS: dict[AwarenessDomain, timedelta] = {
    AwarenessDomain.ORDERBOOK: timedelta(minutes=5),
    AwarenessDomain.LIQUIDITY: timedelta(minutes=5),
    AwarenessDomain.FEES: timedelta(hours=6),
    AwarenessDomain.RISK: timedelta(hours=24),
    AwarenessDomain.EXIT: timedelta(hours=24),
    AwarenessDomain.CANDIDATE: timedelta(hours=24),
    AwarenessDomain.POSITION: timedelta(hours=24),
    AwarenessDomain.CAPITAL: timedelta(hours=24),
    AwarenessDomain.PNL: timedelta(hours=24),
    AwarenessDomain.NEWS: timedelta(hours=24),
    AwarenessDomain.WHALE: timedelta(hours=24),
    AwarenessDomain.SOCIAL: timedelta(hours=24),
    AwarenessDomain.TIME: timedelta(hours=24),
    AwarenessDomain.RULES: timedelta(days=30),
    AwarenessDomain.MEMORY: timedelta(days=30),
}


EVENT_DOMAIN_MAP: dict[str, tuple[AwarenessDomain, ...]] = {
    "NEWS_DETECTED": (AwarenessDomain.NEWS,),
    "WHALE_DETECTED": (AwarenessDomain.WHALE,),
    "SOCIAL_SPIKE": (AwarenessDomain.SOCIAL,),
    "MARKET_REPRICING": (AwarenessDomain.TIME,),
    "LIQUIDITY_CHANGED": (AwarenessDomain.LIQUIDITY,),
    "SPREAD_CHANGED": (AwarenessDomain.LIQUIDITY,),
    "ORDERBOOK_REFRESHED": (AwarenessDomain.ORDERBOOK,),
    "TOKEN_BOOK_UNAVAILABLE": (AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY),
    "MARKET_RESOLVED": (AwarenessDomain.TIME, AwarenessDomain.ORDERBOOK),
    "SIDE_DETERMINED": (AwarenessDomain.CANDIDATE,),
    "TRUSTED_ORDERBOOK_CREATED": (AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY),
    "RISK_CHANGED": (AwarenessDomain.RISK,),
    "EXIT_CHANGED": (AwarenessDomain.EXIT,),
    "ELIGIBILITY_CHANGED": (AwarenessDomain.CANDIDATE,),
    "PAPER_INTENT_CREATED": (AwarenessDomain.CANDIDATE,),
    "POSITION_OPENED": (AwarenessDomain.POSITION,),
    "POSITION_CLOSED": (AwarenessDomain.POSITION, AwarenessDomain.EXIT),
    "POSITION_ORDERBOOK_REFRESHED": (AwarenessDomain.POSITION, AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY),
    "POSITION_EXIT_RISK": (AwarenessDomain.POSITION, AwarenessDomain.EXIT, AwarenessDomain.RISK, AwarenessDomain.LIQUIDITY),
    "TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION": (AwarenessDomain.POSITION, AwarenessDomain.ORDERBOOK, AwarenessDomain.LIQUIDITY, AwarenessDomain.EXIT),
    "EXIT_REVIEW": (AwarenessDomain.POSITION, AwarenessDomain.EXIT),
    "HOLD_REVIEW": (AwarenessDomain.POSITION, AwarenessDomain.EXIT),
    "TOKEN_IDENTITY_DRIFT_REVIEW": (AwarenessDomain.POSITION, AwarenessDomain.RISK, AwarenessDomain.ORDERBOOK),
    "MISSING_POSITION_TOKEN": (AwarenessDomain.POSITION, AwarenessDomain.ORDERBOOK),
    "PNL_CHANGED": (AwarenessDomain.PNL,),
    "CAPITAL_CHANGED": (AwarenessDomain.CAPITAL,),
    "NO_TRADE_RECORDED": (AwarenessDomain.RISK, AwarenessDomain.CANDIDATE),
    "AI_CONTEXT_UPDATED": (AwarenessDomain.CANDIDATE,),
    "AI_CONTEXT_UNAVAILABLE": (AwarenessDomain.CANDIDATE,),
    "MEMORY_UPDATED": (AwarenessDomain.MEMORY,),
}


NEURON_DOMAIN_MAP: dict[str, AwarenessDomain] = {
    "news": AwarenessDomain.NEWS,
    "rules": AwarenessDomain.RULES,
    "rules_wording": AwarenessDomain.RULES,
    "liquidity": AwarenessDomain.LIQUIDITY,
    "fees": AwarenessDomain.FEES,
    "time": AwarenessDomain.TIME,
}


ALL_DOMAINS: tuple[AwarenessDomain, ...] = tuple(AwarenessDomain)
