from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class RuntimeMode(StrEnum):
    DATA_ONLY = "DATA_ONLY"
    PAPER = "PAPER"
    SHADOW_LIVE = "SHADOW_LIVE"
    SMALL_LIVE = "SMALL_LIVE"
    ATTACK_MODE = "ATTACK_MODE"
    COOLDOWN = "COOLDOWN"
    KILL = "KILL"


class RuntimeAction(StrEnum):
    COLLECT_DATA = "COLLECT_DATA"
    SCORE_MARKET = "SCORE_MARKET"
    GENERATE_SIGNAL = "GENERATE_SIGNAL"
    OPEN_PAPER_POSITION = "OPEN_PAPER_POSITION"
    OPEN_SHADOW_POSITION = "OPEN_SHADOW_POSITION"
    OPEN_LIVE_POSITION = "OPEN_LIVE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    CREATE_ORDER_INTENT = "CREATE_ORDER_INTENT"
    SEND_LIVE_ORDER = "SEND_LIVE_ORDER"
    USE_ATTACK_ENGINE = "USE_ATTACK_ENGINE"
    CALL_CLOUD_AI = "CALL_CLOUD_AI"
    RUN_INTELLIGENCE = "RUN_INTELLIGENCE"
    RUN_PAPER_SIMULATION = "RUN_PAPER_SIMULATION"
    RUN_PAPER_ENGINE = "RUN_PAPER_ENGINE"
    RUN_SHADOW_ENGINE = "RUN_SHADOW_ENGINE"
    RUN_LIVE_ENGINE = "RUN_LIVE_ENGINE"


@dataclass(frozen=True, slots=True)
class RuntimePermissions:
    can_collect_data: bool = False
    can_score_opportunities: bool = False
    can_generate_signals: bool = False
    can_open_paper_positions: bool = False
    can_create_shadow_orders: bool = False
    can_create_live_orders: bool = False
    can_open_new_positions: bool = False
    can_close_positions: bool = False
    can_use_attack_engines: bool = False
    can_call_cloud_ai: bool = False
    can_run_intelligence: bool = False
    can_run_paper_simulation: bool = False
    can_run_paper_engine: bool = False
    can_run_shadow_engine: bool = False
    can_run_live_engine: bool = False
    max_risk_multiplier: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def allows(self, action: RuntimeAction, metadata: dict[str, object] | None = None) -> bool:
        metadata = metadata or {}
        if action == RuntimeAction.COLLECT_DATA:
            return self.can_collect_data
        if action == RuntimeAction.SCORE_MARKET:
            return self.can_score_opportunities
        if action == RuntimeAction.GENERATE_SIGNAL:
            return self.can_generate_signals
        if action == RuntimeAction.OPEN_PAPER_POSITION:
            return self.can_open_paper_positions and self.can_open_new_positions
        if action == RuntimeAction.OPEN_SHADOW_POSITION:
            return self.can_create_shadow_orders and self.can_open_new_positions
        if action == RuntimeAction.OPEN_LIVE_POSITION:
            return self.can_create_live_orders and self.can_open_new_positions
        if action == RuntimeAction.CLOSE_POSITION:
            return self.can_close_positions
        if action == RuntimeAction.CREATE_ORDER_INTENT:
            return (
                (metadata.get("shadow") is True and self.can_create_shadow_orders)
                or (metadata.get("paper") is True and self.can_open_paper_positions)
                or (metadata.get("live") is True and self.can_create_live_orders)
            )
        if action == RuntimeAction.SEND_LIVE_ORDER:
            return self.can_create_live_orders and self.can_run_live_engine
        if action == RuntimeAction.USE_ATTACK_ENGINE:
            return self.can_use_attack_engines
        if action == RuntimeAction.CALL_CLOUD_AI:
            return self.can_call_cloud_ai
        if action == RuntimeAction.RUN_INTELLIGENCE:
            return self.can_run_intelligence
        if action == RuntimeAction.RUN_PAPER_SIMULATION:
            return self.can_run_paper_simulation
        if action == RuntimeAction.RUN_PAPER_ENGINE:
            return self.can_run_paper_engine
        if action == RuntimeAction.RUN_SHADOW_ENGINE:
            return self.can_run_shadow_engine
        if action == RuntimeAction.RUN_LIVE_ENGINE:
            return self.can_run_live_engine
        return False


def parse_runtime_mode(value: RuntimeMode | str) -> RuntimeMode:
    if isinstance(value, RuntimeMode):
        return value
    return RuntimeMode(str(value).strip().upper())


def parse_runtime_action(value: RuntimeAction | str) -> RuntimeAction:
    if isinstance(value, RuntimeAction):
        return value
    return RuntimeAction(str(value).strip().upper())


def get_permissions_for_mode(mode: RuntimeMode | str) -> RuntimePermissions:
    mode = parse_runtime_mode(mode)
    if mode == RuntimeMode.DATA_ONLY:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            can_run_paper_simulation=True,
            max_risk_multiplier=0.0,
        )
    if mode == RuntimeMode.PAPER:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_generate_signals=True,
            can_open_paper_positions=True,
            can_open_new_positions=True,
            can_close_positions=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            can_run_paper_simulation=True,
            can_run_paper_engine=True,
            max_risk_multiplier=1.0,
        )
    if mode == RuntimeMode.SHADOW_LIVE:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_generate_signals=True,
            can_create_shadow_orders=True,
            can_open_new_positions=True,
            can_close_positions=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            can_run_shadow_engine=True,
            max_risk_multiplier=0.0,
        )
    if mode == RuntimeMode.SMALL_LIVE:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_generate_signals=True,
            can_create_shadow_orders=True,
            can_create_live_orders=True,
            can_open_new_positions=True,
            can_close_positions=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            can_run_shadow_engine=True,
            can_run_live_engine=True,
            max_risk_multiplier=0.1,
        )
    if mode == RuntimeMode.ATTACK_MODE:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_generate_signals=True,
            can_open_new_positions=True,
            can_close_positions=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            can_use_attack_engines=True,
            max_risk_multiplier=0.0,
        )
    if mode == RuntimeMode.COOLDOWN:
        return RuntimePermissions(
            can_collect_data=True,
            can_score_opportunities=True,
            can_close_positions=True,
            can_call_cloud_ai=True,
            can_run_intelligence=True,
            max_risk_multiplier=0.25,
        )
    return RuntimePermissions()
