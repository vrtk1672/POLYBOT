from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_20_scripts_force_live_disabled() -> None:
    script_names = [
        "run_v2_20_data_only_smoke.ps1",
        "run_v2_20_paper_smoke.ps1",
    ]

    for script_name in script_names:
        text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert '$env:LIVE_TRADING_ENABLED = "false"' in text
        assert '$env:LIVE_EXECUTION_ENABLED = "false"' in text
        assert '$env:LIVE_KILL_SWITCH = "true"' in text
        assert "SMALL_LIVE" not in text
        assert "ATTACK_MODE" not in text


def test_long_run_scripts_delegate_to_safe_smoke_scripts() -> None:
    expected = {
        "run_v2_20_24h_data_only.ps1": "run_v2_20_data_only_smoke.ps1",
        "run_v2_20_24h_paper.ps1": "run_v2_20_paper_smoke.ps1",
        "run_v2_20_72h_paper.ps1": "run_v2_20_paper_smoke.ps1",
        "run_v2_20_7d_paper.ps1": "run_v2_20_paper_smoke.ps1",
    }

    for script_name, target in expected.items():
        text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert target in text
        assert "DurationSeconds" in text


def test_verify_scripts_are_read_only() -> None:
    for script in (ROOT / "scripts").glob("verify_v2_20_*.ps1"):
        text = script.read_text(encoding="utf-8").lower()
        assert "/runtime/mode/request" not in text
        assert "/runtime/kill" not in text
        assert "live_trading_enabled = \"true\"" not in text
