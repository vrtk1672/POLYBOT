from __future__ import annotations

import os
from pathlib import Path

from app.env_runtime import load_env_file_into_process


def test_env_runtime_loader_injects_missing_raw_keys_without_overwriting(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ANTHROPIC_API_KEY=test-anthropic-key",
                "LIVE_TRADING_ENABLED=false",
                "POLYBOT_RUNTIME_MODE=paper_safe",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    status = load_env_file_into_process(env_path)

    assert status.exists is True
    assert status.loaded is True
    assert os.environ["ANTHROPIC_API_KEY"] == "test-anthropic-key"
    assert os.environ["LIVE_TRADING_ENABLED"] == "true"
    assert os.environ["POLYBOT_RUNTIME_MODE"] == "paper_safe"
    assert os.environ["POLYBOT_ENV_FILE_LOADED"] == "true"
