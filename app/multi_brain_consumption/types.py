from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.shared_awareness.types import AwarenessDomain


class BrainType(StrEnum):
    RISK_BRAIN = "RISK_BRAIN"
    EXIT_BRAIN = "EXIT_BRAIN"
    CAPITAL_BRAIN = "CAPITAL_BRAIN"
    CONTEXT_BRAIN = "CONTEXT_BRAIN"
    POSITION_BRAIN = "POSITION_BRAIN"
    COORDINATOR_OBSERVER = "COORDINATOR_OBSERVER"


class BrainStance(StrEnum):
    SUPPORT = "SUPPORT"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class BrainSpec:
    brain_type: BrainType
    brain_name: str
    consumed_domains: tuple[AwarenessDomain, ...]
    required_domains: tuple[AwarenessDomain, ...]
    optional_without_block: tuple[AwarenessDomain, ...] = ()


BRAIN_SPECS: dict[BrainType, BrainSpec] = {
    BrainType.RISK_BRAIN: BrainSpec(
        brain_type=BrainType.RISK_BRAIN,
        brain_name="Risk Brain",
        consumed_domains=(
            AwarenessDomain.RULES,
            AwarenessDomain.LIQUIDITY,
            AwarenessDomain.ORDERBOOK,
            AwarenessDomain.FEES,
            AwarenessDomain.TIME,
            AwarenessDomain.NEWS,
            AwarenessDomain.CAPITAL,
        ),
        required_domains=(
            AwarenessDomain.RULES,
            AwarenessDomain.LIQUIDITY,
            AwarenessDomain.ORDERBOOK,
            AwarenessDomain.FEES,
            AwarenessDomain.CAPITAL,
        ),
        optional_without_block=(AwarenessDomain.NEWS, AwarenessDomain.TIME),
    ),
    BrainType.EXIT_BRAIN: BrainSpec(
        brain_type=BrainType.EXIT_BRAIN,
        brain_name="Exit Brain",
        consumed_domains=(
            AwarenessDomain.EXIT,
            AwarenessDomain.RISK,
            AwarenessDomain.LIQUIDITY,
            AwarenessDomain.ORDERBOOK,
            AwarenessDomain.TIME,
            AwarenessDomain.POSITION,
            AwarenessDomain.PNL,
        ),
        required_domains=(AwarenessDomain.RISK, AwarenessDomain.LIQUIDITY, AwarenessDomain.ORDERBOOK),
        optional_without_block=(AwarenessDomain.TIME, AwarenessDomain.POSITION, AwarenessDomain.PNL, AwarenessDomain.EXIT),
    ),
    BrainType.CAPITAL_BRAIN: BrainSpec(
        brain_type=BrainType.CAPITAL_BRAIN,
        brain_name="Capital Brain",
        consumed_domains=(
            AwarenessDomain.CAPITAL,
            AwarenessDomain.FEES,
            AwarenessDomain.TIME,
            AwarenessDomain.PNL,
            AwarenessDomain.POSITION,
            AwarenessDomain.RISK,
            AwarenessDomain.EXIT,
        ),
        required_domains=(AwarenessDomain.CAPITAL,),
        optional_without_block=(AwarenessDomain.TIME, AwarenessDomain.PNL, AwarenessDomain.POSITION, AwarenessDomain.RISK, AwarenessDomain.EXIT),
    ),
    BrainType.CONTEXT_BRAIN: BrainSpec(
        brain_type=BrainType.CONTEXT_BRAIN,
        brain_name="Context Brain",
        consumed_domains=(
            AwarenessDomain.NEWS,
            AwarenessDomain.WHALE,
            AwarenessDomain.SOCIAL,
            AwarenessDomain.RULES,
            AwarenessDomain.MEMORY,
            AwarenessDomain.CANDIDATE,
        ),
        required_domains=(AwarenessDomain.RULES, AwarenessDomain.CANDIDATE),
        optional_without_block=(AwarenessDomain.NEWS, AwarenessDomain.WHALE, AwarenessDomain.SOCIAL, AwarenessDomain.MEMORY),
    ),
    BrainType.POSITION_BRAIN: BrainSpec(
        brain_type=BrainType.POSITION_BRAIN,
        brain_name="Position Brain",
        consumed_domains=(
            AwarenessDomain.POSITION,
            AwarenessDomain.PNL,
            AwarenessDomain.RISK,
            AwarenessDomain.EXIT,
            AwarenessDomain.NEWS,
            AwarenessDomain.LIQUIDITY,
        ),
        required_domains=(AwarenessDomain.POSITION,),
        optional_without_block=(AwarenessDomain.PNL, AwarenessDomain.RISK, AwarenessDomain.EXIT, AwarenessDomain.NEWS, AwarenessDomain.LIQUIDITY),
    ),
}


OPINION_BRAIN_TYPES: tuple[BrainType, ...] = (
    BrainType.RISK_BRAIN,
    BrainType.EXIT_BRAIN,
    BrainType.CAPITAL_BRAIN,
    BrainType.CONTEXT_BRAIN,
    BrainType.POSITION_BRAIN,
)
