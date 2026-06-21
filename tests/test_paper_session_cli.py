from __future__ import annotations

from pathlib import Path


def test_polybot_cli_exposes_official_paper_session_commands() -> None:
    script = Path("tools/polybot.ps1").read_text(encoding="utf-8")

    assert '"reset-paper-session"' in script
    assert '"restart-paper-session"' in script
    assert '"paper-session-status"' in script
    assert '"paper-session-history"' in script
    assert "/dashboard/api/v2/control/paper-session/reset" in script
    assert "-balance 1000" in script


def test_restart_paper_session_chains_reset_health_and_on() -> None:
    script = Path("tools/polybot.ps1").read_text(encoding="utf-8")
    restart_block = script.split('"restart-paper-session"')[1].split('"on"')[0]

    assert "reset-paper-session" in restart_block
    assert "health" in restart_block
    assert "on -mode paper" in restart_block

