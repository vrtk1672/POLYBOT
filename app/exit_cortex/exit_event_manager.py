from __future__ import annotations


class ExitEventManager:
    def event_type_for_trigger(self, trigger_type: str) -> str:
        return {
            "TAKE_PROFIT": "EXIT_TAKE_PROFIT_TRIGGERED",
            "PARTIAL_TAKE_PROFIT": "EXIT_PARTIAL_TAKE_PROFIT_TRIGGERED",
            "STOP_LOSS": "EXIT_STOP_LOSS_TRIGGERED",
            "MAX_HOLD": "EXIT_MAX_HOLD_TRIGGERED",
            "NEWS_INVALIDATED": "EXIT_NEWS_INVALIDATED_TRIGGERED",
            "SPREAD_EXIT": "EXIT_SPREAD_EXIT_TRIGGERED",
            "MOMENTUM_DECAY": "EXIT_MOMENTUM_DECAY_TRIGGERED",
            "EMERGENCY_EXIT": "EXIT_EMERGENCY_TRIGGERED",
        }.get(trigger_type, "EXIT_TRIGGER_DETECTED")

