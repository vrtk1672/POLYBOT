from __future__ import annotations

from app.control_center.system_overview import derive_execution_mode


def test_execution_mode_paper_is_adapter_state_not_live_state() -> None:
    assert derive_execution_mode(system_power="ON", paper_simulation_enabled=True) == "PAPER"
    assert derive_execution_mode(system_power="ON", paper_simulation_enabled=False) == "DATA_ONLY"
    assert derive_execution_mode(system_power="OFF", paper_simulation_enabled=True) == "DISABLED"


def test_paper_adapter_script_keeps_live_adapter_disabled() -> None:
    script = open("tools/polybot.ps1", encoding="utf-8").read()
    assert "enable-paper-simulation" in script
    assert "system-on" in script
    assert "live_adapter = $false" in script
    assert "Only -mode paper is supported" in script
