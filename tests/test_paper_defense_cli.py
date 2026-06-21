from __future__ import annotations

from pathlib import Path


def test_polybot_cli_exposes_paper_defense_commands() -> None:
    script = Path("tools/polybot.ps1").read_text(encoding="utf-8")
    assert '"paper-defense"' in script
    assert '"set-paper-defense"' in script
    assert '"paper-session-report"' in script
    assert '"export-paper-session"' in script
    assert "-defense" in script
    assert "/dashboard/api/v2/control/paper-defense" in script
