from __future__ import annotations

from pathlib import Path


def test_polybot_terminal_commands_exist_and_call_safe_endpoints() -> None:
    script = Path("tools/polybot.ps1")
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    for command in ("status", "on", "off", "report", "health"):
        assert f'"{command}"' in text
    assert "/dashboard/api/v2/control/system-overview" in text
    assert "/dashboard/api/v2/control/actions/system-on" in text
    assert "/dashboard/api/v2/control/actions/system-off" in text
    assert "/dashboard/api/v2/control/actions/enable-paper-simulation" in text


def test_polybot_terminal_commands_do_not_print_secret_files_or_env() -> None:
    text = Path("tools/polybot.ps1").read_text(encoding="utf-8")
    forbidden = (
        "POLY_PRIVATE_KEY",
        "POLYMARKET_CLOB_SECRET",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "Get-Content .env",
        "cat .env",
    )
    assert not any(item in text for item in forbidden)
