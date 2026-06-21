from __future__ import annotations

from app.services.capital_allocator import LiveCapitalSource
from app.stage4.config import load_stage4_settings_from_env


class ExplodingExecutionClient:
    def get_balance_allowance(self, *, token_id=None):  # pragma: no cover - should never be called
        raise AssertionError("live balance endpoint should not be called while live is disabled")


def test_live_capital_source_does_not_call_external_balance_when_live_disabled() -> None:
    settings = load_stage4_settings_from_env(
        {
            "LIVE_TRADING_ENABLED": "false",
            "LIVE_KILL_SWITCH": "true",
            "POLY_API_KEY": "present",
            "POLY_API_SECRET": "present",
            "POLY_API_PASSPHRASE": "present",
        }
    )

    snapshot = LiveCapitalSource(
        stage4_settings=settings,
        execution_client=ExplodingExecutionClient(),
    ).snapshot()

    assert snapshot.source_status == "DISABLED"
    assert snapshot.metadata["reason"] == "live_trading_disabled_or_kill_switch_active"
    assert snapshot.available_cash_usd == 0.0
