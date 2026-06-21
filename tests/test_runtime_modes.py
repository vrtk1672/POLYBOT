from __future__ import annotations

import pytest

from app.runtime.modes import RuntimeAction, RuntimeMode, get_permissions_for_mode, parse_runtime_mode


def test_every_runtime_mode_has_permissions() -> None:
    for mode in RuntimeMode:
        permissions = get_permissions_for_mode(mode)
        assert permissions.max_risk_multiplier >= 0


def test_kill_blocks_trading_actions() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.KILL)
    for action in [
        RuntimeAction.GENERATE_SIGNAL,
        RuntimeAction.OPEN_PAPER_POSITION,
        RuntimeAction.OPEN_SHADOW_POSITION,
        RuntimeAction.OPEN_LIVE_POSITION,
        RuntimeAction.SEND_LIVE_ORDER,
        RuntimeAction.USE_ATTACK_ENGINE,
        RuntimeAction.CALL_CLOUD_AI,
    ]:
        assert not permissions.allows(action)


def test_data_only_blocks_orders_and_positions() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.DATA_ONLY)
    assert permissions.allows(RuntimeAction.COLLECT_DATA)
    assert permissions.allows(RuntimeAction.SCORE_MARKET)
    assert not permissions.allows(RuntimeAction.GENERATE_SIGNAL)
    assert not permissions.allows(RuntimeAction.OPEN_PAPER_POSITION)
    assert not permissions.allows(RuntimeAction.SEND_LIVE_ORDER)


def test_paper_allows_paper_but_blocks_live() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.PAPER)
    assert permissions.allows(RuntimeAction.RUN_PAPER_ENGINE)
    assert permissions.allows(RuntimeAction.OPEN_PAPER_POSITION)
    assert not permissions.allows(RuntimeAction.SEND_LIVE_ORDER)
    assert not permissions.allows(RuntimeAction.RUN_LIVE_ENGINE)


def test_shadow_live_blocks_live_order_sending() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.SHADOW_LIVE)
    assert permissions.allows(RuntimeAction.RUN_SHADOW_ENGINE)
    assert permissions.allows(RuntimeAction.CREATE_ORDER_INTENT, {"shadow": True})
    assert not permissions.allows(RuntimeAction.SEND_LIVE_ORDER)


def test_cooldown_blocks_new_entries() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.COOLDOWN)
    assert permissions.allows(RuntimeAction.CLOSE_POSITION)
    assert not permissions.allows(RuntimeAction.OPEN_PAPER_POSITION)
    assert permissions.max_risk_multiplier < 1


def test_attack_mode_requires_governor_state_for_actual_execution() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.ATTACK_MODE)
    assert permissions.can_use_attack_engines
    assert not permissions.can_create_live_orders


def test_invalid_mode_parsing_fails_clearly() -> None:
    with pytest.raises(ValueError):
        parse_runtime_mode("definitely_not_a_mode")
