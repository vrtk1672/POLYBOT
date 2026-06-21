from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EnvFileStatus:
    path: str
    exists: bool
    loaded: bool
    loaded_keys: int


def load_env_file_into_process(env_path: str | Path | None = None) -> EnvFileStatus:
    path = Path(env_path) if env_path is not None else _default_env_path()
    if not path.exists():
        os.environ["POLYBOT_ENV_FILE_EXISTS"] = "false"
        os.environ["POLYBOT_ENV_FILE_LOADED"] = "false"
        os.environ["POLYBOT_ENV_FILE_PATH"] = str(path)
        return EnvFileStatus(path=str(path), exists=False, loaded=False, loaded_keys=0)

    loaded_keys = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value
        loaded_keys += 1

    os.environ["POLYBOT_ENV_FILE_EXISTS"] = "true"
    os.environ["POLYBOT_ENV_FILE_LOADED"] = "true"
    os.environ["POLYBOT_ENV_FILE_PATH"] = str(path)
    return EnvFileStatus(path=str(path), exists=True, loaded=True, loaded_keys=loaded_keys)


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"
