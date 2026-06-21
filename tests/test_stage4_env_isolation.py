from __future__ import annotations

import importlib
import os
from pathlib import Path

from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.state_governor import StateGovernor
from app.stage4.config import (
    Stage4Settings,
    load_stage4_settings_from_env,
)


def test_importing_stage4_config_does_not_load_local_env(monkeypatch) -> None:
    for key in ("LIVE_TRADING_ENABLED", "LIVE_KILL_SWITCH", "POLY_PRIVATE_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("POLYBOT_ENV_FILE_LOADED", raising=False)

    import app.stage4.config as stage4_config

    importlib.reload(stage4_config)

    assert os.environ.get("POLYBOT_ENV_FILE_LOADED") is None
    assert os.environ.get("LIVE_TRADING_ENABLED") is None
    assert os.environ.get("POLY_PRIVATE_KEY") is None


def test_stage4_settings_with_empty_env_contain_no_live_credentials(monkeypatch) -> None:
    for key in ("POLY_PRIVATE_KEY", "POLY_FUNDER", "POLY_API_KEY", "POLY_API_SECRET", "POLY_API_PASSPHRASE"):
        monkeypatch.delenv(key, raising=False)

    settings = load_stage4_settings_from_env({})

    assert settings.poly_private_key is None
    assert settings.poly_funder is None
    assert settings.poly_api_key is None
    assert settings.poly_api_secret is None
    assert settings.poly_api_passphrase is None
    assert settings.has_l1_credentials is False
    assert settings.has_l2_credentials is False


def test_live_trading_enabled_defaults_false() -> None:
    assert load_stage4_settings_from_env({}).live_trading_enabled is False


def test_live_kill_switch_defaults_true() -> None:
    assert load_stage4_settings_from_env({}).live_kill_switch is True


def test_explicit_fake_env_values_are_respected() -> None:
    settings = load_stage4_settings_from_env(
        {
            "LIVE_TRADING_ENABLED": "true",
            "LIVE_KILL_SWITCH": "false",
            "LIVE_MARKET_WHITELIST": "market-1,market-2",
            "POLY_API_KEY": "fake-key",
            "POLY_API_SECRET": "fake-secret",
            "POLY_API_PASSPHRASE": "fake-passphrase",
        }
    )

    assert settings.live_trading_enabled is True
    assert settings.live_kill_switch is False
    assert settings.live_market_whitelist == ["market-1", "market-2"]
    assert settings.has_l2_credentials is True


def test_local_env_file_presence_does_not_change_stage4_test_behavior(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LIVE_TRADING_ENABLED=true",
                "LIVE_KILL_SWITCH=false",
                "POLY_PRIVATE_" + "KEY=placeholder",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in ("LIVE_TRADING_ENABLED", "LIVE_KILL_SWITCH", "POLY_PRIVATE_KEY"):
        monkeypatch.delenv(key, raising=False)

    settings = Stage4Settings()

    assert settings.live_trading_enabled is False
    assert settings.live_kill_switch is True
    assert settings.poly_private_key is None


def _governor_for_mode(mode: RuntimeMode) -> StateGovernor:
    governor = StateGovernor()
    state = RuntimeState(
        current_mode=mode,
        previous_mode=None,
        state_status="ACTIVE",
        kill_switch_active=mode == RuntimeMode.KILL,
        cooldown_active=mode == RuntimeMode.COOLDOWN,
        attack_mode_active=False,
        reason="test",
        actor="test",
        metadata_json={},
    )
    governor.get_current_state = lambda: state  # type: ignore[method-assign]
    return governor


def test_state_governor_blocks_send_live_order_outside_live_certified_modes() -> None:
    for mode in [RuntimeMode.DATA_ONLY, RuntimeMode.PAPER, RuntimeMode.SHADOW_LIVE, RuntimeMode.COOLDOWN, RuntimeMode.KILL]:
        assert _governor_for_mode(mode).can_execute(RuntimeAction.SEND_LIVE_ORDER) is False


def test_paper_mode_cannot_send_live_orders_even_if_env_says_live_enabled() -> None:
    settings = load_stage4_settings_from_env({"LIVE_TRADING_ENABLED": "true", "LIVE_KILL_SWITCH": "false"})
    assert settings.live_trading_enabled is True
    assert _governor_for_mode(RuntimeMode.PAPER).can_execute(RuntimeAction.SEND_LIVE_ORDER) is False


def test_shadow_live_cannot_send_live_orders_even_if_env_says_live_enabled() -> None:
    settings = load_stage4_settings_from_env({"LIVE_TRADING_ENABLED": "true", "LIVE_KILL_SWITCH": "false"})
    assert settings.live_trading_enabled is True
    assert _governor_for_mode(RuntimeMode.SHADOW_LIVE).can_execute(RuntimeAction.SEND_LIVE_ORDER) is False


def test_kill_blocks_live_regardless_of_env() -> None:
    settings = load_stage4_settings_from_env({"LIVE_TRADING_ENABLED": "true", "LIVE_KILL_SWITCH": "false"})
    assert settings.live_trading_enabled is True
    assert _governor_for_mode(RuntimeMode.KILL).can_execute(RuntimeAction.SEND_LIVE_ORDER) is False
